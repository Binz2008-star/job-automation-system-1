from src.job_history import get_job_stats, load_job_history
from src.applications import get_application_stats, get_applied_jobs
from src.telegram_bot import send_telegram_message
from datetime import datetime, timedelta
from collections import defaultdict


def generate_weekly_report() -> str:
    """Generate comprehensive weekly job report with application tracking."""
    job_stats = get_job_stats()
    history = load_job_history()
    app_stats = get_application_stats()
    applied_jobs = get_applied_jobs()

    # Filter jobs from last 7 days
    week_ago = datetime.now() - timedelta(days=7)
    week_jobs = [job for job in history if datetime.fromisoformat(job.get('date_found', '')) >= week_ago]

    # Filter applications from last 7 days
    week_applications = [job for job in applied_jobs if datetime.fromisoformat(job.get('date_applied', '')) >= week_ago]

    if not week_jobs and not week_applications:
        return "<b>📊 Weekly Job Report</b>\n\nNo jobs found and no applications in the past 7 days."

    # Calculate weekly statistics
    weekly_total = len(week_jobs)
    weekly_scores = [job.get('score', 0) for job in week_jobs]
    weekly_avg = sum(weekly_scores) / len(weekly_scores) if weekly_scores else 0

    # Count companies and titles for this week
    weekly_companies = defaultdict(int)
    weekly_titles = defaultdict(int)

    for job in week_jobs:
        company = job.get('company', '')
        title = job.get('title', '')
        if company:
            weekly_companies[company] += 1
        if title:
            weekly_titles[title] += 1

    # Get top 10 jobs from this week
    top_week_jobs = sorted(week_jobs, key=lambda x: x.get('score', 0), reverse=True)[:10]

    # Build report
    lines = [
        "<b>📊 Weekly Job Report</b>",
        f"<i>Period: Last 7 days</i>",
        "",
        f"<b>📈 Job Summary</b>",
        f"Total Jobs Found: {weekly_total}",
        f"High-Quality Jobs (≥65): {len([j for j in week_jobs if j.get('score', 0) >= 65])}",
        f"Average Score: {weekly_avg:.1f}",
        ""
    ]

    # Application tracking
    lines.extend([
        f"<b>🎯 Application Tracking</b>",
        f"Jobs Applied This Week: {len(week_applications)}",
        f"Total Applications: {app_stats['total_applied']}",
        f"Interviews Scheduled: {app_stats['interviews_scheduled']}",
        f"Rejections: {app_stats['rejections']}",
        f"Success Rate: {app_stats['success_rate']}%",
        ""
    ])

    # Top companies this week
    if weekly_companies:
        lines.append("<b>🏢 Top Companies This Week</b>")
        for company, count in sorted(weekly_companies.items(), key=lambda x: x[1], reverse=True)[:5]:
            lines.append(f"• {company}: {count} jobs")
        lines.append("")

    # Top job titles this week
    if weekly_titles:
        lines.append("<b>💼 Top Job Titles This Week</b>")
        for title, count in sorted(weekly_titles.items(), key=lambda x: x[1], reverse=True)[:5]:
            lines.append(f"• {title}: {count}")
        lines.append("")

    # Top 10 highest scored jobs
    if top_week_jobs:
        lines.append("<b>⭐ Top 10 Highest Scored Jobs</b>")
        for i, job in enumerate(top_week_jobs, 1):
            title = job.get('title', 'N/A')[:50] + ('...' if len(job.get('title', '')) > 50 else '')
            company = job.get('company', 'N/A')[:30]
            score = job.get('score', 0)
            lines.append(f"{i}. <b>{title}</b>")
            lines.append(f"   🏢 {company} | ⭐ {score}")
        lines.append("")

    # Recent applications
    if week_applications:
        lines.append("<b>📋 Recent Applications</b>")
        for job in week_applications[-5:]:  # Show last 5 applications
            title = job.get('title', 'N/A')[:40] + ('...' if len(job.get('title', '')) > 40 else '')
            company = job.get('company', 'N/A')[:25]
            status = job.get('status', 'applied')
            status_emoji = {"applied": "📝", "interview": "🎯", "rejected": "❌"}.get(status, "📝")
            lines.append(f"{status_emoji} {title} - {company} ({status})")
        lines.append("")

    # Overall statistics
    lines.extend([
        "<b>📋 Overall Statistics (All Time)</b>",
        f"Total Jobs in History: {job_stats['total_jobs']}",
        f"Overall Average Score: {job_stats['average_score']}",
        f"Total Applications: {app_stats['total_applied']}",
        f"Overall Success Rate: {app_stats['success_rate']}%",
        ""
    ])

    # Overall top companies
    if job_stats['top_companies']:
        lines.append("<b>🏆 Top Companies (All Time)</b>")
        for company, count in job_stats['top_companies'][:5]:
            lines.append(f"• {company}: {count} jobs")

    return "\n".join(lines)


def send_weekly_report() -> bool:
    """Send weekly report to Telegram."""
    try:
        report_content = generate_weekly_report()
        return send_telegram_message(report_content)
    except Exception as e:
        print(f"Error sending weekly report: {e}")
        return False


def main():
    """Generate and send weekly report."""
    print("Generating weekly job report...")

    if send_weekly_report():
        print("✅ Weekly report sent successfully")
    else:
        print("❌ Failed to send weekly report")

    # Also print to console for debugging
    print("\n" + "="*50)
    print(generate_weekly_report())
    print("="*50)


if __name__ == "__main__":
    main()
