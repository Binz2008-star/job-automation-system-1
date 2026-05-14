"""
Job Search Dashboard - Enhanced with Decision Engine
Generates a local HTML dashboard with AI-powered decision insights.
Features predictive analytics, competitive analysis, and strategic recommendations.

Run:
    python src/dashboard.py
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
from src.decision_engine import JobDecisionEngine
from src.profile import get_candidate_profile, get_target_roles
from src.feedback_loop import FeedbackLoopOrchestrator
from src.response_intelligence import ResponseType
from src.pdf_manager import PDFManager, initialize_pdf_system
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
JOB_HISTORY_FILE = BASE_DIR / "data" / "job_history.json"
APPLIED_JOBS_FILE = BASE_DIR / "data" / "applied_jobs.json"
OUTPUT_FILE = BASE_DIR / "dashboard.html"

# Application sources — keep in sync with importer/pipeline constants
_IMPORTED_SOURCES: frozenset[str] = frozenset({"linkedin_import"})
_GMAIL_SOURCES: frozenset[str] = frozenset({"gmail"})


def load_json(path: Path, default):
    """Load JSON file with fallback."""
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def load_ng_telemetry() -> Dict[str, Any]:
    """Load NaukriGulf telemetry data."""
    try:
        ng_rate_file = BASE_DIR / "data" / "ng_apply_rate.json"
        if ng_rate_file.exists():
            with open(ng_rate_file, 'r') as f:
                return json.load(f)
    except Exception:
        pass

    return {
        'session_status': 'UNKNOWN',
        'captcha_failures': 0,
        'apply_successes': 0,
        'apply_failures': 0,
        'avg_apply_time': 0,
        'last_successful_apply': None,
        'daily_applies': 0,
        'excluded_jobs': []
    }


def parse_dt(value: str | None):
    """Parse datetime string."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def calculate_effectiveness_metrics(jobs: List[Dict], applications: List[Dict]) -> Dict[str, Any]:
    """Calculate true effectiveness metrics instead of vanity metrics."""
    # Target keywords for relevant roles
    target_keywords = {
        "hse", "qhse", "ehs", "hsse", "safety", "environment", "environmental",
        "sustainability", "compliance", "risk", "operations", "operational",
        "project director", "contracts manager", "contracts lead"
    }

    # Count relevant jobs
    relevant_jobs = []
    excluded_jobs = []
    for job in jobs:
        title = job.get("title", "").lower()
        if any(keyword in title for keyword in target_keywords):
            relevant_jobs.append(job)
        else:
            excluded_jobs.append(job)

    # Calculate metrics
    total_jobs = len(jobs)
    relevant_count = len(relevant_jobs)
    relevant_rate = (relevant_count / total_jobs * 100) if total_jobs > 0 else 0

    # Application funnel metrics
    total_applications = len(applications)
    interviews = sum(1 for app in applications if app.get("status") in ["interview", "interview_scheduled"])
    interview_rate = (interviews / total_applications * 100) if total_applications > 0 else 0

    # Split imported vs real applications
    pipeline_apps = [a for a in applications if a.get("source", "pipeline") not in _IMPORTED_SOURCES]
    imported_apps = [a for a in applications if a.get("source") in _IMPORTED_SOURCES]

    # Top excluded jobs for tuning
    excluded_by_title = Counter(job.get("title", "Unknown") for job in excluded_jobs[:10])

    return {
        'relevant_roles_rate': relevant_rate,
        'relevant_count': relevant_count,
        'total_jobs': total_jobs,
        'interview_rate': interview_rate,
        'interviews': interviews,
        'total_applications': total_applications,
        'pipeline_applications': len(pipeline_apps),
        'imported_applications': len(imported_apps),
        'false_positive_rate': 100 - relevant_rate,
        'top_excluded_jobs': excluded_by_title.most_common(5)
    }


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


