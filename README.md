# Trailblaze Commit Intelligence

Scan a GitHub org's repos, classify every commit with heuristics, and generate a static dashboard tracking AI tool adoption and bug/feature ratios over time.

## What it does

- Scans repos from a GitHub org (via API) or from local git clones on disk
- Incrementally fetches only new commits since last run
- Classifies each commit using pattern matching: AI-assisted? which tool? bug fix or feature?
- Deduplicates authors via heuristics (merges multiple emails/names per person)
- Stores everything in a SQLite database
- Generates a self-contained HTML dashboard with Chart.js charts and a searchable repo picker
- Bot commits (dependabot, renovate, github-actions, etc.) and merge commits are excluded from all metrics

## Setup

- Python 3.12+
- For GitHub API scanning: a PAT with `repo` + `read:org` scopes

```bash
pip install -r requirements.txt
echo "GITHUB_TOKEN=ghp_your_token_here" > .env
```

## Usage

```bash
# All-in-one from GitHub API
python -m commit_intelligence run --org YOUR-ORG

# All-in-one from local git repos
python -m commit_intelligence run-local --path /path/to/repos --org my-org --since 2026-01-01
```

Individual steps are also available if needed:

```bash
python -m commit_intelligence scan --org YOUR-ORG
python -m commit_intelligence scan-local --path /path/to/repos --org my-org --since 2026-01-01
python -m commit_intelligence analyze
python -m commit_intelligence deduplicate-authors
python -m commit_intelligence backfill-sizes --path /path/to/repos
python -m commit_intelligence dashboard
```

## Dashboard

Open `docs/index.html` in a browser. The dashboard shows:

- AI tool adoption over time (stacked area: copilot, claude, cursor, etc.)
- Bug / feature ratio trend
- Commit size (avg lines changed per week)
- Commit frequency (commits per author per week)
- Fix-after-commit rate (% of commits followed by a fix to same files within 48h)
- Per-author breakdown table
- Repo filter with search/autocomplete

## Automated updates (GitHub Actions)

The included workflow (`.github/workflows/scan.yml`) runs hourly:

1. Scans for new commits since last run
2. Classifies them with heuristics
3. Deduplicates authors
4. Regenerates the dashboard
5. Commits updated `data/` and `docs/` back to the repo

### Setup

1. Create a GitHub PAT with `repo` + `read:org` scopes
2. Add it as a repository secret named `ORG_TOKEN`
3. Update the `--org` value in the workflow file