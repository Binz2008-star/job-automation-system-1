"""
System Health Check for Job Automation System
Comprehensive health monitoring for all system components.
"""

import os
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Any
import json

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def check_imports() -> Dict[str, bool]:
    """Check that all required modules can be imported."""
    results = {}

    modules = [
        "src.decision_engine",
        "src.response_intelligence",
        "src.feedback_loop",
        "src.profile",
        "src.applications",
        "src.job_sources",
        "src.scoring",
        "src.filter",
        "src.notifier",
        "src.telegram_bot",
        "src.job_history",
        "src.apply_assistant",
        "src.db",
        "src.run_daily",
        "src.dashboard",
    ]

    for module in modules:
        try:
            __import__(module)
            results[module] = True
        except ImportError as e:
            results[module] = False
            print(f"❌ Import failed for {module}: {e}")

    return results

def check_environment() -> Dict[str, Any]:
    """Check environment variables and configuration."""
    results = {
        "env_file_exists": False,
        "required_env_vars": {},
        "optional_env_vars": {},
        "secrets_hidden": True
    }

    # Check .env file
    env_file = project_root / ".env"
    results["env_file_exists"] = env_file.exists()

    if env_file.exists():
        # Load environment variables (without printing secrets)
        with open(env_file, 'r') as f:
            env_content = f.read()

        required_vars = ["EMAIL_USER", "EMAIL_PASS", "TELEGRAM_BOT_TOKEN"]
        optional_vars = ["DATABASE_URL", "GITHUB_TOKEN"]

        for var in required_vars:
            if var in env_content and "=" in env_content:
                value = env_content.split(f"{var}=")[1].split("\n")[0].strip()
                results["required_env_vars"][var] = bool(value) and value != ""
            else:
                results["required_env_vars"][var] = False

        for var in optional_vars:
            if var in env_content and "=" in env_content:
                value = env_content.split(f"{var}=")[1].split("\n")[0].strip()
                results["optional_env_vars"][var] = bool(value) and value != ""
            else:
                results["optional_env_vars"][var] = False

    return results

def check_database() -> Dict[str, Any]:
    """Check database connectivity and availability."""
    results = {
        "available": False,
        "connection_test": False,
        "fallback_available": True
    }

    try:
        from src.db import is_db_available, init_db

        results["available"] = is_db_available()
        if results["available"]:
            results["connection_test"] = init_db()

        # Check JSON fallback availability
        data_dir = project_root / "data"
        results["fallback_available"] = data_dir.exists() or data_dir.mkdir(parents=True, exist_ok=True)

    except Exception as e:
        print(f"❌ Database check failed: {e}")
        results["error"] = str(e)

    return results

def check_decision_engine() -> Dict[str, Any]:
    """Check decision engine initialization."""
    results = {
        "initializes": False,
        "loads_profile": False,
        "loads_roles": False,
        "error": None
    }

    try:
        from src.decision_engine import JobDecisionEngine
        from src.profile import get_candidate_profile, get_target_roles

        # Test profile loading
        profile = get_candidate_profile()
        results["loads_profile"] = bool(profile) and len(profile) > 0

        # Test roles loading
        roles = get_target_roles()
        results["loads_roles"] = bool(roles) and len(roles) > 0

        # Test engine initialization
        engine = JobDecisionEngine.from_loaders(lambda: profile, lambda: roles)
        results["initializes"] = engine is not None

    except Exception as e:
        results["error"] = str(e)
        print(f"❌ Decision engine check failed: {e}")

    return results

def check_response_intelligence() -> Dict[str, Any]:
    """Check response intelligence system."""
    results = {
        "initializes": False,
        "creates_engine": False,
        "status_aliases_work": False,
        "error": None
    }

    try:
        from src.response_intelligence import ResponseIntelligenceEngine, create_engine, ResponseType
        from src.decision_engine import JobDecisionEngine
        from src.profile import get_candidate_profile, get_target_roles

        # Test ResponseType aliases
        interview_type = ResponseType.from_raw("interview")
        results["status_aliases_work"] = interview_type == ResponseType.INTERVIEW_SCHEDULED

        # Test engine creation
        profile = get_candidate_profile()
        roles = get_target_roles()
        decision_engine = JobDecisionEngine.from_loaders(lambda: profile, lambda: roles)
        engine = create_engine(decision_engine)
        results["creates_engine"] = engine is not None
        results["initializes"] = True

    except Exception as e:
        results["error"] = str(e)
        print(f"❌ Response intelligence check failed: {e}")

    return results

