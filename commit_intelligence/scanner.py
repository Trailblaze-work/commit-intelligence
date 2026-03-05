"""GitHub API and local git scanner -- fetches commits from repos."""

import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from github import Github
from github.GithubException import GithubException

from . import db

BOT_LOGINS = {
    "dependabot[bot]",
    "renovate[bot]",
    "github-actions[bot]",
    "snyk-bot",
    "greenkeeper[bot]",
    "imgbot[bot]",
    "codecov[bot]",
    "mergify[bot]",
    "allcontributors[bot]",
}


def is_bot(login: str | None, email: str | None) -> bool:
    if login and (login in BOT_LOGINS or login.endswith("[bot]")):
        return True
    if email and "[bot]" in email:
        return True
    return False


def is_merge_commit(message: str | None, parents_count: int) -> bool:
    if parents_count > 1:
        return True
    if message and message.startswith("Merge "):
        return True
    return False


def scan(org_name: str, token: str | None = None, months: int = 6) -> None:
    token = token or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Error: GitHub token required (--token or GITHUB_TOKEN env var)")

    g = Github(token, per_page=100)
    org = g.get_organization(org_name)
    conn = db.get_connection()
    db.init_db(conn)

    since_default = datetime.now(timezone.utc) - timedelta(days=months * 30)
    repos = list(org.get_repos())
    print(f"Found {len(repos)} repos in {org_name}")

    for repo in repos:
        repo_id = db.upsert_repo(conn, repo.name, repo.full_name, repo.default_branch)
        last_scanned = db.get_repo_last_scanned(conn, repo.name)

        if last_scanned:
            since = datetime.fromisoformat(last_scanned).replace(tzinfo=timezone.utc)
        else:
            since = since_default

        print(f"  Scanning {repo.full_name} (since {since.date()})...", end=" ", flush=True)

        count = 0
        try:
            commits = repo.get_commits(since=since)
            for commit in commits:
                sha = commit.sha
                git_commit = commit.commit

                author_name = git_commit.author.name if git_commit.author else None
                author_email = git_commit.author.email if git_commit.author else None
                author_login = commit.author.login if commit.author else None
                committed_at = git_commit.committer.date.isoformat() if git_commit.committer else git_commit.author.date.isoformat()
                message = git_commit.message
                parents_count = len(commit.parents)

                bot = is_bot(author_login, author_email)
                merge = is_merge_commit(message, parents_count)

                db.ensure_alias(conn, author_email, author_login, author_name)
                db.insert_commit(
                    conn, repo_id, sha, author_name, author_email, author_login,
                    committed_at, message, merge, bot,
                )
                count += 1
        except GithubException as e:
            print(f"error ({e.status}: {e.data.get('message', '')})")
            continue

        conn.commit()
        now = datetime.now(timezone.utc).isoformat()
        db.update_repo_scanned(conn, repo.name, now)
        print(f"{count} commits")

    conn.close()
    print("Scan complete.")


