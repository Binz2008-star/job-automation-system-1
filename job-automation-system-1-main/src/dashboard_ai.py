"""
AI-Powered Job Search Decision Dashboard
High-end dashboard with predictive analytics and strategic recommendations.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

from src.db import get_top_jobs, get_application_stats, is_db_available
from src.applications import get_applied_jobs
from src.decision_engine import generate_decision_insights

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = BASE_DIR / "dashboard.html"


def build_ai_dashboard() -> str:
    """Build AI-powered dashboard with decision engine insights."""
    
    # Generate decision insights
    insights = generate_decision_insights()
    market_analysis = insights.get('market_analysis', {})
    application_strategy = insights.get('application_strategy', {})
    competitive_analysis = insights.get('competitive_analysis', {})
    candidate_profile = insights.get('candidate_profile', {})
    
    # Get data
    if is_db_available():
        jobs = get_top_jobs(50)
        applications = get_applied_jobs()
        data_source = "Database"
    else:
        jobs = []
        applications = []
        data_source = "JSON Fallback"
    
    now = datetime.now()
    
    # Calculate metrics
    total_jobs = len(jobs)
    high_quality = len([j for j in jobs if j.get('score', 0) >= 65])
    very_high_quality = len([j for j in jobs if j.get('score', 0) >= 85])
    applied_count = len(applications)
    
    # Market health
    market_health = market_analysis.get('market_health', {})
    health_score = market_health.get('health_score', 0)
    health_status = market_health.get('status', 'Unknown')
    
    # Priority jobs
    prioritized_jobs = application_strategy.get('prioritized_jobs', [])[:10]
    apply_today_count = len([j for j in prioritized_jobs if j.get('apply_today', False)])
    
    # Success probabilities
    success_probs = [j.get('success_probability', 0) for j in prioritized_jobs[:5]]
    avg_success = f"{sum(success_probs)/len(success_probs):.0f}%" if success_probs else "0%"
    
    # Strategy recommendations
    market_recs = market_analysis.get('recommendations', [])[:3]
    app_recs = application_strategy.get('strategy_recommendations', [])[:3]
    competitive_advantages = candidate_profile.get('competitive_advantages', [])[:3]
    
    # Build HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🧠 AI Job Search Decision Engine</title>
    <style>
        :root {{
            --bg: #0f172a;
            --card: #1f2937;
            --accent: #38bdf8;
            --good: #22c55e;
            --ai: #8b5cf6;
            --danger: #ef4444;
            --text: #f9fafb;
            --muted: #9ca3af;
        }}
        
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #020617, #111827);
            color: var(--text);
            line-height: 1.6;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1800px;
            margin: 0 auto;
            padding: 2rem;
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 3rem;
        }}
        
        h1 {{
            font-size: 3rem;
            font-weight: 800;
            background: linear-gradient(135deg, var(--accent), var(--ai));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }}
        
        .subtitle {{
            color: var(--muted);
            font-size: 1.2rem;
        }}
        
        .badges {{
            display: flex;
            gap: 1rem;
            justify-content: center;
            margin-top: 1rem;
            flex-wrap: wrap;
        }}
        
        .badge {{
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            padding: 0.5rem 1rem;
            border-radius: 2rem;
            font-size: 0.9rem;
        }}
        
        .ai-badge {{
            background: rgba(139, 92, 246, 0.2);
            border-color: var(--ai);
        }}
        
        .grid {{
            display: grid;
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}
        
        .grid-4 {{
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        }}
        
        .grid-3 {{
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        }}
        
        .grid-2 {{
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
        }}
        
        .card {{
            background: rgba(31, 41, 55, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 1rem;
            padding: 1.5rem;
            backdrop-filter: blur(10px);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        
        .card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        }}
        
        .ai-card {{
            background: rgba(139, 92, 246, 0.1);
            border-color: var(--ai);
        }}
        
        .stat-card {{
            text-align: center;
        }}
        
        .stat-label {{
            color: var(--muted);
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 0.5rem;
        }}
        
        .stat-value {{
            font-size: 2.5rem;
            font-weight: 800;
            margin-bottom: 0.5rem;
        }}
        
        .stat-sub {{
            color: var(--muted);
            font-size: 0.9rem;
        }}
        
        h2 {{
            font-size: 1.5rem;
            margin-bottom: 1rem;
            color: var(--accent);
        }}
        
        h3 {{
            font-size: 1.2rem;
            margin-bottom: 0.8rem;
            color: var(--ai);
        }}
        
        .insight-card {{
            text-align: center;
            padding: 1rem;
        }}
        
        .insight-value {{
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }}
        
        .insight-label {{
            color: var(--muted);
            font-size: 0.9rem;
        }}
        
        .strategy-item {{
            display: flex;
            gap: 0.8rem;
            margin-bottom: 1rem;
            align-items: flex-start;
        }}
        
        .strategy-bullet {{
            font-size: 1.2rem;
        }}
        
        .priority-job {{
            background: rgba(59, 130, 246, 0.1);
            border-color: var(--accent);
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        th, td {{
            padding: 0.8rem;
            text-align: left;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        th {{
            color: var(--muted);
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        
        a {{
            color: var(--accent);
            text-decoration: none;
        }}
        
        a:hover {{
            text-decoration: underline;
        }}
        
        .muted {{
            color: var(--muted);
            font-size: 0.9rem;
        }}
        
        .score {{
            font-weight: 700;
            font-size: 1.1rem;
        }}
        
        .success-rate {{
            color: var(--good);
            font-weight: 600;
        }}
        
        .apply-today {{
            font-size: 1.2rem;
        }}
        
        .bar {{
            height: 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 1rem;
            overflow: hidden;
            margin-top: 0.5rem;
        }}
        
        .bar-fill {{
            height: 100%;
            background: linear-gradient(90deg, var(--accent), var(--good));
            border-radius: 1rem;
            transition: width 0.3s ease;
        }}
        
        .footer {{
            text-align: center;
            color: var(--muted);
            margin-top: 3rem;
            padding: 2rem;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        .refresh-btn {{
            background: var(--accent);
            color: white;
            border: none;
            padding: 0.8rem 1.5rem;
            border-radius: 0.5rem;
            cursor: pointer;
            font-weight: 600;
            margin-top: 1rem;
        }}
        
        .refresh-btn:hover {{
            background: #0ea5e9;
        }}
        
        @media (max-width: 768px) {{
            .container {{
                padding: 1rem;
            }}
            
            h1 {{
                font-size: 2rem;
            }}
            
            .grid-4, .grid-3, .grid-2 {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧠 AI Job Search Decision Engine</h1>
            <p class="subtitle">Predictive analytics, strategic insights, and intelligent recommendations for optimal job hunting success</p>
            <div class="badges">
                <div class="badge ai-badge">🤖 AI-Enhanced</div>
                <div class="badge">🗄️ {data_source}</div>
                <div class="badge">📊 {now.strftime('%Y-%m-%d %H:%M')}</div>
            </div>
        </div>

        <div class="grid grid-4">
            <div class="card stat-card">
                <div class="stat-label">Jobs Tracked</div>
                <div class="stat-value">{total_jobs}</div>
                <div class="stat-sub">In database</div>
            </div>
            <div class="card stat-card">
                <div class="stat-label">Very High Quality</div>
                <div class="stat-value">{very_high_quality}</div>
                <div class="stat-sub">85+ score</div>
            </div>
            <div class="card stat-card">
                <div class="stat-label">Applications</div>
                <div class="stat-value">{applied_count}</div>
                <div class="stat-sub">Total submitted</div>
            </div>
            <div class="card stat-card">
                <div class="stat-label">Market Health</div>
                <div class="stat-value">{health_score:.0f}</div>
                <div class="stat-sub">{health_status}</div>
            </div>
        </div>

        <div class="grid grid-4">
            <div class="card insight-card">
                <div class="insight-value">{apply_today_count}</div>
                <div class="insight-label">🎯 Apply Today</div>
            </div>
            <div class="card insight-card">
                <div class="insight-value">{avg_success}</div>
                <div class="insight-label">📈 Success Rate</div>
            </div>
            <div class="card insight-card">
                <div class="insight-value">{len(prioritized_jobs)}</div>
                <div class="insight-label">🏆 Priority Jobs</div>
            </div>
            <div class="card insight-card">
                <div class="insight-value">{len(competitive_advantages)}</div>
                <div class="insight-label">⚡ Competitive Edges</div>
            </div>
        </div>

        <div class="card ai-card">
            <h2>🎯 AI Strategy Recommendations</h2>
            <div class="grid grid-3">
                <div>
                    <h3>Market Strategy</h3>
                    {"".join(f'<div class="strategy-item"><div class="strategy-bullet">💡</div><div>{rec}</div></div>' for rec in market_recs)}
                </div>
                <div>
                    <h3>Application Strategy</h3>
                    {"".join(f'<div class="strategy-item"><div class="strategy-bullet">💡</div><div>{rec}</div></div>' for rec in app_recs)}
                </div>
                <div>
                    <h3>Competitive Edge</h3>
                    {"".join(f'<div class="strategy-item"><div class="strategy-bullet">✓</div><div>{adv}</div></div>' for adv in competitive_advantages)}
                </div>
            </div>
        </div>

        <div class="card priority-job">
            <h2>🏆 AI-Ranked Priority Jobs</h2>
            <table>
                <thead>
                    <tr>
                        <th>Role</th>
                        <th>Company</th>
                        <th>Score</th>
                        <th>Success %</th>
                        <th>AI Recommendation</th>
                        <th>Apply Today</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(f'''
                    <tr>
                        <td><a href="{job.get('job', {}).get('link', '#')}" target="_blank">{job.get('job', {}).get('title', 'N/A')}</a></td>
                        <td>{job.get('job', {}).get('company', 'N/A')}</td>
                        <td class="score">{job.get('job', {}).get('score', 0)}</td>
                        <td class="success-rate">{job.get('success_probability', 0)}%</td>
                        <td>{job.get('recommendation', 'N/A')[:50]}...</td>
                        <td class="apply-today">{'🎯' if job.get('apply_today') else ''}</td>
                    </tr>
                    ''' for job in prioritized_jobs)}
                </tbody>
            </table>
        </div>

        <div class="footer">
            <p>🤖 Powered by AI Decision Engine with predictive analytics</p>
            <p>Data source: {data_source} | Real-time insights and recommendations</p>
            <button class="refresh-btn" onclick="location.reload()">🔄 Refresh Dashboard</button>
        </div>
    </div>
</body>
</html>"""
    
    return html


def main():
    """Generate AI-powered decision dashboard."""
    try:
        html = build_ai_dashboard()
        OUTPUT_FILE.write_text(html, encoding="utf-8")
        print(f"✅ AI Decision Dashboard generated: {OUTPUT_FILE}")
        print(f"🌐 Open: {OUTPUT_FILE}")
        print(f"🤖 Features: Predictive analytics, AI recommendations, strategic insights")
        print(f"📊 Data source: {'Database' if is_db_available() else 'JSON fallback'}")
    except Exception as e:
        print(f"❌ Dashboard generation failed: {e}")


if __name__ == "__main__":
    main()
