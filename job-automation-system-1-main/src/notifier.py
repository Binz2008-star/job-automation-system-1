import smtplib
import ssl
import os
from email.message import EmailMessage
from typing import List, Dict, Tuple
from dotenv import load_dotenv

load_dotenv()


def send_email(subject: str, content: str) -> bool:
    """Send email using SMTP (Gmail). Returns True if successful, False otherwise."""
    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_PASS", "").replace(" ", "").strip()
    email_to = os.getenv("EMAIL_TO")

    if not all([email_user, email_pass, email_to]):
        print("Error: EMAIL_USER, EMAIL_PASS, and EMAIL_TO must be set in .env file")
        return False

    try:
        msg = EmailMessage()
        msg.set_content(content)
        msg["Subject"] = subject
        msg["From"] = email_user
        msg["To"] = email_to

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(email_user, email_pass)
            server.send_message(msg)

        print("Email sent successfully")
        return True
    except smtplib.SMTPAuthenticationError:
        print("Error: Email authentication failed. Check EMAIL_USER and EMAIL_PASS")
        return False
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def format_jobs_email(jobs_with_scores: List[Tuple[Dict, int]]) -> str:
    """Format jobs into clean text email output."""
    if not jobs_with_scores:
        return "No new jobs found today."

    lines = [
        "Job Hunting Daily Report",
        "=" * 40,
        f"Found {len(jobs_with_scores)} high-quality job matches",
        ""
    ]

    for job, score in jobs_with_scores[:10]:
        lines.extend([
            f"Title: {job.get('title', 'N/A')}",
            f"Company: {job.get('company', 'N/A')}",
            f"Location: {job.get('location', 'N/A')}",
            f"Score: {score}",
            f"Link: {job.get('link', 'N/A')}",
            ""
        ])

    lines.append("=" * 40)
    return "\n".join(lines)
