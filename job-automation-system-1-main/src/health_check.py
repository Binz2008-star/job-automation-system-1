"""
src/health_check.py
System health check — verifies every layer initialises correctly.

Exit codes:
    0  all checks passed (warnings are OK)
    1  one or more checks failed

Run:
    python -m src.health_check

Output is plain text to stdout — works in CI, Docker HEALTHCHECK,
and terminal equally. Secrets are never printed.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    duration_ms: float
    warning: bool = False


@dataclass
class HealthReport:
    results: List[CheckResult] = field(default_factory=list)

    def record(self, result: CheckResult) -> None:
        self.results.append(result)
        if result.passed and not result.warning:
            symbol = f"{GREEN}✓{RESET}"
        elif result.warning:
            symbol = f"{YELLOW}⚠{RESET}"
        else:
            symbol = f"{RED}✗{RESET}"
        print(f"  {symbol}  {result.name:<50} {result.message}  ({result.duration_ms:.0f}ms)")

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failed(self) -> List[CheckResult]:
        return [r for r in self.results if not r.passed]

    @property
    def warnings(self) -> List[CheckResult]:
        return [r for r in self.results if r.warning]


def _run(name: str, fn: Callable[[], Optional[str]]) -> CheckResult:
    """
    Execute a check function.
    fn() returns None on success, or an error/warning string on failure.
    Strings starting with "warning:" are treated as warnings (passed=True).
    """
    t0 = time.monotonic()
    try:
        msg = fn()
        ms = (time.monotonic() - t0) * 1000
        if msg is None:
            return CheckResult(name=name, passed=True, message="OK", duration_ms=ms)
        is_warn = msg.lower().startswith("warning:")
        return CheckResult(
            name=name, passed=is_warn, message=msg,
            duration_ms=ms, warning=is_warn,
        )
    except Exception as exc:
        ms = (time.monotonic() - t0) * 1000
        return CheckResult(
            name=name, passed=False,
            message=str(exc)[:120],
            duration_ms=ms,
        )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_imports() -> Optional[str]:
    import src.db
    import src.job_history
    import src.applications
    import src.profile
    import src.decision_engine
    import src.response_intelligence
    import src.feedback_loop
    import src.dashboard
    return None


def _check_environment() -> Optional[str]:
    missing = [v for v in ["DATABASE_URL"] if not os.environ.get(v)]
    if missing:
        return f"warning: {', '.join(missing)} not set — JSON fallback active"
    return None


def _check_data_dir() -> Optional[str]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    probe = DATA_DIR / ".health_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return None
    except OSError as exc:
        return f"data dir not writable: {exc}"


def _check_database() -> Optional[str]:
    if not os.environ.get("DATABASE_URL"):
        return "warning: DATABASE_URL not set — skipping DB check"
    from src.db import is_db_available
    if not is_db_available():
        return "database unreachable"
    return None


def _check_json_fallback() -> Optional[str]:
    from src.job_history import load_job_history
    from src.applications import get_applied_jobs
    if not isinstance(load_job_history(), list):
        return "load_job_history() did not return list"
    if not isinstance(get_applied_jobs(), list):
        return "get_applied_jobs() did not return list"
    return None


def _check_decision_engine() -> Optional[str]:
    from src.profile import get_candidate_profile, get_target_roles
    from src.decision_engine import JobDecisionEngine
    engine = JobDecisionEngine.from_loaders(get_candidate_profile, get_target_roles)
    prob = engine.calculate_success_probability({
        "title": "Backend Engineer",
        "company": "Acme",
        "location": "Dubai UAE",
        "score": 75,
    })
    if not (0 < prob.probability <= 95):
        return f"probability out of range: {prob.probability}"
    return None


def _check_response_intelligence() -> Optional[str]:
    from src.profile import get_candidate_profile, get_target_roles
    from src.decision_engine import JobDecisionEngine
    from src.response_intelligence import create_engine
    engine = JobDecisionEngine.from_loaders(get_candidate_profile, get_target_roles)
    ri = create_engine(engine, state_path=DATA_DIR / "scoring_adjustments.json")
    adj = ri.current_adjustments
    if adj.version < 0:
        return f"invalid adjustments version: {adj.version}"
    return None


def _check_feedback_orchestrator() -> Optional[str]:
    from src.profile import get_candidate_profile, get_target_roles
    from src.decision_engine import JobDecisionEngine
    from src.feedback_loop import FeedbackLoopOrchestrator
    engine = JobDecisionEngine.from_loaders(get_candidate_profile, get_target_roles)
    orch = FeedbackLoopOrchestrator.build(engine, state_dir=DATA_DIR)
    state = orch.cycle_state
    # Verify state loaded without exception and fields are sensible
    if state.total_cycles < 0:
        return f"invalid cycle count: {state.total_cycles}"
    return None


def _check_dashboard() -> Optional[str]:
    from src.dashboard import build_dashboard
    html = build_dashboard()
    if not html or "<html" not in html.lower():
        return "build_dashboard() returned empty or invalid HTML"
    return None


def _check_feedback_state_file() -> Optional[str]:
    adj_file = DATA_DIR / "scoring_adjustments.json"
    cycle_file = DATA_DIR / "cycle_state.json"
    missing = [str(f) for f in [adj_file, cycle_file] if not f.exists()]
    if missing:
        return f"warning: state files not yet created (first run): {missing}"
    return None


def _check_hf_config() -> Optional[str]:
    from src.rico_env import get_rico_env_report
    report = get_rico_env_report()
    if report.ready_for_deepseek:
        return f"DeepSeek configured (provider={report.ai_provider})"
    if report.ready_for_hf:
        return f"HF free mode configured (provider={report.ai_provider})"
    if report.ready_for_openai:
        return f"OpenAI configured (provider={report.ai_provider})"
    return "warning: no AI provider keys found — chat will use keyword fallback only"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

CHECKS: List[tuple[str, Callable[[], Optional[str]]]] = [
    ("imports",                _check_imports),
    ("environment variables",  _check_environment),
    ("data directory writable",_check_data_dir),
    ("database connection",    _check_database),
    ("JSON fallback",          _check_json_fallback),
    ("decision engine",        _check_decision_engine),
    ("response intelligence",  _check_response_intelligence),
    ("feedback orchestrator",  _check_feedback_orchestrator),
    ("dashboard generation",   _check_dashboard),
    ("feedback state files",   _check_feedback_state_file),
    ("AI provider config",     _check_hf_config),
]


def main() -> int:
    print(f"\n{BOLD}System Health Check{RESET}")
    print(f"{'─' * 70}")

    report = HealthReport()
    for name, fn in CHECKS:
        report.record(_run(name, fn))

    print(f"{'─' * 70}")

    if report.all_passed:
        warn_count = len(report.warnings)
        warn_str = f" ({warn_count} warning{'s' if warn_count != 1 else ''})" if warn_count else ""
        print(f"\n{GREEN}{BOLD}✓ All checks passed{RESET}{warn_str}\n")
        return 0

    print(f"\n{RED}{BOLD}✗ {len(report.failed)} check(s) failed:{RESET}")
    for r in report.failed:
        print(f"  • {r.name}: {r.message}")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
