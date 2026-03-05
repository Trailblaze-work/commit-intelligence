"""Generate static HTML dashboard from commit data."""

import json
from datetime import datetime, timezone
from pathlib import Path

from . import db

TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Commit Intelligence - Trailblaze-work</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root {{
    --bg: #0f172a;
    --surface: #1e293b;
    --border: #334155;
    --text: #e2e8f0;
    --text-muted: #94a3b8;
    --accent: #38bdf8;
    --green: #4ade80;
    --red: #f87171;
    --purple: #a78bfa;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 2rem;
    max-width: 1200px;
    margin: 0 auto;
  }}
  h1 {{ font-size: 1.5rem; font-weight: 600; }}
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 2rem;
    flex-wrap: wrap;
    gap: 0.5rem;
  }}
  .header-meta {{ color: var(--text-muted); font-size: 0.85rem; }}
  .cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
  }}
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 0.75rem;
    padding: 1.25rem;
  }}
  .card-label {{ font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }}
  .card-value {{ font-size: 1.75rem; font-weight: 700; margin-top: 0.25rem; }}
  .card-value.accent {{ color: var(--accent); }}
  .card-value.green {{ color: var(--green); }}
  .card-value.purple {{ color: var(--purple); }}
  .chart-container {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 0.75rem;
    padding: 1.5rem;
    margin-bottom: 2rem;
  }}
  .chart-container h2 {{ font-size: 1.1rem; margin-bottom: 1rem; font-weight: 500; }}
  canvas {{ max-height: 350px; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
  }}
  th, td {{ padding: 0.6rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--text-muted); font-weight: 500; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  tr:hover td {{ background: rgba(56, 189, 248, 0.05); }}
  .empty {{ text-align: center; color: var(--text-muted); padding: 3rem; }}
</style>
</head>
<body>
<div class="header">
  <h1>Commit Intelligence &mdash; Trailblaze-work</h1>
  <div class="header-meta">Last updated: {last_updated}</div>
</div>

<div class="cards">
  <div class="card">
    <div class="card-label">Total Commits</div>
    <div class="card-value">{total_commits}</div>
  </div>
  <div class="card">
    <div class="card-label">AI Adoption</div>
    <div class="card-value accent">{ai_pct}%</div>
  </div>
  <div class="card">
    <div class="card-label">Bug / Feature Ratio</div>
    <div class="card-value green">{bug_feature_ratio}</div>
  </div>
  <div class="card">
    <div class="card-label">Active Contributors</div>
    <div class="card-value purple">{contributors}</div>
  </div>
</div>

<div class="chart-container">
  <h2>AI Adoption Rate (weekly % of human commits)</h2>
  <canvas id="aiChart"></canvas>
</div>

<div class="chart-container">
  <h2>Bug Fixes vs Features (weekly)</h2>
  <canvas id="bfChart"></canvas>
</div>

<div class="chart-container">
  <h2>Author Breakdown</h2>
  {author_table}
</div>

<script>
const aiData = {ai_data_json};
const bfData = {bf_data_json};

const chartDefaults = {{
  color: '#94a3b8',
  borderColor: '#334155',
}};
Chart.defaults.color = chartDefaults.color;
Chart.defaults.borderColor = chartDefaults.borderColor;

// AI Adoption line chart
new Chart(document.getElementById('aiChart'), {{
  type: 'line',
  data: {{
    labels: aiData.map(d => d.week),
    datasets: [{{
      label: 'AI-Assisted %',
      data: aiData.map(d => d.total > 0 ? Math.round(d.ai_count / d.total * 100 * 10) / 10 : 0),
      borderColor: '#38bdf8',
      backgroundColor: 'rgba(56, 189, 248, 0.15)',
      fill: true,
      tension: 0.3,
      pointRadius: 3,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{ display: false }},
    }},
    scales: {{
      y: {{
        beginAtZero: true,
        max: 100,
        ticks: {{ callback: v => v + '%' }},
      }},
    }},
  }},
}});

// Bug vs Feature stacked bar chart
new Chart(document.getElementById('bfChart'), {{
  type: 'bar',
  data: {{
    labels: bfData.map(d => d.week),
    datasets: [
      {{
        label: 'Bugs Fixed',
        data: bfData.map(d => d.bugs),
        backgroundColor: '#f87171',
      }},
      {{
        label: 'Features Added',
        data: bfData.map(d => d.features),
        backgroundColor: '#4ade80',
      }},
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{ position: 'top' }},
    }},
    scales: {{
      x: {{ stacked: true }},
      y: {{ stacked: true, beginAtZero: true }},
    }},
  }},
}});
</script>
</body>
</html>
"""


def generate(output_dir: str = "docs/") -> None:
    conn = db.get_connection()
    db.init_db(conn)

    summary = db.summary_stats(conn)
    weekly_ai = db.weekly_ai_stats(conn)
    weekly_bf = db.weekly_bugfix_feature_stats(conn)
    authors = db.author_stats(conn)
    conn.close()

    total = summary["total"] or 0
    ai_count = summary["ai_count"] or 0
    bugs = summary["bugs"] or 0
    features = summary["features"] or 0
    contributors = summary["contributors"] or 0

    ai_pct = round(ai_count / total * 100, 1) if total > 0 else 0
    bug_feature_ratio = round(bugs / features, 2) if features > 0 else bugs

    ai_data = [{"week": r["week"], "total": r["total"], "ai_count": r["ai_count"]}
               for r in weekly_ai]
    bf_data = [{"week": r["week"], "bugs": r["bugs"], "features": r["features"]}
               for r in weekly_bf]

    # Author table
    if authors:
        rows = []
        for a in authors:
            a_total = a["total"]
            a_ai = a["ai_count"] or 0
            a_pct = round(a_ai / a_total * 100, 1) if a_total > 0 else 0
            rows.append(
                f"<tr><td>{_esc(a['author'])}</td><td>{a_total}</td>"
                f"<td>{a_pct}%</td><td>{a['bugs']}</td><td>{a['features']}</td></tr>"
            )
        author_table = (
            "<table><thead><tr><th>Author</th><th>Commits</th><th>AI %</th>"
            "<th>Bugs Fixed</th><th>Features</th></tr></thead><tbody>"
            + "\n".join(rows)
            + "</tbody></table>"
        )
    else:
        author_table = '<div class="empty">No data yet. Run scan and analyze first.</div>'

    last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = TEMPLATE.format(
        last_updated=last_updated,
        total_commits=total,
        ai_pct=ai_pct,
        bug_feature_ratio=bug_feature_ratio,
        contributors=contributors,
        ai_data_json=json.dumps(ai_data),
        bf_data_json=json.dumps(bf_data),
        author_table=author_table,
    )

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "index.html").write_text(html)
    print(f"Dashboard written to {out_path / 'index.html'}")


def _esc(s: str | None) -> str:
    if not s:
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