def _load_feedback_state(orchestrator: FeedbackLoopOrchestrator = None) -> Dict[str, Any]:
    """Load feedback loop state from orchestrator or disk."""
    if orchestrator:
        state = orchestrator.cycle_state
        adjustments = orchestrator.engine.current_adjustments

        return {
            "last_run_status": state.last_run_status,
            "last_run_at": state.last_run_at,
            "total_cycles": state.total_cycles,
            "total_samples_processed": state.total_samples_processed,
            "last_adjustments_version": state.last_adjustments_version,
            "last_error": state.last_error,
            "adjustments": adjustments.__dict__ if adjustments else {}
        }
    else:
        feedback_data = {
            "last_run_status": "never",
            "last_run_at": None,
            "total_cycles": 0,
            "total_samples_processed": 0,
            "last_adjustments_version": 0,
            "last_error": None,
            "adjustments": {}
        }

        try:
            state_dir = BASE_DIR / "data"
            state_file = state_dir / "cycle_state.json"

            if state_file.exists():
                with open(state_file, 'r') as f:
                    feedback_data.update(json.load(f))

            adjustments_file = state_dir / "scoring_adjustments.json"
            if adjustments_file.exists():
                with open(adjustments_file, 'r') as f:
                    adjustments = json.load(f)
                    feedback_data["adjustments"] = adjustments

        except Exception as e:
            feedback_data["error"] = str(e)

        return feedback_data


def _feedback_panel(feedback_data: Dict[str, Any]) -> str:
    """Generate response intelligence panel HTML."""
    status_color = {
        "success": "var(--good)",
        "failed": "var(--danger)",
        "skipped": "var(--muted)",
        "never": "var(--muted)"
    }

    last_status = feedback_data.get('last_run_status', 'never')
    status_color_style = f"color: {status_color.get(last_status, 'var(--muted)')};"

    panels = []
    panels.append(f"""
    <div class="grid two" style="margin-bottom:16px;">
      <div>
        <div class="bar-row">
          <div class="bar-head"><span>Last Feedback Cycle</span><strong style="{status_color_style}">{last_status.title()}</strong></div>
        </div>
        <div class="bar-row">
          <div class="bar-head"><span>Total Cycles</span><strong>{feedback_data.get('total_cycles', 0)}</strong></div>
        </div>
        <div class="bar-row">
          <div class="bar-head"><span>Samples Processed</span><strong>{feedback_data.get('total_samples_processed', 0)}</strong></div>
        </div>
      </div>
      <div>
        <div class="bar-row">
          <div class="bar-head"><span>Adjustments Version</span><strong>{feedback_data.get('last_adjustments_version', 0)}</strong></div>
        </div>
        <div class="bar-row">
          <div class="bar-head"><span>Success Rate</span><strong>{feedback_data.get('success_rate', 0):.1f}%</strong></div>
        </div>
        <div class="bar-row">
          <div class="bar-head"><span>Last Run</span><strong>{feedback_data.get('last_run_at', 'Never')[:10] if feedback_data.get('last_run_at') else 'Never'}</strong></div>
        </div>
      </div>
    </div>
    """)

    if feedback_data.get('last_error'):
        panels.append(f'<div class="muted" style="color:var(--danger);">⚠️ Last error: {feedback_data.get("last_error")}</div>')

    response_patterns = feedback_data.get('response_patterns', {})
    if response_patterns:
        panels.append('<h3 style="margin-top:16px; margin-bottom:8px;">Response Patterns</h3>')
        panels.append('<div class="grid two">')
        for status, count in response_patterns.items():
            panels.append(f'<div class="bar-row"><div class="bar-head"><span>{status.replace("_", " ").title()}</span><strong>{count}</strong></div></div>')
        panels.append('</div>')

    total_cycles = feedback_data.get('total_cycles', 0)
    if total_cycles > 0:
        panels.append(f'<div class="muted" style="margin-top:12px;">Learning active: {total_cycles} cycles completed</div>')
    else:
        panels.append('<div class="muted">Feedback loop ready - needs 5+ matched outcomes to start learning</div>')

    return ''.join(panels)


def _application_row(app):
    """Generate HTML row for application data."""
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


