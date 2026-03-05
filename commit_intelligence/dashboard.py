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
<title>Commit Intelligence - Trailblaze</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Outfit:wght@300;400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root {{
    --bg: #08080a;
    --surface: #111113;
    --border: rgba(232, 154, 46, 0.12);
    --border-glow: rgba(232, 154, 46, 0.25);
    --text: #f0ebe3;
    --text-muted: #9a9590;
    --accent: #e89a2e;
    --accent-orange: #e86a2e;
    --accent-ember: #ff4d1a;
    --green: #4ade80;
    --red: #f87171;
    --purple: #a78bfa;
    --font-display: 'Syne', sans-serif;
    --font-body: 'Outfit', sans-serif;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  ::-webkit-scrollbar {{ width: 6px; }}
  ::-webkit-scrollbar-track {{ background: var(--bg); }}
  ::-webkit-scrollbar-thumb {{ background: var(--accent); border-radius: 3px; }}
  body {{
    font-family: var(--font-body);
    font-weight: 400;
    color: var(--text);
    background: var(--bg);
    padding: 2rem;
    max-width: 1200px;
    margin: 0 auto;
    -webkit-font-smoothing: antialiased;
  }}
  h1 {{
    font-family: var(--font-display);
    font-size: 1.5rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, var(--accent), var(--accent-orange), var(--accent-ember));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }}
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 1.5rem;
    flex-wrap: wrap;
    gap: 0.5rem;
  }}
  .header-meta {{ color: var(--text-muted); font-size: 0.85rem; font-weight: 300; }}
  .filter-bar {{
    margin-bottom: 1.5rem;
    position: relative;
    display: inline-block;
  }}
  .filter-bar label {{
    color: var(--text-muted);
    font-size: 0.85rem;
    margin-right: 0.5rem;
  }}
  .combo {{
    position: relative;
    display: inline-block;
  }}
  .combo-input {{
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    padding: 0.5rem 0.75rem;
    font-size: 0.9rem;
    width: 280px;
    outline: none;
  }}
  .combo-input:focus {{
    border-color: var(--border-glow);
  }}
  .combo-list {{
    display: none;
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 0 0 0.5rem 0.5rem;
    max-height: 240px;
    overflow-y: auto;
    z-index: 10;
  }}
  .combo-list.open {{
    display: block;
  }}
  .combo-item {{
    padding: 0.45rem 0.75rem;
    cursor: pointer;
    font-size: 0.9rem;
  }}
  .combo-item:hover, .combo-item.active {{
    background: rgba(232, 154, 46, 0.12);
  }}
  .combo-item .match {{
    color: var(--accent);
    font-weight: 600;
  }}
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
  .card-value.purple {{ color: var(--accent-orange); }}
  .chart-container {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 0.75rem;
    padding: 1.5rem;
    margin-bottom: 2rem;
  }}
  .chart-container h2 {{ font-family: var(--font-display); font-size: 1.05rem; margin-bottom: 1rem; font-weight: 700; letter-spacing: -0.01em; }}
  canvas {{ max-height: 350px; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
  }}
  th, td {{ padding: 0.6rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--text-muted); font-weight: 500; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  tr:hover td {{ background: rgba(232, 154, 46, 0.06); }}
  .empty {{ text-align: center; color: var(--text-muted); padding: 3rem; }}
</style>
</head>
<body>
<div class="header">
  <h1>Commit Intelligence &mdash; Trailblaze-work</h1>
  <div class="header-meta">Last updated: {last_updated}</div>
</div>

<div class="filter-bar">
  <label>Repository:</label>
  <div class="combo" id="repoCombo">
    <input type="text" class="combo-input" id="repoInput" placeholder="All repositories" autocomplete="off">
    <div class="combo-list" id="repoList"></div>
  </div>
</div>

<div class="cards">
  <div class="card">
    <div class="card-label">Total Commits</div>
    <div class="card-value" id="cardTotal">0</div>
  </div>
  <div class="card">
    <div class="card-label">AI Adoption</div>
    <div class="card-value accent" id="cardAI">0%</div>
  </div>
  <div class="card">
    <div class="card-label">Bug / Feature Ratio</div>
    <div class="card-value green" id="cardBF">0</div>
  </div>
  <div class="card">
    <div class="card-label">Active Contributors</div>
    <div class="card-value purple" id="cardContrib">0</div>
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
  <table>
    <thead><tr><th>Author</th><th>Commits</th><th>AI %</th><th>Bugs Fixed</th><th>Features</th></tr></thead>
    <tbody id="authorBody"></tbody>
  </table>
</div>

<script>
// --- Embedded data ---
const DATA = {all_data_json};

// --- Chart instances ---
Chart.defaults.color = '#9a9590';
Chart.defaults.borderColor = 'rgba(232, 154, 46, 0.12)';

let aiChart = new Chart(document.getElementById('aiChart'), {{
  type: 'line',
  data: {{ labels: [], datasets: [{{ label: 'AI-Assisted %', data: [], borderColor: '#e89a2e', backgroundColor: 'rgba(232, 154, 46, 0.15)', fill: true, tension: 0.3, pointRadius: 3 }}] }},
  options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true, max: 100, ticks: {{ callback: v => v + '%' }} }} }} }},
}});

