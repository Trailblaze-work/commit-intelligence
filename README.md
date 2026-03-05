# commit-intelligence

Scan a GitHub org's repos, classify every commit with a local LLM, and generate a static dashboard tracking AI adoption and bug/feature ratios over time.

## What it does

- Incrementally scans all repos in a GitHub org (only fetches new commits since last run)
- Classifies each commit using a local Ollama LLM: AI-assisted? which tool? bug fix or feature?
- Stores everything in a SQLite database (committed to repo for portability)
- Generates a self-contained HTML dashboard with Chart.js charts and a searchable repo picker
- Bot commits (dependabot, renovate, github-actions, etc.) and merge commits are excluded from all metrics

## Prerequisites

- Python 3.12+
- [Ollama](https://ollama.com) installed and running locally
- A GitHub PAT with `repo` + `read:org` scopes

## Setup

```bash
# Clone and install
git clone <this-repo>
cd commit-intelligence
pip install -r requirements.txt

# Pull the LLM model
ollama pull qwen2.5:3b

# Configure your token
echo "GITHUB_TOKEN=ghp_your_token_here" > .env
```

## Usage

### Adapting for your org

Replace `Trailblaze-work` with your org name in all commands below and in `.github/workflows/scan.yml`.

### Step-by-step

```bash
# 1. Scan commits (last 6 months by default)
python -m commit_intelligence scan --org YOUR-ORG

# 2. Classify with Ollama
python -m commit_intelligence analyze

# 3. Generate dashboard
python -m commit_intelligence dashboard
```

### All-in-one

```bash
python -m commit_intelligence run --org YOUR-ORG
```

### Options

```
scan   --org ORG  --token TOKEN  --months N (default: 6)
analyze           --model MODEL  (default: qwen2.5:3b)
dashboard         --output DIR   (default: docs/)
run    --org ORG  --token TOKEN  --months N  --model MODEL  --output DIR
```

The token can also be set via the `GITHUB_TOKEN` environment variable or a `.env` file.

## Dashboard

Open `docs/index.html` in a browser, or serve it:

```bash
python -m http.server -d docs/
```

The dashboard shows:
- Summary cards (total commits, AI adoption %, bug/feature ratio, contributors)
- Weekly AI adoption trend (line chart)
- Weekly bugs vs features (stacked bar chart)
- Per-author breakdown table
- Repo filter with search/autocomplete to view any of the above per-repo

## Automated updates (GitHub Actions)

The included workflow (`.github/workflows/scan.yml`) runs hourly:

1. Installs Ollama and pulls the model
2. Scans for new commits since last run
3. Classifies them with the LLM
4. Regenerates the dashboard
5. Commits updated `data/` and `docs/` back to the repo

### Setup

1. Create a GitHub PAT (classic) with `repo` + `read:org` scopes
2. Add it as a repository secret named `ORG_TOKEN`
3. Update the `--org` value in the workflow file to match your org

Since commits are processed incrementally, the hourly job is fast -- typically only a handful of new commits to analyze.

## Author deduplication

The database includes an `author_aliases` table that maps email addresses to canonical display names. When a person commits from multiple emails, update the alias:

```bash
sqlite3 data/commits.db "UPDATE author_aliases SET canonical_name = 'preferred-name' WHERE email = 'other@email.com'"
```

New emails are auto-registered during scanning with the GitHub login as the default name.

## Architecture

```
commit_intelligence/
  __main__.py    CLI entry point (argparse + dotenv)
  scanner.py     GitHub API -> SQLite (incremental via last_scanned_at)
  analyzer.py    Ollama LLM classification (heuristic fallback on errors)
  dashboard.py   SQLite -> static HTML with Chart.js
  db.py          Schema, queries, author aliases
```

## Dependencies

- **PyGithub** -- GitHub API client
- **ollama** -- Ollama Python client
- **python-dotenv** -- .env file loading
- Everything else is stdlib (sqlite3, json, argparse, etc.)