def _job_row(job, show_confidence=False):
    """Generate HTML row for job data with score-based button logic."""
    title = escape(job.get("title") or "Untitled")
    company = escape(job.get("company") or "Unknown")
    location = escape(job.get("location") or "Unknown")
    score = int(job.get("score") or 0)
    link = escape(job.get("link") or "#")
    band = score_band(score)
    confidence = get_confidence_emoji(score) if show_confidence else ""
    explanation = escape(job.get("profile_explanation", ""))[:100] + "..." if job.get("profile_explanation") else ""

    # Get score thresholds from environment
    import os
    auto_apply_score = int(os.getenv("AUTO_APPLY_SCORE", "85"))
    manual_approval_score = int(os.getenv("MANUAL_APPROVAL_SCORE", "65"))

    # Safety check for apply button
    can_apply = "naukrigulf.com" in link.lower()
    job_json = escape(json.dumps(job))

    # Three-tier button logic based on score
    if not can_apply:
        action_buttons = """
        <td>
          <button class="apply-btn" disabled>
            🔒 NaukriGulf Only
          </button>
        </td>
        """
    elif score >= auto_apply_score:
        # High confidence - Auto Apply badge
        action_buttons = f"""
        <td>
          <div style="display: flex; gap: 8px; align-items: center;">
            <span class="pill" style="background: #10b981; color: white; font-size: 11px;">
              🤖 Auto Apply
            </span>
            <button
              class="apply-btn"
              onclick="applyJob(this)"
              data-job='{job_json}'
              style="background: var(--good);">
              ✅ Apply
            </button>
          </div>
        </td>
        """
    elif score >= manual_approval_score:
        # Medium confidence - Manual approval buttons
        action_buttons = f"""
        <td>
          <div style="display: flex; gap: 6px; flex-wrap: wrap;">
            <button
              class="apply-btn"
              onclick="applyJob(this)"
              data-job='{job_json}'
              style="background: var(--accent); font-size: 12px; padding: 6px 10px;">
              🚀 Apply
            </button>
            <button
              class="apply-btn"
              onclick="skipJob(this)"
              data-job='{job_json}'
              style="background: var(--muted); font-size: 12px; padding: 6px 10px;">
              ⏭️ Skip
            </button>
            <button
              class="apply-btn"
              onclick="openJob(this)"
              data-link='{link}'
              style="background: var(--low); font-size: 12px; padding: 6px 10px;">
              � Open
            </button>
          </div>
        </td>
        """
    else:
        # Low confidence - Skip/Watch only
        action_buttons = f"""
        <td>
          <div style="display: flex; gap: 6px; flex-wrap: wrap;">
            <button
              class="apply-btn"
              onclick="skipJob(this)"
              data-job='{job_json}'
              style="background: var(--muted); font-size: 12px; padding: 6px 10px;">
              ⏭️ Skip
            </button>
            <button
              class="apply-btn"
              onclick="openJob(this)"
              data-link='{link}'
              style="background: var(--low); font-size: 12px; padding: 6px 10px;">
              🔗 Open
            </button>
            <button
              class="apply-btn"
              onclick="blockSimilar(this)"
              data-job='{job_json}'
              style="background: var(--danger); font-size: 12px; padding: 6px 10px;">
              🚫 Block
            </button>
          </div>
        </td>
        """

    return f"""
    <tr>
        <td><a href="{link}" target="_blank">{title}</a><div class="muted">{company}</div></td>
        <td>{location}</td>
        <td><span class="pill {band.lower().replace(' ', '-')}">{band}</span></td>
        <td class="score">{score} {confidence}</td>
        {"<td class='explanation'>" + explanation + "</td>" if explanation else ""}
        {action_buttons}
    </tr>
    """


def _recent_section(recent_applications: List[Dict[str, Any]], recent_jobs: List[Dict[str, Any]]) -> str:
    """Generate recent applications and jobs section HTML."""
    if recent_applications:
        apps_html = f"""
        <div class="card" style="margin-bottom:16px;">
          <h2>Recent Applications</h2>
          <table>
            <thead><tr><th>Role</th><th>Status</th><th>Date</th><th>Notes</th></tr></thead>
            <tbody>{''.join(_application_row(app) for app in recent_applications)}</tbody>
          </table>
        </div>
        <div class="card">
          <h2>Recent Jobs</h2>
          <table>
            <thead><tr><th>Role</th><th>Location</th><th>Quality</th><th>Score</th><th>Why it matches</th><th>Action</th></tr></thead>
            <tbody>{''.join(_job_row(job) for job in recent_jobs)}</tbody>
          </table>
        </div>
        """
        return f'<div class="grid two">{apps_html}</div>'
    else:
        jobs_html = f"""
        <div class="card">
          <h2>Recent Jobs</h2>
          <table>
            <thead><tr><th>Role</th><th>Location</th><th>Quality</th><th>Score</th><th>Why it matches</th><th>Action</th></tr></thead>
            <tbody>{''.join(_job_row(job) for job in recent_jobs)}</tbody>
          </table>
        </div>
        """
        return jobs_html


