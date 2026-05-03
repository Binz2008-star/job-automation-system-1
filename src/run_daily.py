from src.job_sources import get_jobs
from src.scoring import score_job
from src.message_generator import generate_message
from src.filter import filter_new_jobs
from src.notifier import send_email, format_jobs_email


def main():
    jobs = get_jobs()
    jobs = filter_new_jobs(jobs)
    print(f"Found {len(jobs)} new jobs after filtering")
    matches = []

    for job in jobs:
        score = score_job(job)
        if score >= 40:
            matches.append((job, score))

    matches.sort(key=lambda x: x[1], reverse=True)

    print(f"Found {len(matches)} high-quality matches")

    for job, score in matches[:20]:
        print("\n=== JOB MATCH ===")
        print(job.get("title"), "-", job.get("company"))
        print("Location:", job.get("location"))
        print("Score:", score)
        print("Apply:", job.get("link"))
        print(generate_message(job))

    # Send email notification
    try:
        email_content = format_jobs_email(matches)
        email_subject = "Job Hunting Daily Report" if matches else "No New Jobs Today"
        send_email(email_subject, email_content)
    except Exception as e:
        print(f"Failed to send email notification: {e}")


if __name__ == "__main__":
    main()