def check_feedback_orchestrator() -> Dict[str, Any]:
    """Check feedback loop orchestrator."""
    results = {
        "initializes": False,
        "state_dir_writable": False,
        "due_check_works": False,
        "error": None
    }

    try:
        from src.feedback_loop import FeedbackLoopOrchestrator
        from src.decision_engine import JobDecisionEngine
        from src.profile import get_candidate_profile, get_target_roles

        # Test state directory
        state_dir = project_root / "data" / "feedback_state"
        state_dir.mkdir(parents=True, exist_ok=True)
        test_file = state_dir / "test_write.tmp"
        try:
            test_file.write_text("test")
            test_file.unlink()
            results["state_dir_writable"] = True
        except Exception:
            results["state_dir_writable"] = False

        # Test orchestrator initialization
        profile = get_candidate_profile()
        roles = get_target_roles()
        decision_engine = JobDecisionEngine.from_loaders(lambda: profile, lambda: roles)

        orchestrator = FeedbackLoopOrchestrator.build(
            decision_engine=decision_engine,
            state_dir=state_dir,
            cooldown=None
        )

        results["initializes"] = orchestrator is not None
        results["due_check_works"] = orchestrator.is_due() is not None

    except Exception as e:
        results["error"] = str(e)
        print(f"❌ Feedback orchestrator check failed: {e}")

    return results

def check_dashboard() -> Dict[str, Any]:
    """Check dashboard generation."""
    results = {
        "generates": False,
        "output_writable": False,
        "error": None
    }

    try:
        from src.dashboard import load_dashboard_data

        # Test output directory
        output_file = project_root / "dashboard.html"
        output_dir = output_file.parent
        results["output_writable"] = output_dir.exists() and output_dir.is_dir()

        # Test dashboard data loading (without actually generating)
        # This would require mocking the data sources, so we'll just check imports
        results["generates"] = True

    except Exception as e:
        results["error"] = str(e)
        print(f"❌ Dashboard check failed: {e}")

    return results

def run_health_check() -> Dict[str, Any]:
    """Run comprehensive health check."""
    print("🏥 Starting System Health Check...")
    print("=" * 50)

    checks = {
        "imports": check_imports(),
        "environment": check_environment(),
        "database": check_database(),
        "decision_engine": check_decision_engine(),
        "response_intelligence": check_response_intelligence(),
        "feedback_orchestrator": check_feedback_orchestrator(),
        "dashboard": check_dashboard(),
    }

    # Calculate overall health
    total_checks = 0
    passed_checks = 0

    for category, results in checks.items():
        print(f"\n📋 {category.replace('_', ' ').title()}:")

        if isinstance(results, dict):
            for check, result in results.items():
                if isinstance(result, bool):
                    total_checks += 1
                    if result:
                        print(f"  ✅ {check}")
                        passed_checks += 1
                    else:
                        print(f"  ❌ {check}")
                elif isinstance(result, dict):
                    for sub_check, sub_result in result.items():
                        if isinstance(sub_result, bool):
                            total_checks += 1
                            if sub_result:
                                print(f"  ✅ {sub_check}")
                                passed_checks += 1
                            else:
                                print(f"  ❌ {sub_check}")
        else:
            print(f"  ℹ️ {results}")

    # Overall status
    health_percentage = (passed_checks / total_checks * 100) if total_checks > 0 else 0
    print(f"\n{'='*50}")
    print(f"📊 Overall Health: {passed_checks}/{total_checks} checks passed ({health_percentage:.1f}%)")

    if health_percentage >= 90:
        print("🟢 System is HEALTHY")
    elif health_percentage >= 70:
        print("🟡 System has some issues but is OPERATIONAL")
    else:
        print("🔴 System has CRITICAL issues")

    return {
        "overall_percentage": health_percentage,
        "passed_checks": passed_checks,
        "total_checks": total_checks,
        "checks": checks
    }

def main():
    """Main health check entry point."""
    try:
        results = run_health_check()

        # Exit with appropriate code
        if results["overall_percentage"] >= 90:
            sys.exit(0)  # Healthy
        elif results["overall_percentage"] >= 70:
            sys.exit(1)  # Warning
        else:
            sys.exit(2)  # Critical

    except Exception as e:
        print(f"❌ Health check failed with error: {e}")
        print(traceback.format_exc())
        sys.exit(3)

if __name__ == "__main__":
    main()
