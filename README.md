# commit-intel

Commit Intelligence for the Trailblaze-work GitHub org. Scans repos, classifies commits (AI-assisted, bug fixes, features), and generates static HTML dashboards.

## Setup

```bash
pip install -r requirements.txt
```

For Ollama classification (optional, more accurate):
```bash
ollama pull qwen2.5:3b
```

## Usage

### Scan commits from the org

```bash
# Requires a GitHub PAT with repo + read:org scopes
export GITHUB_TOKEN=ghp_...

# Scan last 6 months (default)
python -m commit_intel scan --org Trailblaze-work

# Scan last 1 month
python -m commit_intel scan --org Trailblaze-work --months 1
```

### Classify commits

```bash
# Fast heuristic classification (pattern matching)
python -m commit_intel analyze --mode heuristic

# Ollama LLM classification (more accurate, requires local Ollama)
python -m commit_intel analyze --mode ollama --model qwen2.5:3b
```

### Generate dashboard

```bash
python -m commit_intel dashboard --output docs/
```

### All-in-one (scan + heuristic + dashboard)

```bash
python -m commit_intel run --org Trailblaze-work
```

## CI / GitHub Actions

The included workflow (`.github/workflows/scan.yml`) runs hourly:
1. Scans for new commits
2. Classifies with heuristics
3. Regenerates the dashboard
4. Commits updated data and HTML

Requires an `ORG_TOKEN` secret (PAT with `repo` + `read:org` scopes).

## Architecture

- **scanner.py** -- GitHub API via PyGithub, incremental fetching
- **analyzer.py** -- Heuristic pattern matching + Ollama LLM classification
- **dashboard.py** -- Static HTML generation with Chart.js
- **db.py** -- SQLite schema and query layer

## Metrics

1. **AI Adoption Rate** -- % of human commits authored with AI tools (Copilot, Claude, Codex, Cursor, etc.) week-by-week
2. **Bug Fix vs Feature Ratio** -- Distinct bugs and features per commit, tracked weekly

Bot commits (dependabot, renovate, etc.) are excluded from all metrics.

## Hosting

The dashboard is generated as static HTML in `docs/`. Serve it with:

```bash
python -m http.server -d docs/
```

Or deploy to Cloudflare Pages, Vercel, or any static hosting.
