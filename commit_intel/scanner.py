"""GitHub API scanner -- fetches commits from all repos in an org."""

import os
from datetime import datetime, timedelta, timezone

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
