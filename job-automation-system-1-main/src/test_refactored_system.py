"""
Test Suite for Refactored Job Search System
Comprehensive testing of decision engine, response intelligence, and feedback loop.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any

from src.db import get_top_jobs, get_application_stats, is_db_available
from src.applications import get_applied_jobs
from src.profile import get_candidate_profile, get_target_roles
from src.decision_engine import JobDecisionEngine, generate_decision_insights
from src.response_intelligence import ResponseIntelligenceEngine, create_engine
from src.feedback_loop import FeedbackLoopSystem, create_feedback_loop_system


def test_decision_engine() -> Dict[str, Any]:
    """Test the refactored decision engine."""
    print("🧪 Testing Decision Engine V2...")

    try:
        # Create engine with dependency injection
        engine = JobDecisionEngine.from_loaders(get_candidate_profile, get_target_roles)

        # Load test data
        jobs = get_top_jobs(10) if is_db_available() else []
        applications = get_applied_jobs()
        app_stats = get_application_stats()

        if not jobs:
            # Create mock job data for testing
            jobs = [
                {
                    "title": "Senior Operations Manager",
                    "company": "Test Company",
                    "location": "Dubai, UAE",
                    "link": "https://example.com/job1",
                    "score": 75,
                    "date_found": datetime.now().isoformat(),
                },
                {
                    "title": "Executive Assistant",
                    "company": "Another Corp",
                    "location": "Abu Dhabi, UAE",
                    "link": "https://example.com/job2",
                    "score": 85,
                    "date_found": datetime.now().isoformat(),
                }
            ]

        # Test success probability calculation
        if jobs:
            prob_result = engine.calculate_success_probability(jobs[0])
            print(f"✅ Success probability calculated: {prob_result.probability}%")

        # Test market trend analysis
        trends = engine.analyze_market_trends(jobs, applications)
        print(f"✅ Market trends analyzed: {trends.market_overview.get('total_jobs', 0)} jobs")

        # Test application strategy
        strategy = engine.generate_application_strategy(jobs, applications, app_stats)
        print(f"✅ Application strategy generated: {strategy.optimal_daily_applications} daily apps")

        # Test insights generation
        insights = generate_decision_insights(jobs, applications, app_stats, engine)
        print(f"✅ Decision insights generated: {len(insights)} sections")

        return {
            "status": "success",
            "engine_type": "DecisionEngineV2",
            "tests_passed": 4,
            "data_points": len(jobs) + len(applications),
        }

    except Exception as e:
        print(f"❌ Decision engine test failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "engine_type": "DecisionEngineV2",
        }


def test_response_intelligence() -> Dict[str, Any]:
    """Test the response intelligence layer."""
    print("\n🧪 Testing Response Intelligence Layer...")

    try:
        # Create decision engine first
        decision_engine = JobDecisionEngine.from_loaders(get_candidate_profile, get_target_roles)

        # Create response intelligence engine
        response_engine = create_engine(decision_engine)

        # Load test data
        applications = get_applied_jobs()

        if not applications:
            # Create mock application data for testing
            applications = [
                {
                    "title": "Test Job 1",
                    "company": "Test Company",
                    "status": "applied",
                    "date_applied": (datetime.now() - timedelta(days=5)).isoformat(),
                    "date_updated": (datetime.now() - timedelta(days=5)).isoformat(),
                    "link": "https://example.com/job1",
                },
                {
                    "title": "Test Job 2",
                    "company": "Another Corp",
                    "status": "interview",
                    "date_applied": (datetime.now() - timedelta(days=10)).isoformat(),
                    "date_updated": (datetime.now() - timedelta(days=3)).isoformat(),
                    "link": "https://example.com/job2",
                }
            ]

        # Test response pattern analysis
        patterns = response_engine.analyze_response_patterns(applications)
        print(f"✅ Response patterns analyzed: {patterns.get('total_applications', 0)} applications")

        # Test follow-up intelligence
        follow_up = response_engine.generate_follow_up_intelligence(applications)
        print(f"✅ Follow-up actions generated: {follow_up.get('total_actions_needed', 0)} actions")

        return {
            "status": "success",
            "engine_type": "ResponseIntelligence",
            "tests_passed": 2,
            "applications_analyzed": len(applications),
        }

    except Exception as e:
        print(f"❌ Response intelligence test failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "engine_type": "ResponseIntelligence",
        }


def test_feedback_loop() -> Dict[str, Any]:
    """Test the feedback loop system."""
    print("\n🧪 Testing Feedback Loop System...")

    try:
        # Create decision engine
        decision_engine = JobDecisionEngine.from_loaders(get_candidate_profile, get_target_roles)

        # Create feedback loop system
        feedback_system = create_feedback_loop_system(decision_engine)

        # Test learning cycle timing
        should_run = feedback_system.should_run_learning_cycle()
        print(f"✅ Learning cycle check: {'should run' if should_run else 'not needed'}")

        # Get learning status
        status = feedback_system.get_learning_status()
        print(f"✅ Learning status retrieved: next cycle {status.get('next_learning_cycle', 'unknown')}")

        # Test complete cycle (with limited data to avoid long execution)
        print("🔄 Running complete feedback loop cycle...")
        cycle_results = feedback_system.run_complete_cycle()

        if "error" not in cycle_results:
            print(f"✅ Feedback loop cycle completed successfully")
            cycle_summary = cycle_results.get("cycle_summary", {})
            print(f"   - Success rate: {cycle_summary.get('key_metrics', {}).get('current_success_rate', 'N/A')}")
            print(f"   - Insights: {cycle_summary.get('key_metrics', {}).get('insights_generated', 0)}")
            print(f"   - Follow-ups: {cycle_summary.get('key_metrics', {}).get('follow_up_actions_needed', 0)}")
        else:
            print(f"⚠️ Feedback loop completed with issues: {cycle_results.get('error')}")

        return {
            "status": "success" if "error" not in cycle_results else "partial",
            "engine_type": "FeedbackLoop",
            "cycle_completed": "error" not in cycle_results,
            "learning_status": status,
        }

    except Exception as e:
        print(f"❌ Feedback loop test failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "engine_type": "FeedbackLoop",
        }


def test_dashboard_integration() -> Dict[str, Any]:
    """Test dashboard integration with refactored components."""
    print("\n🧪 Testing Dashboard Integration...")

    try:
        # Import and test dashboard
        from src.dashboard_v2 import build_refactored_dashboard

        # Generate dashboard
        html_content = build_refactored_dashboard()

        # Check if HTML was generated
        if html_content and len(html_content) > 1000:
            print("✅ Dashboard HTML generated successfully")

            # Check for key components
            has_decision_engine = "Decision Engine V2" in html_content
            has_response_intel = "Response Intelligence" in html_content
            has_clean_arch = "dependency injection" in html_content

            print(f"✅ Dashboard components check:")
            print(f"   - Decision Engine V2: {'✓' if has_decision_engine else '✗'}")
            print(f"   - Response Intelligence: {'✓' if has_response_intel else '✗'}")
            print(f"   - Clean Architecture: {'✓' if has_clean_arch else '✗'}")

            return {
                "status": "success",
                "html_length": len(html_content),
                "components_present": {
                    "decision_engine": has_decision_engine,
                    "response_intelligence": has_response_intel,
                    "clean_architecture": has_clean_arch,
                },
            }
        else:
            return {
                "status": "failed",
                "error": "Dashboard HTML too short or empty",
                "html_length": len(html_content) if html_content else 0,
            }

    except Exception as e:
        print(f"❌ Dashboard integration test failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
        }


def run_comprehensive_test() -> Dict[str, Any]:
    """Run comprehensive test suite for refactored system."""
    print("🚀 Starting Comprehensive Test Suite for Refactored Job Search System")
    print("=" * 70)

    # Run all tests
    test_results = {
        "decision_engine": test_decision_engine(),
        "response_intelligence": test_response_intelligence(),
        "feedback_loop": test_feedback_loop(),
        "dashboard_integration": test_dashboard_integration(),
    }

    # Calculate overall results
    total_tests = len(test_results)
    successful_tests = sum(1 for result in test_results.values() if result.get("status") == "success")

    print("\n" + "=" * 70)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 70)

    for test_name, result in test_results.items():
        status = result.get("status", "unknown")
        icon = "✅" if status == "success" else "⚠️" if status == "partial" else "❌"
        print(f"{icon} {test_name.replace('_', ' ').title()}: {status}")

        if "error" in result:
            print(f"   Error: {result['error']}")

    print(f"\n📈 Overall Success Rate: {successful_tests}/{total_tests} ({successful_tests/total_tests*100:.1f}%)")

    if successful_tests == total_tests:
        print("🎉 ALL TESTS PASSED! System is ready for production.")
    elif successful_tests >= total_tests * 0.75:
        print("✅ Most tests passed. System is mostly functional.")
    else:
        print("⚠️ Several tests failed. Review issues before deployment.")

    return {
        "test_summary": {
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "success_rate": successful_tests / total_tests,
            "timestamp": datetime.now().isoformat(),
        },
        "detailed_results": test_results,
    }


if __name__ == "__main__":
    # Run comprehensive test suite
    results = run_comprehensive_test()

    # Save test results
    results_file = Path("test_results.json")
    try:
        with results_file.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n📄 Test results saved to: {results_file}")
    except Exception as e:
        print(f"\n⚠️ Could not save test results: {e}")
