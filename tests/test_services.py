import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from loki.models import IncidentReport
from loki.personas.registry import PersonaChoice
from loki.services.heal import HealError, HealingService
from loki.services.run import (
    RunOptions,
    RunSetupError,
    TargetNotAuthorizedError,
    gate_passed,
    prepare_run,
    rules_violated,
    run_attack,
)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Isolated working directory so .loki/ config, journeys and authorizations don't leak."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".loki" / "journeys").mkdir(parents=True)
    return tmp_path


def write_config(root: Path, text: str):
    (root / ".loki" / "config.yaml").write_text(text, encoding="utf-8")


def test_prepare_run_requires_a_url(workspace):
    with pytest.raises(RunSetupError) as exc:
        prepare_run(RunOptions())
    assert exc.value.hint


def test_prepare_run_uses_config_defaults(workspace):
    write_config(
        workspace,
        "target:\n  default_url: http://localhost:9000\n  timeout_seconds: 7\n"
        "chaos:\n  default_persona: adversary\n",
    )
    plan = prepare_run(RunOptions(seed=42))
    assert plan.url == "http://localhost:9000"
    assert plan.duration == 7
    assert plan.seed == 42
    assert plan.persona_choice == PersonaChoice.ADVERSARY
    assert plan.persona.name == "Adversary"


def test_prepare_run_swarm_flag_overrides_persona(workspace):
    plan = prepare_run(RunOptions(url="http://localhost:8000", persona=PersonaChoice.ADVERSARY, swarm=True, seed=1))
    assert plan.persona_choice == PersonaChoice.SWARM
    assert plan.persona.name == "Swarm"
    assert plan.api_chaos_active


def test_prepare_run_none_persona_is_passive(workspace):
    plan = prepare_run(RunOptions(url="http://localhost:8000", persona=PersonaChoice.NONE, seed=1))
    assert plan.persona is None
    assert not plan.api_chaos_active


def test_prepare_run_missing_journey(workspace):
    with pytest.raises(RunSetupError, match="not found"):
        prepare_run(RunOptions(url="http://localhost:8000", journey="ghost"))


def test_prepare_run_journey_supplies_url_and_concurrency_selector(workspace):
    journey = {
        "name": "checkout",
        "start_url": "http://localhost:8000/shop",
        "steps": [
            {"action": "input", "selector": "#email", "value": "a@b.c"},
            {"action": "click", "selector": "#pay"},
        ],
    }
    (workspace / ".loki" / "journeys" / "checkout.json").write_text(json.dumps(journey), encoding="utf-8")
    plan = prepare_run(RunOptions(journey="checkout", concurrency=3, seed=1))
    assert plan.url == "http://localhost:8000/shop"
    assert plan.target_selector == "#pay"


def test_run_attack_refuses_unauthorized_remote_host(workspace):
    plan = prepare_run(RunOptions(url="https://example.com", seed=1))
    with patch("loki.services.run.ChaosSandbox") as sandbox:
        with pytest.raises(TargetNotAuthorizedError):
            run_attack(plan)
        sandbox.assert_not_called()


def test_run_attack_dispatches_concurrency_probe(workspace):
    plan = prepare_run(RunOptions(url="http://localhost:8000", concurrency=2, target_selector="#go", seed=1))
    with patch("loki.services.run.ChaosSandbox") as sandbox:
        run_attack(plan)
    sandbox.return_value.run_concurrent_probe.assert_called_once()
    sandbox.return_value.run_session.assert_not_called()


def test_gate_and_rule_violations():
    clean = IncidentReport(target_url="http://localhost:8000")
    assert gate_passed(clean, None)
    assert not rules_violated([{"status": "PASSED"}, {"status": "SKIPPED"}])
    assert not gate_passed(clean, [{"status": "VIOLATED"}])

    crashed = IncidentReport(target_url="http://localhost:8000", crashes=["TypeError"])
    assert not gate_passed(crashed, None)


def test_healing_service_wraps_healer_results(tmp_path):
    healer = MagicMock()
    healer.synthesize_patch.return_value = {
        "success": True,
        "target_file": "app.js",
        "explanation": "guard null",
        "original_snippet": "a.b",
        "replacement_snippet": "a?.b",
    }
    healer.apply_patch.return_value = {"success": True, "backup_file": tmp_path / "app.js.loki.bak", "diff": "-a.b\n+a?.b"}
    healer.verify_fix.return_value = {"verified": True, "message": "healed"}

    service = HealingService(healer=healer)
    proposal = service.synthesize(tmp_path)
    assert proposal.target_file == Path("app.js")

    applied = service.apply(proposal)
    assert applied.diff == "-a.b\n+a?.b"

    result = service.verify(applied, tmp_path)
    assert result.verified and result.message == "healed"
    healer.verify_fix.assert_called_once_with(tmp_path, backup_file=applied.backup_file, target_file=Path("app.js"))


def test_healing_service_raises_on_failures(tmp_path):
    healer = MagicMock()
    healer.synthesize_patch.return_value = {"success": False, "error": "no source file"}
    with pytest.raises(HealError, match="no source file"):
        HealingService(healer=healer).synthesize(tmp_path)
