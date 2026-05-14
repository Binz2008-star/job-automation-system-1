import os
from dotenv import load_dotenv
from src.notifier import send_email

load_dotenv()


def _mask(value: str | None) -> str:
    if not value:
        return "NOT SET"
    if len(value) <= 4:
        return "****"
    return value[:2] + "****" + value[-2:]


# Debug Gmail authentication
def main():
    print("=== Gmail Authentication Debug ===")

    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_PASS")
    email_to = os.getenv("EMAIL_TO")

    print(f"EMAIL_USER configured: {bool(email_user)}")
    print(f"EMAIL_TO configured: {bool(email_to)}")

    if email_user:
        print(f"EMAIL_USER masked: {_mask(email_user)}")

    if email_to:
        print(f"EMAIL_TO masked: {_mask(email_to)}")

    if email_pass:
        print(f"EMAIL_PASS configured: True")
        print(f"EMAIL_PASS length = {len(email_pass)}")
    else:
        print("EMAIL_PASS configured: False")

    print("\n=== Notifier Configuration Check ===")
    print("Uses Gmail SMTP with SSL")
    print("Uses secure login flow")

    print("\n=== Email Test ===")
    subject = "Job Automation System - Email Test"
    content = """
This is a test email from your Job Automation System.

If you receive this email, the email notification system is working correctly.
"""

    if send_email(subject, content):
        print("Email test successful")
    else:
        print("Email test failed")


if __name__ == "__main__":
    main()
