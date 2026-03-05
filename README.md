# Trailblaze Commit Intelligence

Scan a GitHub org's repos, classify every commit with heuristics, and generate a static dashboard tracking AI tool adoption and bug/feature ratios over time.

## What it does

- Scans repos from a GitHub org (via API) or from local git clones on disk
- Incrementally fetches only new commits since last run
- Classifies each commit using pattern matching: AI-assisted? which tool? bug fix or feature?
- Deduplicates authors via heuristics (merges multiple emails/names per person)
- Stores everything in a SQLite database (committed to repo for portability)
- Generates a self-contained HTML dashboard with Chart.js charts and a searchable repo picker
- Bot commits (dependabot, renovate, github-actions, etc.) and merge commits are excluded from all metrics

## Quick start (Docker)

```bash
docker build -t commit-intelligence .

# Scan local repos + analyze + generate dashboard
docker run \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/docs:/app/docs \
  -v /path/to/repos:/repos:ro \
  commit-intelligence scan-local --path /repos --org my-org --since 2026-01-01

docker run \
  -v $(pwd)/data:/app/data \
  commit-intelligence analyze

docker run \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/docs:/app/docs \
  commit-intelligence dashboard

# Or scan from GitHub API
docker run \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/docs:/app/docs \
  -e GITHUB_TOKEN=ghp_... \
  commit-intelligence run --org YOUR-ORG
```

## Local setup (without Docker)

### Prerequisites

- Python 3.12+
- For GitHub API scanning: a PAT with `repo` + `read:org` scopes

```bash
pip install -r requirements.txt
echo "GITHUB_TOKEN=ghp_your_token_here" > .env
```

### Usage

```bash
# Scan from local git repos (no token needed)
python -m commit_intelligence scan-local --path /path/to/repos --org my-org --since 2026-01-01

# Scan from GitHub API
python -m commit_intelligence scan --org YOUR-ORG

# Classify commits
python -m commit_intelligence analyze

# Deduplicate authors
python -m commit_intelligence deduplicate-authors

# Generate dashboard
python -m commit_intelligence dashboard

# All-in-one (GitHub API: scan + analyze + dashboard)
python -m commit_intelligence run --org YOUR-ORG
```

### First run

```bash
python -m commit_intelligence scan-local --path /path/to/repos --org my-org --since 2026-01-01
python -m commit_intelligence analyze
python -m commit_intelligence deduplicate-authors
python -m commit_intelligence backfill-sizes --path /path/to/repos
python -m commit_intelligence dashboard
```

After the initial backlog, commit `data/commits.db` to the repo. The CI job will then only process new commits.

## Dashboard

Open `docs/index.html` in a browser. The dashboard shows:

- AI tool adoption over time (stacked area: copilot, claude, cursor, etc.)
- Bug / feature ratio trend
- Commit size (avg lines changed per week)
- Commit frequency (commits per author per week)
- Fix-after-commit rate
- Per-author breakdown table
- Repo filter with search/autocomplete

## Automated updates (GitHub Actions)

The included workflow (`.github/workflows/scan.yml`) runs hourly:

1. Scans for new commits since last run
2. Classifies them with heuristics
3. Regenerates the dashboard
4. Commits updated `data/` and `docs/` back to the repo

### Setup

1. Create a GitHub PAT with `repo` + `read:org` scopes
2. Add it as a repository secret named `ORG_TOKEN`
3. Update the `--org` value in the workflow file

## Architecture

```
commit_intelligence/
  __main__.py        CLI entry point
  scanner.py         GitHub API + local git scanning
  analyzer.py        Heuristic classification + author deduplication
  dashboard.py       SQLite -> static HTML (template in templates/)
  db.py              Schema, queries, author aliases
  templates/
    dashboard.html   Dashboard HTML/CSS/JS template
```