let bfChart = new Chart(document.getElementById('bfChart'), {{
  type: 'bar',
  data: {{ labels: [], datasets: [
    {{ label: 'Bugs Fixed', data: [], backgroundColor: '#e86a2e' }},
    {{ label: 'Features Added', data: [], backgroundColor: '#e89a2e' }},
  ] }},
  options: {{ responsive: true, plugins: {{ legend: {{ position: 'top' }} }}, scales: {{ x: {{ stacked: true }}, y: {{ stacked: true, beginAtZero: true }} }} }},
}});

// --- Searchable repo picker ---
const REPOS = {repos_json};
let selectedRepo = '__all__';
let activeIdx = -1;

const comboInput = document.getElementById('repoInput');
const comboList = document.getElementById('repoList');

function highlightMatch(text, query) {{
  if (!query) return text;
  const i = text.toLowerCase().indexOf(query.toLowerCase());
  if (i === -1) return text;
  return text.slice(0, i) + '<span class="match">' + text.slice(i, i + query.length) + '</span>' + text.slice(i + query.length);
}}

function renderList(query) {{
  const q = (query || '').toLowerCase();
  const items = [{{ value: '__all__', label: 'All repositories' }}]
    .concat(REPOS.map(r => ({{ value: r, label: r }})))
    .filter(it => !q || it.label.toLowerCase().includes(q));
  activeIdx = -1;
  comboList.innerHTML = items.map((it, i) =>
    `<div class="combo-item" data-value="${{it.value}}" data-idx="${{i}}">${{highlightMatch(it.label, query)}}</div>`
  ).join('');
  comboList.classList.toggle('open', items.length > 0);
}}

function selectRepo(value, label) {{
  selectedRepo = value;
  comboInput.value = value === '__all__' ? '' : label || value;
  comboInput.placeholder = value === '__all__' ? 'All repositories' : '';
  comboList.classList.remove('open');
  applyFilter();
}}

comboInput.addEventListener('focus', () => renderList(comboInput.value));
comboInput.addEventListener('input', () => renderList(comboInput.value));

comboInput.addEventListener('keydown', (e) => {{
  const items = comboList.querySelectorAll('.combo-item');
  if (e.key === 'ArrowDown') {{
    e.preventDefault();
    activeIdx = Math.min(activeIdx + 1, items.length - 1);
  }} else if (e.key === 'ArrowUp') {{
    e.preventDefault();
    activeIdx = Math.max(activeIdx - 1, 0);
  }} else if (e.key === 'Enter') {{
    e.preventDefault();
    if (activeIdx >= 0 && items[activeIdx]) {{
      selectRepo(items[activeIdx].dataset.value, items[activeIdx].textContent);
    }} else if (comboInput.value === '') {{
      selectRepo('__all__', '');
    }}
    comboInput.blur();
    return;
  }} else if (e.key === 'Escape') {{
    comboList.classList.remove('open');
    comboInput.blur();
    return;
  }} else {{
    return;
  }}
  items.forEach((el, i) => el.classList.toggle('active', i === activeIdx));
  if (items[activeIdx]) items[activeIdx].scrollIntoView({{ block: 'nearest' }});
}});

comboList.addEventListener('mousedown', (e) => {{
  const item = e.target.closest('.combo-item');
  if (item) selectRepo(item.dataset.value, item.textContent);
}});

document.addEventListener('click', (e) => {{
  if (!document.getElementById('repoCombo').contains(e.target)) {{
    comboList.classList.remove('open');
  }}
}});

// If input is cleared and blurred, reset to all
comboInput.addEventListener('blur', () => {{
  setTimeout(() => {{
    if (!comboInput.value && selectedRepo !== '__all__') {{
      selectRepo('__all__', '');
    }}
  }}, 200);
}});

