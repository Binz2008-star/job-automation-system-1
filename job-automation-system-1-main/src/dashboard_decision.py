"""
Job Search Decision Engine Dashboard
High-end AI-powered dashboard with predictive analytics and strategic insights.
Features decision scoring, competitive analysis, and real-time recommendations.

Run:
    python src/dashboard_decision.py
Then open:
    dashboard.html
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from html import escape
from typing import Dict, List, Any

from src.db import get_top_jobs, get_application_stats, is_db_available, get_seen_links
from src.job_history import load_job_history
from src.applications import get_applied_jobs
from src.decision_engine import JobDecisionEngine, generate_decision_insights

BASE_DIR = Path(__file__).resolve().parent.parent
JOB_HISTORY_FILE = BASE_DIR / "data" / "job_history.json"
APPLIED_JOBS_FILE = BASE_DIR / "data" / "applied_jobs.json"
OUTPUT_FILE = BASE_DIR / "dashboard.html"


def load_json(path: Path, default):
    """Load JSON file with fallback."""
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def parse_dt(value: str | None):
    """Parse datetime string."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def score_band(score: int | float) -> str:
    """Get score quality band."""
    if score >= 85:
        return "Very High"
    elif score >= 75:
        return "High"
    elif score >= 65:
        return "High quality"
    elif score >= 40:
        return "Medium"
    return "Low"


def pct(part: int, total: int) -> str:
    """Calculate percentage."""
    return f"{(part / total * 100):.1f}%" if total else "0.0%"


def get_confidence_emoji(score: int) -> str:
    """Get confidence emoji for score."""
    if score >= 85:
        return "⭐⭐⭐⭐⭐"
    elif score >= 75:
        return "⭐⭐⭐⭐"
    elif score >= 65:
        return "⭐⭐⭐"
    elif score >= 40:
        return "⭐⭐"
    return "⭐"


def load_dashboard_data() -> Dict[str, Any]:
    """Load dashboard data from database with JSON fallback."""
    # Try database first
    if is_db_available():
        try:
            # Get jobs from database
            top_jobs = get_top_jobs(50)  # Get more jobs for dashboard
            jobs = []

            # Convert database format to dashboard format
            for job in top_jobs:
                jobs.append({
                    'title': job.get('title', ''),
                    'company': job.get('company', ''),
                    'location': job.get('location', ''),
                    'link': job.get('link', ''),
                    'score': job.get('score', 0),
                    'date_found': job.get('date_found', ''),
                    'profile_explanation': job.get('match_reason', ''),
                    'source': job.get('source', 'jobspy')
                })

            # Get application stats from database
            app_stats = get_application_stats()
            applications = get_applied_jobs()

            return {
                'jobs': jobs,
                'applications': applications,
                'app_stats': app_stats,
                'source': 'database'
            }

        except Exception as e:
            print(f"⚠️ Database dashboard failed, using JSON fallback: {e}")

    # Fallback to JSON files
    jobs = load_json(JOB_HISTORY_FILE, [])
    applications = load_json(APPLIED_JOBS_FILE, [])

    # Calculate application stats manually
    status_counts = Counter(a.get("status", "unknown") for a in applications)
    app_stats = {
        'total_applied': len(applications),
        'status_breakdown': dict(status_counts),
        'interviews_scheduled': status_counts.get("interview", 0),
        'rejections': status_counts.get("rejected", 0),
        'pending': status_counts.get("applied", 0),
        'success_rate': (status_counts.get("interview", 0) / len(applications) * 100) if applications else 0.0
    }

    return {
        'jobs': jobs,
        'applications': applications,
        'app_stats': app_stats,
        'source': 'json'
    }


