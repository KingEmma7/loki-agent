"""Self-healing use-cases shared by `loki fix --apply` and `loki run --auto-heal`."""
from dataclasses import dataclass
from pathlib import Path
from loki.engine.healer import CodeHealer


class HealError(Exception):
    """A patch could not be synthesized or applied."""


@dataclass
class PatchProposal:
    target_file: Path
    explanation: str | None
    original_snippet: str
    replacement_snippet: str


@dataclass
class AppliedPatch:
    target_file: Path
    backup_file: Path | None
    diff: str | None


@dataclass
class VerificationResult:
    verified: bool
    message: str
    output: str | None = None


class HealingService:
    """Typed facade over CodeHealer's synthesize -> backup/apply -> verify/rollback lifecycle."""

    def __init__(self, healer: CodeHealer | None = None):
        self.healer = healer or CodeHealer()

    def find_run_dir(self, run_id: str | None = None) -> Path | None:
        return self.healer.replayer.get_run_dir(run_id)

    def synthesize(self, run_dir: Path, model: str | None = None) -> PatchProposal:
        patch = self.healer.synthesize_patch(run_dir, model=model)
        if not patch.get("success"):
            raise HealError(patch.get("error") or "Patch synthesis failed.")
        return PatchProposal(
            target_file=Path(patch["target_file"]),
            explanation=patch.get("explanation"),
            original_snippet=patch["original_snippet"],
            replacement_snippet=patch["replacement_snippet"],
        )

    def apply(self, proposal: PatchProposal) -> AppliedPatch:
        """Backs up the target file and writes the patch."""
        applied = self.healer.apply_patch(
            target_file=proposal.target_file,
            original_snippet=proposal.original_snippet,
            replacement_snippet=proposal.replacement_snippet,
        )
        if not applied.get("success"):
            raise HealError(applied.get("error") or "Patch could not be applied.")
        return AppliedPatch(
            target_file=proposal.target_file,
            backup_file=applied.get("backup_file"),
            diff=applied.get("diff"),
        )

    def verify(self, applied: AppliedPatch, run_dir: Path) -> VerificationResult:
        """Replays the captured repro test; rolls the patch back if the crash persists."""
        result = self.healer.verify_fix(run_dir, backup_file=applied.backup_file, target_file=applied.target_file)
        return VerificationResult(
            verified=bool(result.get("verified")),
            message=result.get("message", ""),
            output=result.get("output"),
        )