def load_feedback_loop_data(orchestrator: FeedbackLoopOrchestrator = None) -> Dict[str, Any]:
    """Load feedback loop state and intelligence data."""
    feedback_data = _load_feedback_state(orchestrator)

    try:
        applications = get_applied_jobs()
        if applications:
            status_counts = {}
            for app in applications:
                status = app.get("status", "unknown")
                try:
                    response_type = ResponseType.from_raw(status)
                    normalized_status = response_type.value
                except:
                    normalized_status = status

                status_counts[normalized_status] = status_counts.get(normalized_status, 0) + 1

            feedback_data["response_patterns"] = status_counts

            total_responses = sum(status_counts.values())
            positive_responses = sum(count for status, count in status_counts.items()
                                 if status in ["interview_scheduled", "interview_completed", "technical_assessment", "offer_extended", "offer_accepted"])

            if total_responses > 0:
                feedback_data["success_rate"] = (positive_responses / total_responses) * 100
            else:
                feedback_data["success_rate"] = 0

    except Exception as e:
        feedback_data["analysis_error"] = str(e)

    return feedback_data


def load_dashboard_data() -> Dict[str, Any]:
    """Load dashboard data from database with JSON fallback."""
    if is_db_available():
        try:
            top_jobs = get_top_jobs(50)
            jobs = []

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

            app_stats = get_application_stats()
            applications = get_applied_jobs()

            # Load NG telemetry data
            ng_telemetry = load_ng_telemetry()

            return {
                'jobs': jobs,
                'applications': applications,
                'app_stats': app_stats,
                'ng_telemetry': ng_telemetry,
                'source': 'database'
            }

        except Exception as e:
            print(f"⚠️ Database dashboard failed, using JSON fallback: {e}")

    jobs = load_json(JOB_HISTORY_FILE, [])
    applications = load_json(APPLIED_JOBS_FILE, [])

    normalized_statuses = []
    for app in applications:
        status = app.get("status", "unknown")
        try:
            response_type = ResponseType.from_raw(status)
            normalized_statuses.append(response_type.value)
        except:
            normalized_statuses.append(status)

    status_counts = Counter(normalized_statuses)
    app_stats = {
        'total_applied': len(applications),
        'status_breakdown': dict(status_counts),
        'interviews_scheduled': status_counts.get("interview_scheduled", 0) + status_counts.get("interview", 0),
        'rejections': status_counts.get("rejected", 0),
        'pending': status_counts.get("applied", 0),
        'success_rate': ((status_counts.get("interview_scheduled", 0) + status_counts.get("interview", 0)) / len(applications) * 100) if applications else 0.0
    }

    return {
        'jobs': jobs,
        'applications': applications,
        'app_stats': app_stats,
        'source': 'json'
    }


def build_dashboard(orchestrator: FeedbackLoopOrchestrator = None) -> str:
    """Build enhanced dashboard HTML."""
    data = load_dashboard_data()
    jobs = data['jobs']
    applications = data['applications']
    app_stats = data['app_stats']
    ng_telemetry = data.get('ng_telemetry', {})
    data_source = data['source']

    feedback_data = load_feedback_loop_data(orchestrator)

    # Initialize PDF system
    pdf_manager = initialize_pdf_system()
    cv_pdf = pdf_manager.get_cv_pdf()

    # Calculate true effectiveness metrics
    effectiveness_metrics = calculate_effectiveness_metrics(jobs, applications)

    now = datetime.now()
    week_ago = now - timedelta(days=7)

    scores = [int(j.get("score") or 0) for j in jobs]
    high_quality = [j for j in jobs if int(j.get("score") or 0) >= 65]
    very_high_quality = [j for j in jobs if int(j.get("score") or 0) >= 85]
    week_jobs = [j for j in jobs if (parse_dt(j.get("date_found")) or datetime.min) >= week_ago]

    # ── Application source segmentation ──────────────────────────────────────
    # "pipeline" = originated from the fetch→score→apply loop.
    # "linkedin_import" = bulk-imported from LinkedIn export; excluded from
    #                     apply-rate to avoid inflating the metric.
    # "gmail" = auto-imported from confirmation emails.
    applied_count   = len(applications)
    pipeline_apps   = [a for a in applications
                       if a.get("source", "pipeline") not in _IMPORTED_SOURCES]
    linkedin_apps   = [a for a in applications if a.get("source") in _IMPORTED_SOURCES]
    gmail_apps      = [a for a in applications if a.get("source") in _GMAIL_SOURCES]
    pipeline_count  = len(pipeline_apps)
    # ─────────────────────────────────────────────────────────────────────────

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


    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Job Search Command Center</title>
