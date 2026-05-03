"""
Test Suite for FeedbackLoopOrchestrator
Comprehensive testing of the new orchestrator architecture.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any

from src.decision_engine_v2 import JobDecisionEngine
from src.feedback_loop import FeedbackLoopOrchestrator, CycleState, CycleResult


def test_orchestrator_basic_functionality() -> Dict[str, Any]:
    """Test basic orchestrator functionality."""
    print("🧪 Testing FeedbackLoopOrchestrator...")

    try:
        # Create temporary directory for test state
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)

            # Create mock decision engine
            def mock_profile_loader() -> Dict[str, Any]:
                return {
                    "experience_years": 8,
                    "skills": {"python": {"weight": 15}, "management": {"weight": 12}},
                    "location": "Dubai"
                }

            def mock_roles_loader() -> List[str]:
                return ["backend engineer", "software engineer", "tech lead"]

            decision_engine = JobDecisionEngine.from_loaders(
                mock_profile_loader,
                mock_roles_loader
            )

            # Build orchestrator
            orchestrator = FeedbackLoopOrchestrator.build(
                decision_engine=decision_engine,
                state_dir=state_dir,
                cooldown=timedelta(minutes=1)  # Short cooldown for testing
            )

            print("✅ Orchestrator built successfully")

            # Test initial state
            state = orchestrator.cycle_state
            assert state.last_run_status == "never"
            assert state.total_cycles == 0
            print("✅ Initial state correct")

            # Test is_due (should be True initially)
            assert orchestrator.is_due() == True
            print("✅ Initial cycle is due")

            # Test engine access
            assert hasattr(orchestrator.engine, 'adjusted_probability')
            print("✅ Engine access working")

            # Create mock data loaders with sufficient data for learning
            def mock_jobs_loader() -> List[Dict[str, Any]]:
                return [
                    {"title": "Senior Backend Engineer", "company": "Tech Corp", "score": 85, "link": "job1", "location": "Dubai"},
                    {"title": "Software Engineer", "company": "Startup Inc", "score": 75, "link": "job2", "location": "Abu Dhabi"},
                    {"title": "Backend Developer", "company": "Big Tech", "score": 80, "link": "job3", "location": "Dubai"},
                    {"title": "Full Stack Engineer", "company": "Medium Corp", "score": 70, "link": "job4", "location": "Sharjah"},
                    {"title": "Python Developer", "company": "Small Startup", "score": 65, "link": "job5", "location": "Dubai"},
                    {"title": "Tech Lead", "company": "Enterprise Co", "score": 90, "link": "job6", "location": "Abu Dhabi"},
                ]

            def mock_apps_loader() -> List[Dict[str, Any]]:
                return [
                    {"title": "Senior Backend Engineer", "company": "Tech Corp", "status": "interview_scheduled", "date_applied": "2024-01-01T10:00:00Z", "date_updated": "2024-01-03T14:00:00Z", "link": "job1"},
                    {"title": "Software Engineer", "company": "Startup Inc", "status": "rejected", "date_applied": "2024-01-02T11:00:00Z", "date_updated": "2024-01-04T16:00:00Z", "link": "job2"},
                    {"title": "Backend Developer", "company": "Big Tech", "status": "offer_extended", "date_applied": "2024-01-03T12:00:00Z", "date_updated": "2024-01-05T16:00:00Z", "link": "job3"},
                    {"title": "Full Stack Engineer", "company": "Medium Corp", "status": "interview_completed", "date_applied": "2024-01-04T13:00:00Z", "date_updated": "2024-01-06T17:00:00Z", "link": "job4"},
                    {"title": "Python Developer", "company": "Small Startup", "status": "screening", "date_applied": "2024-01-05T14:00:00Z", "date_updated": "2024-01-07T18:00:00Z", "link": "job5"},
                    {"title": "Tech Lead", "company": "Enterprise Co", "status": "interview_scheduled", "date_applied": "2024-01-06T15:00:00Z", "date_updated": "2024-01-08T19:00:00Z", "link": "job6"},
                ]

            # Test sync cycle
            result = orchestrator.run_cycle_sync(mock_jobs_loader, mock_apps_loader)
            assert result.status == "success"
            assert result.matched_pairs == 6
            assert result.adjustments_version >= 0
            print(f"✅ Sync cycle completed: {result.matched_pairs} pairs processed")

            # Test state after successful cycle
            state_after = orchestrator.cycle_state
            assert state_after.last_run_status == "success"
            assert state_after.total_cycles == 1
            assert state_after.total_samples_processed == 6
            print("✅ State updated correctly after successful cycle")

            # Test cooldown (should not be due immediately)
            assert orchestrator.is_due() == False
            print("✅ Cooldown working correctly")

            # Test cycle persistence
            # Create new orchestrator instance with same state dir
            orchestrator2 = FeedbackLoopOrchestrator.build(
                decision_engine=decision_engine,
                state_dir=state_dir,
                cooldown=timedelta(minutes=1)
            )

            state_restored = orchestrator2.cycle_state
            assert state_restored.total_cycles == 1
            assert state_restored.last_run_status == "success"
            print("✅ State persistence working")

            return {
                "status": "success",
                "cycles_run": state_after.total_cycles,
                "samples_processed": state_after.total_samples_processed,
                "adjustments_version": result.adjustments_version
            }

    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        return {
            "status": "failed",
            "error": str(e)
        }


def test_orchestrator_error_handling() -> Dict[str, Any]:
    """Test orchestrator error handling."""
    print("\n🧪 Testing Error Handling...")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)

            # Create orchestrator
            decision_engine = JobDecisionEngine.from_loaders(
                lambda: {"experience_years": 5},
                lambda: ["engineer"]
            )

            orchestrator = FeedbackLoopOrchestrator.build(
                decision_engine=decision_engine,
                state_dir=state_dir
            )

            # Test with insufficient data
            def empty_jobs_loader() -> List[Dict[str, Any]]:
                return []

            def empty_apps_loader() -> List[Dict[str, Any]]:
                return []

            result = orchestrator.run_cycle_sync(empty_jobs_loader, empty_apps_loader)
            assert result.status == "failed"
            assert "Insufficient data" in result.error
            print("✅ Error handling for insufficient data working")

            # Test state after failure
            state_after = orchestrator.cycle_state
            assert state_after.last_run_status == "failed"
            assert state_after.last_error is not None
            print("✅ Failure state recorded correctly")

            # Test that failed cycles don't trigger cooldown
            assert orchestrator.is_due() == True
            print("✅ Failed cycles don't trigger cooldown")

            return {"status": "success"}

    except Exception as e:
        print(f"❌ Error handling test failed: {str(e)}")
        return {"status": "failed", "error": str(e)}


def test_orchestrator_skip_logic() -> Dict[str, Any]:
    """Test cycle skip logic."""
    print("\n🧪 Testing Skip Logic...")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)

            decision_engine = JobDecisionEngine.from_loaders(
                lambda: {"experience_years": 5},
                lambda: ["engineer"]
            )

            orchestrator = FeedbackLoopOrchestrator.build(
                decision_engine=decision_engine,
                state_dir=state_dir,
                cooldown=timedelta(hours=1)  # Long cooldown
            )

            # Mock data loaders with sufficient data
            def mock_jobs_loader() -> List[Dict[str, Any]]:
                return [
                    {"title": "Senior Backend Engineer", "company": "Tech Corp", "score": 85, "link": "job1", "location": "Dubai"},
                    {"title": "Software Engineer", "company": "Startup Inc", "score": 75, "link": "job2", "location": "Abu Dhabi"},
                    {"title": "Backend Developer", "company": "Big Tech", "score": 80, "link": "job3", "location": "Dubai"},
                    {"title": "Full Stack Engineer", "company": "Medium Corp", "score": 70, "link": "job4", "location": "Sharjah"},
                    {"title": "Python Developer", "company": "Small Startup", "score": 65, "link": "job5", "location": "Dubai"},
                ]

            def mock_apps_loader() -> List[Dict[str, Any]]:
                return [
                    {"title": "Senior Backend Engineer", "company": "Tech Corp", "status": "interview_scheduled", "date_applied": "2024-01-01T10:00:00Z", "date_updated": "2024-01-03T14:00:00Z", "link": "job1"},
                    {"title": "Software Engineer", "company": "Startup Inc", "status": "rejected", "date_applied": "2024-01-02T11:00:00Z", "date_updated": "2024-01-04T16:00:00Z", "link": "job2"},
                    {"title": "Backend Developer", "company": "Big Tech", "status": "offer_extended", "date_applied": "2024-01-03T12:00:00Z", "date_updated": "2024-01-05T16:00:00Z", "link": "job3"},
                    {"title": "Full Stack Engineer", "company": "Medium Corp", "status": "interview_completed", "date_applied": "2024-01-04T13:00:00Z", "date_updated": "2024-01-06T17:00:00Z", "link": "job4"},
                    {"title": "Python Developer", "company": "Small Startup", "status": "screening", "date_applied": "2024-01-05T14:00:00Z", "date_updated": "2024-01-07T18:00:00Z", "link": "job5"},
                ]

            # Run first cycle
            result1 = orchestrator.run_cycle_sync(mock_jobs_loader, mock_apps_loader)
            assert result1.status == "success"
            print("✅ First cycle completed")

            # Try to run second cycle immediately (should be skipped)
            result2 = orchestrator.run_cycle_sync(mock_jobs_loader, mock_apps_loader)
            assert result2.status == "skipped"
            assert "cooldown" in result2.skipped_reason.lower()
            print("✅ Second cycle skipped due to cooldown")

            # State should not have changed after skip
            state_after = orchestrator.cycle_state
            assert state_after.total_cycles == 1  # Still only 1 cycle
            print("✅ State unchanged after skipped cycle")

            return {"status": "success"}

    except Exception as e:
        print(f"❌ Skip logic test failed: {str(e)}")
        return {"status": "failed", "error": str(e)}


if __name__ == "__main__":
    print("🚀 Starting FeedbackLoopOrchestrator Test Suite")
    print("=" * 60)

    results = []

    # Run tests
    results.append(test_orchestrator_basic_functionality())
    results.append(test_orchestrator_error_handling())
    results.append(test_orchestrator_skip_logic())

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)

    success_count = sum(1 for r in results if r["status"] == "success")
    total_count = len(results)

    for i, result in enumerate(results, 1):
        status = "✅" if result["status"] == "success" else "❌"
        print(f"{status} Test {i}: {result['status']}")
        if result["status"] == "failed":
            print(f"   Error: {result.get('error', 'Unknown')}")

    print(f"\n📈 Overall Success Rate: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")

    if success_count == total_count:
        print("🎉 ALL TESTS PASSED! FeedbackLoopOrchestrator is ready for production.")
    else:
        print("⚠️  Some tests failed. Review the errors above.")

    # Save results
    results_data = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": total_count,
        "passed_tests": success_count,
        "success_rate": success_count / total_count,
        "results": results
    }

    with open("orchestrator_test_results.json", "w") as f:
        json.dump(results_data, f, indent=2)

    print(f"\n📄 Test results saved to: orchestrator_test_results.json")
