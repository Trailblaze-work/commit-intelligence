"""Generate static HTML dashboard from commit data."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from . import db

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "dashboard.html"


def generate(output_dir: str = "docs/") -> None:
    conn = db.get_connection()
    db.init_db(conn)

    repos = db.repo_list(conn)
    weekly_ai = db.per_repo_weekly_ai_stats(conn)
    weekly_bf = db.per_repo_weekly_bf_stats(conn)
    authors = db.per_repo_author_stats(conn)
    repo_summary = db.per_repo_summary(conn)
    commit_size = db.per_repo_weekly_commit_size(conn)
    author_freq = db.per_repo_author_frequency(conn)
    fix_rate = db.fix_after_commit_stats(conn)
    ai_tools = db.per_repo_weekly_ai_tool_stats(conn)
    dates = db.date_range(conn)
    conn.close()

    all_data = {
        "weeklyAI": [{"repo": r["repo"], "week": r["week"], "total": r["total"], "ai_count": r["ai_count"]} for r in weekly_ai],
        "aiTools": [{"repo": r["repo"], "week": r["week"], "tool": r["tool"], "count": r["count"]} for r in ai_tools],
        "weeklyBF": [{"repo": r["repo"], "week": r["week"], "bugs": r["bugs"], "features": r["features"]} for r in weekly_bf],
        "authors": [{"repo": r["repo"], "author": r["author"], "total": r["total"], "ai_count": r["ai_count"], "bugs": r["bugs"], "features": r["features"]} for r in authors],
        "repoSummary": [{"repo": r["repo"], "total": r["total"], "ai_count": r["ai_count"], "bugs": r["bugs"], "features": r["features"], "contributors": r["contributors"]} for r in repo_summary],
        "commitSize": [{"repo": r["repo"], "week": r["week"], "avg_size": r["avg_size"], "commit_count": r["commit_count"]} for r in commit_size],
        "authorFreq": [{"repo": r["repo"], "author": r["author"], "week": r["week"], "commits": r["commits"]} for r in author_freq],
        "fixRate": [{"repo": r["repo"], "week": r["week"], "total_commits": r["total_commits"], "followed_by_fix": r["followed_by_fix"]} for r in fix_rate],
        "dateRange": {"earliest": dates["earliest"][:10] if dates["earliest"] else "", "latest": dates["latest"][:10] if dates["latest"] else ""},
    }

    now = datetime.now(timezone.utc)
    last_updated = now.strftime("%Y-%m-%d %H:%M UTC")
    expires = (now + timedelta(minutes=50)).strftime("%a, %d %b %Y %H:%M:%S GMT")

    html = TEMPLATE_PATH.read_text()
    replacements = {
        "%%LAST_UPDATED%%": last_updated,
        "%%EXPIRES%%": expires,
        "%%REPOS_JSON%%": json.dumps(repos),
        "%%ALL_DATA_JSON%%": json.dumps(all_data),
    }
    for key, value in replacements.items():
        html = html.replace(key, value)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "index.html").write_text(html)
    print(f"Dashboard written to {out_path / 'index.html'}")
