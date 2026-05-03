from src.job_sources import get_jobs
from src.scoring import score_job, get_profile_explanation
from src.message_generator import generate_message
from src.filter import filter_new_jobs
from src.notifier import send_email, format_jobs_email
from src.telegram_bot import send_telegram_message, format_telegram_jobs
from src.job_history import add_jobs_to_history
from src.apply_assistant import run_apply_assistant
from src.db import init_db, save_job, get_seen_links, is_db_available
from src.profile import get_candidate_profile, get_target_roles
from src.applications import load_applied_jobs
from src.decision_engine import JobDecisionEngine
from src.feedback_loop import FeedbackLoopOrchestrator
from pathlib import Path
import logging


def run_pipeline():
    """Execute the complete job hunting pipeline: fetch, filter, score, notify, learn."""
    # Initialize database if available
    if is_db_available():
        print("🗄️ Database available, initializing...")
        if init_db():
            print("✅ Database ready")
        else:
            print("⚠️ Database initialization failed, using JSON fallback")

    # Initialize feedback loop orchestrator
    print("🧠 Initializing feedback loop orchestrator...")
    try:
        profile = get_candidate_profile()
        target_roles = get_target_roles()
        decision_engine = JobDecisionEngine.from_loaders(lambda: profile, lambda: target_roles)

        # Use project root for state directory
        state_dir = Path(__file__).parent.parent / "data" / "feedback_state"
        state_dir.mkdir(parents=True, exist_ok=True)

        orchestrator = FeedbackLoopOrchestrator.build(
            decision_engine=decision_engine,
            state_dir=state_dir,
            cooldown=None  # Run daily, so no cooldown needed
        )
        print("✅ Feedback loop orchestrator initialized")
    except Exception as e:
        print(f"⚠️ Failed to initialize feedback loop: {e}")
        orchestrator = None

    jobs = get_jobs()
    jobs = filter_new_jobs(jobs)
    print(f"Found {len(jobs)} new jobs after filtering")
    matches = []
    all_scored_jobs = []

    for job in jobs:
        score = score_job(job)
        all_scored_jobs.append((job, score))
        if score >= 65:  # Increased threshold for Roben's profile
            matches.append((job, score))

        # Save to database if available
        if is_db_available():
            save_job(job, score)

    matches.sort(key=lambda x: x[1], reverse=True)

    print(f"Found {len(matches)} high-quality matches")

    for job, score in matches[:20]:
        print("\n=== JOB MATCH ===")
        print(job.get("title"), "-", job.get("company"))
        print("Location:", job.get("location"))
        print("Score:", score)
        print("Why it matches:", get_profile_explanation(job))
        print("Apply:", job.get("link"))
        print(generate_message(job))

    # Save to JSON history (backup)
    add_jobs_to_history(all_scored_jobs)

    # Send email notification (optional)
    try:
        email_content = format_jobs_email(matches)
        email_subject = "Job Hunting Daily Report" if matches else "No New Jobs Today"
        if send_email(email_subject, email_content):
            print("✅ Email notification sent successfully")
        else:
            print("⚠️ Email notification failed (continuing with Telegram)")
    except Exception as e:
        print(f"⚠️ Email notification error: {e} (continuing with Telegram)")

    # Send Telegram notification
    try:
        telegram_content = format_telegram_jobs(matches)
        if send_telegram_message(telegram_content):
            print("✅ Telegram notification sent successfully")
        else:
            print("⚠️ Telegram notification failed")
    except Exception as e:
        print(f"⚠️ Telegram notification error: {e}")

    # Apply assistant for top jobs
    if matches:
        try:
            run_apply_assistant(matches)
        except Exception as e:
            print(f"⚠️ Apply assistant error: {e}")
    else:
        print("No matches for apply assistant.")

    # Run feedback loop learning cycle
    if orchestrator and orchestrator.is_due():
        print("\n🔄 Running feedback loop learning cycle...")
        try:
            # Load jobs and applications for learning
            jobs_for_learning = [job for job, _ in all_scored_jobs]
            applications = load_applied_jobs()

            result = orchestrator.run_cycle_sync(
                jobs_loader=lambda: jobs_for_learning,
                apps_loader=lambda: applications
            )

            if result.status == "success":
                print(f"✅ Feedback loop completed successfully")
                print(f"   - Matched pairs: {result.matched_pairs}")
                print(f"   - Adjustments version: {result.adjustments_version}")
                print(f"   - Duration: {result.duration_seconds:.2f}s")
            elif result.status == "skipped":
                print(f"⏭️ Feedback loop skipped: {result.skipped_reason}")
            else:
                print(f"❌ Feedback loop failed: {result.error}")

        except Exception as e:
            print(f"❌ Feedback loop error: {e}")
            print("   Continuing pipeline - feedback loop failures are non-critical")
    else:
        print("\n🔄 Feedback loop not due or not available")


def main():
    run_pipeline()


if __name__ == "__main__":
    main()
