"""Frozen data structures shared across modules. Imports nothing from the package."""

from dataclasses import dataclass, field
from typing import Optional, Tuple

CARD = "CARD"
TEXT = "TEXT"

PASSED = "PASSED"
FAILED = "FAILED"
INTERRUPTED = "INTERRUPTED"


@dataclass(frozen=True)
class TestCounts:
    total: int
    passed: int
    failed: int
    skipped: int
    failed_names: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CiInfo:
    provider: Optional[str] = None
    branch: Optional[str] = None
    commit: Optional[str] = None
    actor: Optional[str] = None
    build_url: Optional[str] = None

    @property
    def detected(self) -> bool:
        return self.provider is not None


@dataclass(frozen=True)
class RunMeta:
    project: str
    command: str
    run_id: str
    started_at: str
    version: str
    environment: Optional[str] = None
    ci: CiInfo = field(default_factory=CiInfo)


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    duration_seconds: float
    interrupted: bool = False


def resolve_status(result: RunResult, counts: Optional[TestCounts]) -> str:
    """Exit code is authoritative; recorded failures can only add a failure."""
    if result.interrupted:
        return INTERRUPTED
    if result.exit_code != 0:
        return FAILED
    if counts is not None and counts.failed > 0:
        return FAILED
    return PASSED
