from src.job_sources import get_jobs
from src.scoring import score_job
from src.message_generator import generate_message

def main():
    jobs = get_jobs()
    for job in jobs:
        score = score_job(job)
        if score >= 50:
            print("\n=== JOB ===")
            print(job["title"], "-", job["company"])
            print("Score:", score)
            print(generate_message(job))

if __name__ == "__main__":
    main()