def build_decision_dashboard() -> str:
    """Build AI-powered decision engine dashboard."""
    data = load_dashboard_data()
    jobs = data['jobs']
    applications = data['applications']
    app_stats = data['app_stats']
    data_source = data['source']

    # Generate decision engine insights
    decision_insights = generate_decision_insights()
    market_analysis = decision_insights.get('market_analysis', {})
    application_strategy = decision_insights.get('application_strategy', {})
    competitive_analysis = decision_insights.get('competitive_analysis', {})
    candidate_profile = decision_insights.get('candidate_profile', {})

    now = datetime.now()
    week_ago = now - timedelta(days=7)

    scores = [int(j.get("score") or 0) for j in jobs]
    high_quality = [j for j in jobs if int(j.get("score") or 0) >= 65]
    very_high_quality = [j for j in jobs if int(j.get("score") or 0) >= 85]
    week_jobs = [j for j in jobs if (parse_dt(j.get("date_found")) or datetime.min) >= week_ago]

    applied_count = len(applications)
    status_counts = Counter(a.get("status", "unknown") for a in applications)
    interviews = status_counts.get("interview", 0)
    rejections = status_counts.get("rejected", 0)
    pending = status_counts.get("applied", 0)
    offers = status_counts.get("offer", 0)

    avg_score = mean(scores) if scores else 0
    max_score = max(scores) if scores else 0

    company_counts = Counter(j.get("company") or "Unknown" for j in jobs)
    location_counts = Counter(j.get("location") or "Unknown" for j in jobs)
    band_counts = Counter(score_band(int(j.get("score") or 0)) for j in jobs)

    # Get prioritized jobs from decision engine
    prioritized_jobs = application_strategy.get('prioritized_jobs', [])
    top_jobs = sorted(jobs, key=lambda j: int(j.get("score") or 0), reverse=True)[:15]
    recent_jobs = sorted(jobs, key=lambda j: j.get("date_found", ""), reverse=True)[:15]
    recent_applications = sorted(applications, key=lambda a: a.get("date_applied", ""), reverse=True)[:10]

    max_company_count = max(company_counts.values()) if company_counts else 1
    max_location_count = max(location_counts.values()) if location_counts else 1

    def stat_card(label, value, sub="", color=""):
        color_style = f"color: {color};" if color else ""
        return f"""
        <div class="card stat-card">
            <div class="stat-label">{escape(label)}</div>
            <div class="stat-value" style="{color_style}">{escape(str(value))}</div>
            <div class="stat-sub">{escape(sub)}</div>
        </div>
        """

    def bar(label, value, max_value, color=""):
        width = int((value / max_value) * 100) if max_value else 0
        bar_color = color or "linear-gradient(90deg,var(--accent),var(--good))"
        return f"""
        <div class="bar-row">
            <div class="bar-head"><span>{escape(str(label))}</span><strong>{value}</strong></div>
            <div class="bar-bg"><div class="bar-fill" style="width:{width}%; background:{bar_color}"></div></div>
        </div>
        """

    def decision_job_row(job_data, show_insights=False):
        if isinstance(job_data, dict) and 'job' in job_data:
            # Decision engine format
            job = job_data['job']
            priority_score = job_data.get('priority_score', 0)
            success_prob = job_data.get('success_probability', 0)
            recommendation = job_data.get('recommendation', '')
            apply_today = job_data.get('apply_today', False)
        else:
            # Regular job format
            job = job_data
            priority_score = job.get('score', 0)
            success_prob = 0
            recommendation = ''
            apply_today = False

        title = escape(job.get("title") or "Untitled")
        company = escape(job.get("company") or "Unknown")
        location = escape(job.get("location") or "Unknown")
        score = int(job.get("score") or 0)
        link = escape(job.get("link") or "#")
        band = score_band(score)
        confidence = get_confidence_emoji(score)
        explanation = escape(job.get("profile_explanation", ""))[:100] + "..." if job.get("profile_explanation") else ""

        apply_indicator = "🎯" if apply_today else ""

        return f"""
        <tr>
            <td><a href="{link}" target="_blank">{title}</a><div class="muted">{company}</div></td>
            <td>{location}</td>
            <td><span class="pill {band.lower().replace(' ', '-')}">{band}</span></td>
            <td class="score">{score} {confidence}</td>
            {"<td class='priority'>" + str(priority_score) + "</td>" if show_insights else ""}
            {"<td class='success-rate'>" + str(success_prob) + "%</td>" if show_insights else ""}
            {"<td class='recommendation'>" + escape(recommendation[:50]) + "..." + "</td>" if show_insights else ""}
            {"<td class='explanation'>" + explanation + "</td>" if explanation else ""}
            {"<td class='apply-today'>" + apply_indicator + "</td>" if apply_today else ""}
        </tr>
        """

    def application_row(app):
        title = escape(app.get("title") or "Untitled")
        company = escape(app.get("company") or "Unknown")
        status = app.get("status", "unknown")
        applied_date = parse_dt(app.get("date_applied"))
        date_str = applied_date.strftime("%Y-%m-%d") if applied_date else "Unknown"
        notes = escape(app.get("notes", ""))[:50] + "..." if app.get("notes") else ""

        status_colors = {
            "saved": "var(--low)",
            "opened": "var(--mid)",
            "applied": "var(--accent)",
            "interview": "var(--good)",
            "offer": "#10b981",
            "rejected": "var(--danger)"
        }
        color = status_colors.get(status, "var(--muted)")

        return f"""
        <tr>
            <td><strong>{title}</strong><div class="muted">{company}</div></td>
            <td><span class="pill" style="background:{color}; color:white">{status.title()}</span></td>
            <td>{date_str}</td>
            <td class="muted">{notes}</td>
        </tr>
        """

    def market_insight_card(title, value, trend="", color=""):
        trend_icon = "📈" if trend == "up" else "📉" if trend == "down" else "➡️"
        return f"""
        <div class="card insight-card">
            <div class="insight-title">{escape(title)} {trend_icon}</div>
            <div class="insight-value" style="color: {color}">{escape(str(value))}</div>
            <div class="insight-trend">{trend}</div>
        </div>
        """

    def strategy_recommendation(rec):
        return f"""
        <div class="strategy-item">
            <div class="strategy-bullet">💡</div>
            <div class="strategy-text">{escape(rec)}</div>
        </div>
        """

    # Market health color
    market_health = market_analysis.get('market_health', {})
    health_score = market_health.get('health_score', 0)
    if health_score >= 80:
        health_color = "#10b981"
    elif health_score >= 60:
        health_color = "#22c55e"
    elif health_score >= 40:
        health_color = "#f59e0b"
    else:
        health_color = "#ef4444"

    # Pre-calculate all dynamic content to avoid generator issues
    market_recs = ''.join(strategy_recommendation(rec) for rec in market_analysis.get('recommendations', [])[:3])
    app_recs = ''.join(strategy_recommendation(rec) for rec in application_strategy.get('strategy_recommendations', [])[:3])
    competitive_advantages = ''.join(strategy_recommendation(f"✓ {adv}" for adv in candidate_profile.get('competitive_advantages', [])[:3]))
    priority_jobs_html = ''.join(decision_job_row(job, show_insights=True) for job in prioritized_jobs[:10])
    company_bars = ''.join(bar(company, count, max_company_count) for company, count in company_counts.most_common(10))
    location_bars = ''.join(bar(location, count, max_location_count) for location, count in location_counts.most_common(10))
    quality_bars = ''.join(bar(label, band_counts.get(label, 0), max(band_counts.values()) if band_counts else 1,
                "linear-gradient(90deg,#10b981,#22c55e)" if "Very High" in label or "High" in label else "")
                for label in ['Very High','High','High quality','Medium','Low'])
    status_bars = ''.join(bar(status.title(), count, max(status_counts.values()) if status_counts else 1)
                for status, count in status_counts.items()) or '<div class="muted">No applications tracked yet.</div>'

    # Recent applications and jobs
    recent_apps_html = ''.join(application_row(app) for app in recent_applications)
    recent_jobs_html = ''.join(decision_job_row(job) for job in recent_jobs)

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>🧠 Job Search Decision Engine</title>
<style>
:root {{
  --bg:#0f172a; --panel:#111827; --card:#1f2937; --muted:#9ca3af;
  --text:#f9fafb; --line:#374151; --accent:#38bdf8; --good:#22c55e;
  --mid:#f59e0b; --low:#64748b; --danger:#ef4444; --ai:#8b5cf6;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Inter, Arial, sans-serif; background:linear-gradient(135deg,#020617,#111827); color:var(--text); }}
.container {{ max-width:1800px; margin:0 auto; padding:32px; }}
.header {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; margin-bottom:28px; }}
h1 {{ margin:0; font-size:38px; letter-spacing:-0.04em; background:linear-gradient(135deg,var(--accent),var(--ai)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
.subtitle {{ color:var(--muted); margin-top:8px; line-height:1.5; font-size:16px; }}
.badge {{ border:1px solid var(--line); padding:10px 14px; border-radius:999px; color:#d1d5db; background:rgba(255,255,255,0.04); white-space:nowrap; }}
.source-badge {{ background:rgba(34,197,94,.16); color:#86efac; border-color:#22c55e; }}
.ai-badge {{ background:rgba(139,92,246,.16); color:#a78bfa; border-color:#8b5cf6; }}
.grid {{ display:grid; gap:16px; }}
.stats {{ grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); margin-bottom:16px; }}
.four {{ grid-template-columns:repeat(4,1fr); }}
.three {{ grid-template-columns:repeat(3,1fr); }}
.two {{ grid-template-columns:1fr 1fr; margin-bottom:16px; }}
.card {{ background:rgba(31,41,55,0.78); border:1px solid var(--line); border-radius:20px; padding:20px; box-shadow:0 20px 45px rgba(0,0,0,.22); }}
.card:hover {{ transform:translateY(-2px); box-shadow:0 25px 50px rgba(0,0,0,.3); transition:all 0.3s ease; }}
.insight-card {{ background:rgba(31,41,55,0.9); border:1px solid var(--accent); border-radius:16px; padding:16px; text-align:center; }}
.ai-card {{ background:rgba(139,92,246,.08); border:1px solid var(--ai); border-radius:16px; padding:20px; }}
.stat-label {{ color:var(--muted); font-size:13px; text-transform:uppercase; letter-spacing:.08em; }}
.stat-value {{ font-size:32px; font-weight:800; margin-top:8px; }}
.stat-sub {{ color:var(--muted); font-size:13px; margin-top:6px; min-height:18px; }}
.insight-title {{ font-weight:600; margin-bottom:8px; }}
.insight-value {{ font-size:24px; font-weight:700; margin-bottom:4px; }}
.insight-trend {{ font-size:12px; color:var(--muted); }}
h2 {{ margin:0 0 16px; font-size:18px; }}
h3 {{ margin:0 0 12px; font-size:16px; color:var(--ai); }}
.bar-row {{ margin:14px 0; }}
.bar-head {{ display:flex; justify-content:space-between; gap:16px; font-size:14px; margin-bottom:7px; }}
.bar-bg {{ height:9px; background:#0b1220; border-radius:999px; overflow:hidden; }}
.bar-fill {{ height:100%; background:linear-gradient(90deg,var(--accent),var(--good)); border-radius:999px; transition:width 0.3s ease; }}
.pipeline {{ display:grid; grid-template-columns:repeat(5,1fr); gap:10px; }}
.step {{ border:1px solid var(--line); border-radius:16px; padding:14px; background:#111827; transition:all 0.3s ease; }}
.step:hover {{ background:#1f2937; transform:translateY(-1px); }}
.step strong {{ display:block; margin-bottom:6px; }}
.step span {{ color:var(--muted); font-size:13px; }}
table {{ width:100%; border-collapse:collapse; }}
th, td {{ padding:13px 10px; text-align:left; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
a {{ color:#e0f2fe; text-decoration:none; transition:color 0.2s ease; }}
a:hover {{ color:#38bdf8; }}
.muted {{ color:var(--muted); font-size:13px; margin-top:4px; }}
.score {{ font-weight:800; font-size:18px; }}
.priority {{ font-weight:700; color:var(--accent); }}
.success-rate {{ font-weight:600; color:var(--good); }}
.recommendation {{ font-size:12px; color:var(--muted); max-width:200px; }}
.explanation {{ font-size:12px; color:var(--muted); max-width:300px; }}
.apply-today {{ font-size:16px; }}
.pill {{ display:inline-block; padding:5px 10px; border-radius:999px; font-size:12px; font-weight:700; }}
.very-high {{ background:rgba(16,185,129,.16); color:#10b981; }}
.high {{ background:rgba(34,197,94,.16); color:#86efac; }}
.high-quality {{ background:rgba(34,197,94,.16); color:#86efac; }}
.medium {{ background:rgba(245,158,11,.16); color:#fcd34d; }}
.low {{ background:rgba(100,116,139,.20); color:#cbd5e1; }}
.strategy-item {{ display:flex; gap:8px; margin-bottom:12px; align-items:flex-start; }}
.strategy-bullet {{ font-size:16px; }}
.strategy-text {{ flex:1; line-height:1.4; }}
.footer {{ color:var(--muted); font-size:13px; margin-top:18px; }}
.refresh-btn {{ background:var(--accent); color:white; border:none; padding:8px 16px; border-radius:8px; cursor:pointer; font-weight:600; }}
.refresh-btn:hover {{ background:#0ea5e9; }}
.ai-highlight {{ background:linear-gradient(135deg,rgba(139,92,246,.1),rgba(59,130,246,.1)); border:1px solid var(--ai); }}
@media (max-width:1400px) {{ .four {{ grid-template-columns:repeat(2,1fr); }} }}
@media (max-width:1200px) {{ .three {{ grid-template-columns:repeat(2,1fr); }} }}
@media (max-width:900px) {{ .stats,.two,.three,.four,.pipeline {{ grid-template-columns:1fr; }} .header {{ flex-direction:column; }} .container {{ padding:20px; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>🧠 Job Search Decision Engine</h1>
      <div class="subtitle">AI-powered analytics, predictive insights, and strategic recommendations for optimal job hunting success.</div>
    </div>
    <div>
      <div class="badge ai-badge">🤖 AI-Enhanced</div>
      <div class="badge source-badge">🗄️ {data_source.title()}</div>
      <div class="badge">Generated {now.strftime('%Y-%m-%d %H:%M')}</div>
    </div>
  </div>

  <div class="grid stats">
    {stat_card('Jobs tracked', len(jobs), f'{len(week_jobs)} found in last 7 days')}
    {stat_card('Very High Quality', len(very_high_quality), f'{pct(len(very_high_quality), len(jobs))} of tracked jobs', '#10b981')}
    {stat_card('High Quality', len(high_quality), f'{pct(len(high_quality), len(jobs))} of tracked jobs', '#22c55e')}
    {stat_card('Average Score', f'{avg_score:.1f}', f'Best score: {max_score}')}
    {stat_card('Applications', applied_count, f'{pending} pending · {interviews} interviews · {offers} offers')}
    {stat_card('Success Rate', f'{app_stats.get("success_rate", 0):.1f}%', f'{interviews}/{applied_count} interviews')}
    {stat_card('Market Health', f'{health_score:.0f}', f'{market_health.get("status", "Unknown")}', health_color)}
    {stat_card('Optimal Daily Apps', application_strategy.get('daily_strategy', {}).get('optimal_applications', 0), 'AI-recommended', '#8b5cf6')}
  </div>

  <div class="grid four">
    {market_insight_card('Market Status', market_trend, market_trend, health_color)}
    {market_insight_card('Competition Level', competition_count, 'applications', '#f59e0b')}
    {market_insight_card('Apply Today', apply_today_count, 'high-priority jobs', '#22c55e')}
    {market_insight_card('Success Probability', avg_success_prob, 'top 5 jobs', '#38bdf8')}
  </div>

  <div class="ai-card" style="margin-bottom:16px;">
    <h2>🎯 AI Strategy Recommendations</h2>
    <div class="grid three">
      <div>
        <h3>Market Strategy</h3>
        {market_recs}
      </div>
      <div>
        <h3>Application Strategy</h3>
        {app_recs}
      </div>
      <div>
        <h3>Competitive Edge</h3>
        {competitive_advantages}
      </div>
    </div>
  </div>

  <div class="ai-highlight card" style="margin-bottom:16px;">
    <h2>🏆 Priority Jobs (AI-Ranked & Predicted)</h2>
    <table>
      <thead><tr><th>Role</th><th>Location</th><th>Quality</th><th>Score</th><th>Priority</th><th>Success %</th><th>AI Recommendation</th><th>Apply Today</th></tr></thead>
      <tbody>{priority_jobs_html}</tbody>
    </table>
  </div>

  <div class="grid two">
    <div class="card">
      <h2>Top Companies</h2>
      {company_bars}
    </div>
    <div class="card">
      <h2>Top Locations</h2>
      {location_bars}
    </div>
  </div>

  <div class="grid three">
    <div class="card">
      <h2>Score Quality Distribution</h2>
      {quality_bars}
    </div>
    <div class="card">
      <h2>Application Status</h2>
      {status_bars}
    </div>
    <div class="card">
      <h2>Performance Metrics</h2>
      <div class="bar-row">
        <div class="bar-head"><span>Jobs/Day (7d avg)</span><strong>{len(week_jobs)/7:.1f}</strong></div>
        <div class="bar-bg"><div class="bar-fill" style="width:{min(100, (len(week_jobs)/7)*10)}%"></div></div>
      </div>
      <div class="bar-row">
        <div class="bar-head"><span>Apply Rate</span><strong>{pct(applied_count, len(jobs))}</strong></div>
        <div class="bar-bg"><div class="bar-fill" style="width:{min(100, (applied_count/len(jobs))*100) if jobs else 0}%"></div></div>
      </div>
      <div class="bar-row">
        <div class="bar-head"><span>Interview Rate</span><strong>{pct(interviews, applied_count) if applied_count else '0.0%'}</strong></div>
        <div class="bar-bg"><div class="bar-fill" style="width:{min(100, (interviews/applied_count)*100) if applied_count else 0}%"></div></div>
      </div>
    </div>
  </div>

  {"<div class='grid two'>" if recent_applications else ""}
    {"<div class='card' style='margin-bottom:16px;'>" if recent_applications else ""}
    {"<h2>Recent Applications</h2>" if recent_applications else ""}
    {"<table>" if recent_applications else ""}
    {"<thead><tr><th>Role</th><th>Status</th><th>Date</th><th>Notes</th></tr></thead>" if recent_applications else ""}
    {"<tbody>" + recent_apps_html + "</tbody>" if recent_applications else ""}
    {"</table>" if recent_applications else ""}
    {"</div>" if recent_applications else ""}

    {"<div class='card'>" if recent_applications else ""}
    {"<h2>Recent Jobs</h2>" if recent_applications else ""}
    {"<table>" if recent_applications else ""}
    {"<thead><tr><th>Role</th><th>Location</th><th>Quality</th><th>Score</th></tr></thead>" if recent_applications else ""}
    {"<tbody>" + recent_jobs_html + "</tbody>" if recent_applications else ""}
    {"</table>" if recent_applications else ""}
    {"</div>" if recent_applications else ""}
    {"</div>" if recent_applications else ""}

    {"<div class='card'>" if not recent_applications else ""}
    {"<h2>Recent Jobs</h2>" if not recent_applications else ""}
    {"<table>" if not recent_applications else ""}
    {"<thead><tr><th>Role</th><th>Location</th><th>Quality</th><th>Score</th></tr></thead>" if not recent_applications else ""}
    {"<tbody>" + recent_jobs_html + "</tbody>" if not recent_applications else ""}
    {"</table>" if not recent_applications else ""}
    {"</div>" if not recent_applications else ""}

  <div class="footer">
    Data source: {data_source.title()}.
    {"🗄️ Database backend active" if data_source == 'database' else "JSON files (fallback mode)"}.
    🤖 Powered by AI Decision Engine with predictive analytics.
    <button class="refresh-btn" onclick="location.reload()">🔄 Refresh</button>
  </div>
</div>
</body>
</html>"""
    return html


def main():
    """Generate AI-powered decision dashboard."""
    try:
        html = build_decision_dashboard()
        OUTPUT_FILE.write_text(html, encoding="utf-8")
        print(f"✅ Decision Engine Dashboard generated: {OUTPUT_FILE}")
        print(f"🌐 Open: {OUTPUT_FILE}")
        print(f"🤖 Features: AI insights, predictive analytics, strategic recommendations")
        print(f"📊 Data source: {'Database' if is_db_available() else 'JSON fallback'}")
    except Exception as e:
        print(f"❌ Dashboard generation failed: {e}")


if __name__ == "__main__":
    main()
