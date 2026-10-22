"""Chaos run use-cases, free of any terminal UI so the CLI and the chat REPL can share them."""
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from loki.ai.brain import AIBrain
from loki.config import load_loki_config, resolve_api_chaos_config
from loki.engine.api_chaos import ApiChaosConfig
from loki.engine.ci import CIGate
from loki.engine.reporter import IncidentReporter
from loki.engine.sandbox import ChaosSandbox
from loki.models import IncidentReport
from loki.personas.base import BasePersona
from loki.personas.registry import API_CHAOS_PERSONAS, PersonaChoice, build_persona
from loki.safety import extract_host, is_host_authorized, is_local_host

JOURNEYS_DIR = Path(".loki/journeys")
RULES_FILE = Path(".loki/rules.md")


class RunSetupError(Exception):
    """A run cannot start because its inputs are missing or invalid."""

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint


class TargetNotAuthorizedError(Exception):
    """Raised when an attack is requested against a non-local host that was never authorized."""


@dataclass
class RunOptions:
    """Raw user-facing options for a chaos run, as given on the CLI or in chat."""
    url: str | None = None
    duration: int | None = None
    headed: bool = False
    persona: PersonaChoice | None = None
    swarm: bool = False
    journey: str | None = None
    device: str | None = None
    orientation: str = "portrait"
    concurrency: int = 1
    target_selector: str | None = None
    api_chaos: bool | None = None
    fault_rate: float | None = None
    auth_chaos: bool | None = None
    browser: str = "chromium"
    seed: int | None = None


@dataclass
class RunPlan:
    """A fully resolved run: options merged with .loki/config.yaml and the journey blueprint."""
    url: str
    duration: int
    headless: bool
    browser: str
    seed: int
    persona_choice: PersonaChoice
    persona: BasePersona | None
    api_chaos_config: ApiChaosConfig
    journey_data: dict[str, Any] | None
    device: str | None
    orientation: str
    concurrency: int
    target_selector: str | None

    @property
    def api_chaos_active(self) -> bool:
        return self.api_chaos_config.enabled and self.persona_choice in API_CHAOS_PERSONAS


def load_journey(journey: str) -> dict[str, Any]:
    """Loads a recorded journey blueprint by name (from .loki/journeys/) or by path."""
    journey_path = JOURNEYS_DIR / (journey if journey.endswith(".json") else f"{journey}.json")
    if not journey_path.exists():
        journey_path = Path(journey)
    if not journey_path.exists():
        raise RunSetupError(f"Journey blueprint '{journey}' not found in .loki/journeys/")
    try:
        with open(journey_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise RunSetupError(f"Could not read journey blueprint '{journey}': {e}") from e


def _first_journey_click(journey_data: dict[str, Any] | None) -> str | None:
    for step in (journey_data or {}).get("steps", []):
        if step.get("action") == "click" and step.get("selector"):
            return step["selector"]
    return None


def prepare_run(options: RunOptions) -> RunPlan:
    """Resolves options against config and journey, seeds the global RNG, and builds the persona."""
    journey_data = load_journey(options.journey) if options.journey else None

    config = load_loki_config()
    target_config = config.get("target", {})
    url = options.url or (journey_data.get("start_url") if journey_data else None) or target_config.get("default_url")
    if not url:
        raise RunSetupError(
            "No target URL provided and no default found in .loki/config.yaml.",
            hint="Run `loki init` first, or pass a URL: `loki run <url>`",
        )

    chaos_config = config.get("chaos", {})
    persona_choice = options.persona
    if options.swarm:
        persona_choice = PersonaChoice.SWARM
    elif persona_choice is None:
        try:
            persona_choice = PersonaChoice(chaos_config.get("default_persona", "rage-clicker"))
        except ValueError:
            persona_choice = PersonaChoice.RAGE_CLICKER

    api_chaos_config = resolve_api_chaos_config(
        cli_enabled=options.api_chaos,
        fault_rate=options.fault_rate,
        auth_chaos=options.auth_chaos,
    )

    seed = options.seed if options.seed is not None else random.randint(100000, 999999)
    random.seed(seed)

    persona = build_persona(
        persona_choice,
        click_burst_count=int(chaos_config.get("click_burst_count", 5)),
        api_chaos_config=api_chaos_config,
        seed=seed,
    )

    target_selector = options.target_selector
    if options.concurrency > 1 and not target_selector:
        target_selector = _first_journey_click(journey_data)

    return RunPlan(
        url=url,
        duration=options.duration if options.duration is not None else target_config.get("timeout_seconds", 5),
        headless=target_config.get("headless", True) and not options.headed,
        browser=options.browser,
        seed=seed,
        persona_choice=persona_choice,
        persona=persona,
        api_chaos_config=api_chaos_config,
        journey_data=journey_data,
        device=options.device,
        orientation=options.orientation,
        concurrency=options.concurrency,
        target_selector=target_selector,
    )


def run_attack(plan: RunPlan) -> IncidentReport:
    """Executes the browser attack (persona session or concurrency probe) described by the plan.

    Callers must obtain authorization first (see cli.ensure_target_authorized); this re-checks
    it as defense in depth so no caller can reach a non-local host without it.
    """
    if not (is_local_host(plan.url) or is_host_authorized(plan.url)):
        raise TargetNotAuthorizedError(
            f"Target host '{extract_host(plan.url)}' is not authorized. Confirm ownership first."
        )

    sandbox = ChaosSandbox(headless=plan.headless, browser_name=plan.browser, seed=plan.seed)
    if plan.concurrency > 1:
        return sandbox.run_concurrent_probe(
            target_url=plan.url,
            concurrency=plan.concurrency,
            selector=plan.target_selector,
            device_name=plan.device,
            orientation=plan.orientation,
        )
    return sandbox.run_session(
        target_url=plan.url,
        duration=plan.duration,
        persona=plan.persona,
        journey_data=plan.journey_data,
        device_name=plan.device,
        orientation=plan.orientation,
    )


def evaluate_rules(report: IncidentReport, rules_file: Path = RULES_FILE) -> list[dict[str, Any]] | None:
    """Evaluates the natural-language business rules against the report. None if there are no rules."""
    if not rules_file.exists():
        return None
    return AIBrain().evaluate_business_rules(report=report, rules_content=rules_file.read_text(encoding="utf-8"))


def rules_violated(evaluations: list[dict[str, Any]] | None) -> bool:
    return any(item.get("status") == "VIOLATED" for item in evaluations or [])


def save_artifacts(
    report: IncidentReport,
    evaluations: list[dict[str, Any]] | None,
    report_html: bool = True,
) -> Path | None:
    """Persists the run under .loki/runs/ when it failed or an HTML report was requested."""
    if report.has_crashes or report_html:
        return IncidentReporter().save_session(report, rules_evaluations=evaluations)
    return None


def write_ci_summary(report: IncidentReport, evaluations: list[dict[str, Any]] | None, run_dir: Path | None) -> None:
    """Writes the GitHub Actions step summary (no-op outside GitHub Actions)."""
    CIGate.write_github_step_summary(
        report=report,
        evaluations=evaluations,
        run_dir=run_dir,
        has_violations=rules_violated(evaluations),
    )


def gate_passed(report: IncidentReport, evaluations: list[dict[str, Any]] | None) -> bool:
    """CI/CD quality gate: no failures and no business rule violations."""
    return not report.has_crashes and not rules_violated(evaluations)