function applyFilter() {{
  const repo = selectedRepo;
  const isAll = repo === '__all__';

  // Filter weekly AI data
  const aiRows = DATA.weeklyAI.filter(d => isAll || d.repo === repo);
  const aiByWeek = {{}};
  aiRows.forEach(d => {{
    if (!aiByWeek[d.week]) aiByWeek[d.week] = {{ total: 0, ai_count: 0 }};
    aiByWeek[d.week].total += d.total;
    aiByWeek[d.week].ai_count += d.ai_count;
  }});
  const aiWeeks = Object.keys(aiByWeek).sort();
  aiChart.data.labels = aiWeeks;
  aiChart.data.datasets[0].data = aiWeeks.map(w => aiByWeek[w].total > 0 ? Math.round(aiByWeek[w].ai_count / aiByWeek[w].total * 1000) / 10 : 0);
  aiChart.update();

  // Filter weekly bug/feature data
  const bfRows = DATA.weeklyBF.filter(d => isAll || d.repo === repo);
  const bfByWeek = {{}};
  bfRows.forEach(d => {{
    if (!bfByWeek[d.week]) bfByWeek[d.week] = {{ bugs: 0, features: 0 }};
    bfByWeek[d.week].bugs += d.bugs;
    bfByWeek[d.week].features += d.features;
  }});
  const bfWeeks = Object.keys(bfByWeek).sort();
  bfChart.data.labels = bfWeeks;
  bfChart.data.datasets[0].data = bfWeeks.map(w => bfByWeek[w].bugs);
  bfChart.data.datasets[1].data = bfWeeks.map(w => bfByWeek[w].features);
  bfChart.update();

  // Filter author data
  const authRows = DATA.authors.filter(d => isAll || d.repo === repo);
  const authByName = {{}};
  authRows.forEach(d => {{
    if (!authByName[d.author]) authByName[d.author] = {{ total: 0, ai: 0, bugs: 0, features: 0 }};
    authByName[d.author].total += d.total;
    authByName[d.author].ai += d.ai_count;
    authByName[d.author].bugs += d.bugs;
    authByName[d.author].features += d.features;
  }});
  const authSorted = Object.entries(authByName).sort((a, b) => b[1].total - a[1].total);
  const tbody = document.getElementById('authorBody');
  tbody.innerHTML = authSorted.map(([name, s]) => {{
    const pct = s.total > 0 ? Math.round(s.ai / s.total * 1000) / 10 : 0;
    return `<tr><td>${{name}}</td><td>${{s.total}}</td><td>${{pct}}%</td><td>${{s.bugs}}</td><td>${{s.features}}</td></tr>`;
  }}).join('');

  // Summary cards
  const sumRows = DATA.repoSummary.filter(d => isAll || d.repo === repo);
  let total = 0, aiCount = 0, bugs = 0, features = 0;
  const contribs = new Set();
  sumRows.forEach(d => {{
    total += d.total; aiCount += d.ai_count; bugs += d.bugs; features += d.features;
  }});
  authSorted.forEach(([name]) => contribs.add(name));

  document.getElementById('cardTotal').textContent = total;
  document.getElementById('cardAI').textContent = (total > 0 ? Math.round(aiCount / total * 1000) / 10 : 0) + '%';
  document.getElementById('cardBF').textContent = features > 0 ? (bugs / features).toFixed(2) : bugs;
  document.getElementById('cardContrib').textContent = contribs.size;
}}

// Initial render
applyFilter();
</script>
</body>
</html>
"""


def generate(output_dir: str = "docs/") -> None:
    conn = db.get_connection()
    db.init_db(conn)

    repos = db.repo_list(conn)
    weekly_ai = db.per_repo_weekly_ai_stats(conn)
    weekly_bf = db.per_repo_weekly_bf_stats(conn)
    authors = db.per_repo_author_stats(conn)
    repo_summary = db.per_repo_summary(conn)
    conn.close()

    all_data = {
        "weeklyAI": [{"repo": r["repo"], "week": r["week"], "total": r["total"], "ai_count": r["ai_count"]} for r in weekly_ai],
        "weeklyBF": [{"repo": r["repo"], "week": r["week"], "bugs": r["bugs"], "features": r["features"]} for r in weekly_bf],
        "authors": [{"repo": r["repo"], "author": r["author"], "total": r["total"], "ai_count": r["ai_count"], "bugs": r["bugs"], "features": r["features"]} for r in authors],
        "repoSummary": [{"repo": r["repo"], "total": r["total"], "ai_count": r["ai_count"], "bugs": r["bugs"], "features": r["features"], "contributors": r["contributors"]} for r in repo_summary],
    }

    last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = TEMPLATE.format(
        last_updated=last_updated,
        repos_json=json.dumps(repos),
        all_data_json=json.dumps(all_data),
    )

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "index.html").write_text(html)
    print(f"Dashboard written to {out_path / 'index.html'}")


def _esc(s: str | None) -> str:
    if not s:
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