<style>
:root {{
  --bg:#0f172a; --panel:#111827; --card:#1f2937; --muted:#9ca3af;
  --text:#f9fafb; --line:#374151; --accent:#38bdf8; --good:#22c55e;
  --mid:#f59e0b; --low:#64748b; --danger:#ef4444;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Inter, Arial, sans-serif; background:linear-gradient(135deg,#020617,#111827); color:var(--text); }}
.container {{ max-width:1400px; margin:0 auto; padding:32px; }}
.header {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; margin-bottom:28px; }}
h1 {{ margin:0; font-size:34px; letter-spacing:-0.04em; }}
.subtitle {{ color:var(--muted); margin-top:8px; line-height:1.5; }}
.badge {{ border:1px solid var(--line); padding:10px 14px; border-radius:999px; color:#d1d5db; background:rgba(255,255,255,0.04); white-space:nowrap; }}
.source-badge {{ background:rgba(34,197,94,.16); color:#86efac; border-color:#22c55e; }}
.grid {{ display:grid; gap:16px; }}
.stats {{ grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); margin-bottom:16px; }}
.three {{ grid-template-columns:repeat(3,1fr); }}
.two {{ grid-template-columns:1fr 1fr; margin-bottom:16px; }}
.card {{ background:rgba(31,41,55,0.78); border:1px solid var(--line); border-radius:20px; padding:20px; box-shadow:0 20px 45px rgba(0,0,0,.22); }}
.card:hover {{ transform:translateY(-2px); box-shadow:0 25px 50px rgba(0,0,0,.3); transition:all 0.3s ease; }}
.stat-label {{ color:var(--muted); font-size:13px; text-transform:uppercase; letter-spacing:.08em; }}
.stat-value {{ font-size:32px; font-weight:800; margin-top:8px; }}
.stat-sub {{ color:var(--muted); font-size:13px; margin-top:6px; min-height:18px; }}
h2 {{ margin:0 0 16px; font-size:18px; }}
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
.explanation {{ font-size:12px; color:var(--muted); max-width:300px; }}
.pill {{ display:inline-block; padding:5px 10px; border-radius:999px; font-size:12px; font-weight:700; }}
.very-high {{ background:rgba(16,185,129,.16); color:#10b981; }}
.high {{ background:rgba(34,197,94,.16); color:#86efac; }}
.high-quality {{ background:rgba(34,197,94,.16); color:#86efac; }}
.medium {{ background:rgba(245,158,11,.16); color:#fcd34d; }}
.low {{ background:rgba(100,116,139,.20); color:#cbd5e1; }}
.footer {{ color:var(--muted); font-size:13px; margin-top:18px; }}
.refresh-btn {{ background:var(--accent); color:white; border:none; padding:8px 16px; border-radius:8px; cursor:pointer; font-weight:600; }}
.refresh-btn:hover {{ background:#0ea5e9; }}
@media (max-width:900px) {{ .stats,.two,.three,.pipeline {{ grid-template-columns:1fr; }} .header {{ flex-direction:column; }} .container {{ padding:20px; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>Job Search Command Center</h1>
      <div class="subtitle">Live dashboard for pipeline output, match quality, applications, and best opportunities.</div>
    </div>
    <div>
      <div class="badge source-badge">🗄️ {data_source.title()}</div>
      <div class="badge">Generated {now.strftime('%Y-%m-%d %H:%M')}</div>
    </div>
  </div>

  <div class="grid stats">
    {stat_card('Relevant Roles', f'{effectiveness_metrics["relevant_roles_rate"]:.1f}%', f'{effectiveness_metrics["relevant_count"]}/{effectiveness_metrics["total_jobs"]} jobs match target domains', '#10b981')}
    {stat_card('Interview Rate', f'{effectiveness_metrics["interview_rate"]:.1f}%', f'{effectiveness_metrics["interviews"]}/{effectiveness_metrics["total_applications"]} applications')}
    {stat_card('Pipeline Applications', effectiveness_metrics["pipeline_applications"], f'{effectiveness_metrics["imported_applications"]} imported from history')}
    {stat_card('False Positive Rate', f'{effectiveness_metrics["false_positive_rate"]:.1f}%', 'Non-relevant jobs detected')}
    {stat_card('NG Session', ng_telemetry.get('session_status', 'UNKNOWN'), f'Success: {ng_telemetry.get("apply_successes", 0)} · Failures: {ng_telemetry.get("apply_failures", 0)}')}
    {stat_card('Avg Apply Time', f'{ng_telemetry.get("avg_apply_time", 0)}s', f'Last success: {ng_telemetry.get("last_successful_apply", "Never")[:10]}' if ng_telemetry.get("last_successful_apply") else 'No successful applies yet')}
  </div>

  <div class="card" style="margin-bottom:16px;">
    <h2>Platform Flow</h2>
    <div class="pipeline">
      <div class="step"><strong>1. Fetch</strong><span>Indeed, LinkedIn, Google</span></div>
      <div class="step"><strong>2. Filter</strong><span>Deduplication + seen jobs</span></div>
      <div class="step"><strong>3. Score</strong><span>CV-aware match score</span></div>
      <div class="step"><strong>4. Notify</strong><span>Email + Telegram</span></div>
      <div class="step"><strong>5. Apply</strong><span>Track applications</span></div>
      <div class="step"><strong>6. Learn</strong><span>Feedback loop intelligence</span></div>
    </div>
  </div>

  <div class="card" style="margin-bottom:16px;">
    <h2>🎯 Recruiter Funnel</h2>
    <div class="pipeline">
      <div class="step"><strong>Applications Sent</strong><span>{effectiveness_metrics["total_applications"]} total</span></div>
      <div class="step"><strong>Viewed</strong><span>Tracking via Gmail sync</span></div>
      <div class="step"><strong>Replied</strong><span>Response intelligence active</span></div>
      <div class="step"><strong>Interview</strong><span>{effectiveness_metrics["interviews"]} scheduled</span></div>
      <div class="step"><strong>Conversion Rate</strong><span>{effectiveness_metrics["interview_rate"]:.1f}%</span></div>
    </div>
  </div>

  <div class="card" style="margin-bottom:16px;">
    <h2>🚫 Top Excluded Jobs</h2>
    <div style="font-size: 14px;">
      {f'''
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
        <div>
          <h4 style="margin: 0 0 8px 0; color: var(--muted); font-size: 12px;">Most Common Exclusions</h4>
          {"".join([f"<div style='padding: 4px 0; border-bottom: 1px solid var(--line);'><strong>{title}</strong> <span class='muted'>({count} times)</span></div>" for title, count in effectiveness_metrics["top_excluded_jobs"]])}
        </div>
        <div>
          <h4 style="margin: 0 0 8px 0; color: var(--muted); font-size: 12px;">Filter Tuning Insights</h4>
          <div style="padding: 8px; background: rgba(245, 158, 11, 0.1); border: 1px solid var(--mid); border-radius: 8px;">
            <div style="font-size: 12px; margin-bottom: 4px;">False Positive Rate: <strong>{effectiveness_metrics["false_positive_rate"]:.1f}%</strong></div>
            <div style="font-size: 12px;">Relevant Match Rate: <strong>{effectiveness_metrics["relevant_roles_rate"]:.1f}%</strong></div>
          </div>
        </div>
      </div>
      ''' if effectiveness_metrics["top_excluded_jobs"] else '''
      <div style="color: var(--muted); padding: 12px; background: var(--panel); border-radius: 8px;">
        No excluded jobs data available yet. The system is learning from your filtering patterns.
      </div>
      '''}
    </div>
  </div>

  <div class="card" style="margin-bottom:16px;">
    <h2>🧠 Response Intelligence</h2>
    {_feedback_panel(feedback_data)}
  </div>

  <div class="card" style="margin-bottom:16px;">
    <h2>📄 Document Viewer</h2>
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
      <div>
        <h3 style="margin: 0 0 12px 0; font-size: 16px; color: var(--muted);">CV/Resume</h3>
        {f'''
        <a href="static/pdf_viewer_advanced.html?file={cv_pdf['file_path']}&name={cv_pdf['title'].replace(' ', '%20')}"
           target="_blank"
           style="display: inline-block; background: var(--accent); color: white; padding: 12px 20px;
                  border-radius: 8px; text-decoration: none; font-weight: 600; margin-bottom: 8px;">
          📄 View {cv_pdf['title']}
        </a>
        <div class="muted" style="font-size: 13px; margin-top: 8px;">
          Size: {cv_pdf.get('file_size', 0) / 1024:.1f} KB •
          Modified: {cv_pdf.get('modified_at', 'Unknown')[:10]} •
          PDF.js v5.7.284
        </div>
        ''' if cv_pdf else '''
        <div style="color: var(--muted); padding: 12px; background: var(--panel); border-radius: 8px;">
          No CV document found. Place your CV at data/cv.pdf to enable PDF viewing.
        </div>
        '''}
      </div>
      <div>
        <h3 style="margin: 0 0 12px 0; font-size: 16px; color: var(--muted);">Quick Access</h3>
        <div style="display: flex; flex-direction: column; gap: 8px;">
          {f'''
          <button onclick="window.open('static/pdf_viewer_advanced.html?file={cv_pdf['file_path']}&name={cv_pdf['title'].replace(' ', '%20')}', '_blank')"
                  style="background: var(--good); color: white; border: none; padding: 10px 16px;
                         border-radius: 6px; cursor: pointer; font-weight: 600;">
            👁️ Quick View {cv_pdf['title']}
          </button>
          <div class="muted" style="font-size: 13px;">
            Advanced viewer with zoom, navigation, and download
          </div>
          ''' if cv_pdf else '''
          <div style="color: var(--muted); font-size: 13px;">
            Upload your CV to enable document viewing features
          </div>
          '''}
        </div>
      </div>
    </div>
    {f'''
    <div style="margin-top: 16px; padding: 12px; background: rgba(34, 197, 94, 0.1); border: 1px solid var(--good); border-radius: 8px;">
      <h4 style="margin: 0 0 8px 0; color: var(--good); font-size: 14px;">📋 {cv_pdf['title']} Details</h4>
      <p style="margin: 4px 0; font-size: 13px; color: var(--muted);">
        <strong>Description:</strong> {cv_pdf.get('description', 'No description available')}
      </p>
      <p style="margin: 4px 0; font-size: 13px; color: var(--muted);">
        <strong>Tags:</strong> {', '.join(cv_pdf.get('tags', []))}
      </p>
      <p style="margin: 4px 0; font-size: 13px; color: var(--muted);">
        <strong>Registered:</strong> {cv_pdf.get('registered_at', 'Unknown')[:10]}
      </p>
    </div>
    ''' if cv_pdf else ''}
  </div>

  <div class="grid two">
    <div class="card">
      <h2>Top Companies</h2>
      {''.join(bar(company, count, max_company_count) for company, count in company_counts.most_common(10))}
    </div>
    <div class="card">
      <h2>Top Locations</h2>
      {''.join(bar(location, count, max_location_count) for location, count in location_counts.most_common(10))}
    </div>
  </div>

  <div class="grid three">
    <div class="card">
      <h2>Score Quality</h2>
      {''.join(bar(label, band_counts.get(label, 0), max(band_counts.values()) if band_counts else 1,
                "linear-gradient(90deg,#10b981,#22c55e)" if "Very High" in label or "High" in label else "")
                for label in ['Very High','High','High quality','Medium','Low'])}
    </div>
    <div class="card">
      <h2>Application Status</h2>
      {''.join(bar(status.title(), count, max(status_counts.values()) if status_counts else 1)
                for status, count in status_counts.items()) or '<div class="muted">No applications tracked yet.</div>'}
    </div>
    <div class="card">
      <h2>Quick Stats</h2>
      <div class="bar-row">
        <div class="bar-head"><span>Jobs/Day (7d avg)</span><strong>{len(week_jobs)/7:.1f}</strong></div>
        <div class="bar-bg"><div class="bar-fill" style="width:{min(100, (len(week_jobs)/7)*10)}%"></div></div>
      </div>
      <div class="bar-row">
        <div class="bar-head"><span>Apply Rate (pipeline)</span><strong>{pct(pipeline_count, len(jobs))}</strong></div>
        <div class="bar-bg"><div class="bar-fill" style="width:{min(100, (pipeline_count/len(jobs))*100) if jobs else 0}%"></div></div>
      </div>
    </div>
  </div>

  <div class="card" style="margin-bottom:16px;">
    <h2>Top Jobs by Score {f'(🗄️ {data_source.title()})'}</h2>
    <table>
      <thead><tr><th>Role</th><th>Location</th><th>Quality</th><th>Score</th><th>Why it matches</th><th>Action</th></tr></thead>
      <tbody>{''.join(_job_row(job, show_confidence=True) for job in top_jobs)}</tbody>
    </table>
  </div>

  {_recent_section(recent_applications, recent_jobs)}

  <div class="footer">
    Data source: {data_source.title()}.
    {"🗄️ Database backend active" if data_source == 'database' else "JSON files (fallback mode)"}.
    <button class="refresh-btn" onclick="location.reload()">🔄 Refresh</button>
  </div>
</div>

<script>
async function applyJob(btn) {{
    btn.disabled = true;
    btn.innerText = "Applying...";

    try {{
        const job = JSON.parse(btn.dataset.job);

        const res = await fetch("http://127.0.0.1:8000/apply-one", {{
            method: "POST",
            headers: {{
                "Content-Type": "application/json"
            }},
            body: JSON.stringify({{ job }})
        }});

        const data = await res.json();

        if (data.status) {{
            btn.innerText = "✅ " + data.status;
        }} else {{
            btn.innerText = "⚠️ Unknown";
        }}

    }} catch (err) {{
        console.error(err);
        btn.innerText = "❌ Failed";
    }}
}}

async function skipJob(btn) {{
    btn.disabled = true;
    btn.innerText = "⏭️ Skipped";

    try {{
        const job = JSON.parse(btn.dataset.job);
        console.log("Skipped job:", job.title);

        // Mark job as seen/skipped in local storage or send to backend
        const res = await fetch("http://127.0.0.1:8000/skip-job", {{
            method: "POST",
            headers: {{
                "Content-Type": "application/json"
            }},
            body: JSON.stringify({{ job }})
        }});

        if (res.ok) {{
            btn.innerText = "✅ Skipped";
        }} else {{
            btn.innerText = "⚠️ Error";
        }}

    }} catch (err) {{
        console.error(err);
        btn.innerText = "❌ Failed";
    }}
}}

function openJob(btn) {{
    const link = btn.dataset.link;
    if (link && link !== "#") {{
        window.open(link, "_blank");
    }} else {{
        alert("No valid job link available");
    }}
}}

async function blockSimilar(btn) {{
    if (!confirm("Block similar jobs? This will hide jobs with similar titles/companies.")) {{
        return;
    }}

    btn.disabled = true;
    btn.innerText = "🚫 Blocking...";

    try {{
        const job = JSON.parse(btn.dataset.job);
        console.log("Blocking similar to:", job.title);

        // Send to backend to add to exclusion list
        const res = await fetch("http://127.0.0.1:8000/block-similar", {{
            method: "POST",
            headers: {{
                "Content-Type": "application/json"
            }},
            body: JSON.stringify({{ job }})
        }});

        if (res.ok) {{
            btn.innerText = "✅ Blocked";
        }} else {{
            btn.innerText = "⚠️ Error";
        }}

    }} catch (err) {{
        console.error(err);
        btn.innerText = "❌ Failed";
    }}
}}
</script>

</body>
</html>"""
    return html


def main():
    """Generate dashboard."""
    try:
        html = build_dashboard()
        OUTPUT_FILE.write_text(html, encoding="utf-8")
        print(f"✅ Dashboard generated: {OUTPUT_FILE}")
        print(f"🌐 Open: {OUTPUT_FILE}")
        print(f"📊 Data source: {'Database' if is_db_available() else 'JSON fallback'}")
    except Exception as e:
        print(f"❌ Dashboard generation failed: {e}")


if __name__ == "__main__":
    main()