def scan_local(repos_dir: str, org_name: str = "local",
               since_date: str | None = None) -> None:
    """Scan local git repos on disk instead of using the GitHub API."""
    repos_path = Path(repos_dir).resolve()
    if not repos_path.is_dir():
        raise SystemExit(f"Error: {repos_path} is not a directory")

    conn = db.get_connection()
    db.init_db(conn)

    if since_date:
        since_default = datetime.fromisoformat(since_date).replace(tzinfo=timezone.utc)
    else:
        since_default = datetime.now(timezone.utc) - timedelta(days=180)

    # Find all subdirectories that contain a .git folder
    repo_dirs = sorted(
        d for d in repos_path.iterdir()
        if d.is_dir() and (d / ".git").exists()
    )
    print(f"Found {len(repo_dirs)} local repos in {repos_path}")

    # git log format: SHA\x1fauthor_name\x1fauthor_email\x1fISO date\x1fparent_count\x1fsubject+body
    LOG_FORMAT = "%H%x1f%an%x1f%ae%x1f%aI%x1f%P%x1f%B"
    RECORD_SEP = "---commit-sep---"

    for repo_dir in repo_dirs:
        name = repo_dir.name
        full_name = f"{org_name}/{name}"

        # Detect default branch
        result = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=repo_dir, capture_output=True, text=True
        )
        default_branch = result.stdout.strip() if result.returncode == 0 else None

        repo_id = db.upsert_repo(conn, name, full_name, default_branch)
        last_scanned = db.get_repo_last_scanned(conn, name)

        if last_scanned:
            since = datetime.fromisoformat(last_scanned).replace(tzinfo=timezone.utc)
        else:
            since = since_default

        since_str = since.strftime("%Y-%m-%dT%H:%M:%S")

        print(f"  Scanning {name} (since {since.date()})...", end=" ", flush=True)

        cmd = [
            "git", "log", "--all",
            f"--since={since_str}",
            f"--format={RECORD_SEP}{LOG_FORMAT}",
        ]
        result = subprocess.run(
            cmd, cwd=repo_dir, capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            print(f"error: {result.stderr.strip()}")
            continue

        count = 0
        for record in result.stdout.split(RECORD_SEP):
            record = record.strip()
            if not record:
                continue
            parts = record.split("\x1f", 5)
            if len(parts) < 6:
                continue

            sha, author_name, author_email, date_str, parents_str, message = parts
            parents_count = len(parents_str.split()) if parents_str.strip() else 0
            # Normalize date
            try:
                committed_at = datetime.fromisoformat(date_str).isoformat()
            except ValueError:
                committed_at = date_str

            bot = is_bot(None, author_email)
            merge = is_merge_commit(message, parents_count)

            db.ensure_alias(conn, author_email, None, author_name)
            db.insert_commit(
                conn, repo_id, sha, author_name, author_email, None,
                committed_at, message.strip(), merge, bot,
            )
            count += 1

        conn.commit()
        now = datetime.now(timezone.utc).isoformat()
        db.update_repo_scanned(conn, name, now)
        print(f"{count} commits")

    conn.close()
    print("Local scan complete.")


def backfill_sizes(repos_dir: str) -> None:
    """Extract lines added/removed and files changed for commits missing size data."""
    import json as json_mod
    repos_path = Path(repos_dir).resolve()
    conn = db.get_connection()
    db.init_db(conn)

    # Get commits missing size data, grouped by repo
    rows = conn.execute("""
        SELECT c.sha, r.name FROM commits c
        JOIN repos r ON c.repo_id = r.id
        WHERE c.lines_added IS NULL AND c.is_merge = 0
        ORDER BY r.name
    """).fetchall()

    if not rows:
        print("No commits need size backfill.")
        conn.close()
        return

    # Group by repo
    by_repo: dict[str, list[str]] = {}
    for r in rows:
        by_repo.setdefault(r["name"], []).append(r["sha"])

    print(f"Backfilling sizes for {len(rows)} commits across {len(by_repo)} repos...")

    total = 0
    for repo_name, shas in by_repo.items():
        repo_dir = repos_path / repo_name
        if not (repo_dir / ".git").exists():
            continue

        print(f"  {repo_name} ({len(shas)} commits)...", end=" ", flush=True)
        count = 0

        for sha in shas:
            result = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "--numstat", "-r", sha],
                cwd=repo_dir, capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                continue

            added = 0
            removed = 0
            files = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    a, r_val, fname = parts[0], parts[1], parts[2]
                    # Binary files show as "-"
                    added += int(a) if a != "-" else 0
                    removed += int(r_val) if r_val != "-" else 0
                    files.append(fname)

            files_json = json_mod.dumps(files) if files else None
            db.update_commit_size(conn, sha, added, removed, files_json)
            count += 1

        conn.commit()
        total += count
        print(f"{count} done")

    conn.close()
    print(f"Size backfill complete: {total} commits updated.")
