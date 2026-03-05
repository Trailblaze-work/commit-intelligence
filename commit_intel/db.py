"""SQLite schema and query functions for commit-intel."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "commits.db"


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            default_branch TEXT,
            last_scanned_at TEXT,
            last_analyzed_sha TEXT,
            last_analyzed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS commits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_id INTEGER NOT NULL REFERENCES repos(id),
            sha TEXT UNIQUE NOT NULL,
            author_name TEXT,
            author_email TEXT,
            author_login TEXT,
            committed_at TEXT NOT NULL,
            message TEXT,
            is_merge INTEGER DEFAULT 0,
            is_bot INTEGER DEFAULT 0,
            ai_assisted INTEGER,
            ai_tool TEXT,
            ai_confidence REAL,
            bug_count INTEGER,
            feature_count INTEGER,
            analysis_mode TEXT,
            analyzed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_commits_date ON commits(committed_at);
        CREATE INDEX IF NOT EXISTS idx_commits_analyzed ON commits(analyzed_at);

        -- Maps (author_email) to a canonical display name.
        -- Populated automatically from scan data; edit rows to merge identities.
        CREATE TABLE IF NOT EXISTS author_aliases (
            email TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL
        );
    """)
    conn.commit()


def upsert_repo(conn: sqlite3.Connection, name: str, full_name: str,
                 default_branch: str | None) -> int:
    conn.execute(
        "INSERT INTO repos (name, full_name, default_branch) VALUES (?, ?, ?) "
        "ON CONFLICT(name) DO UPDATE SET full_name=excluded.full_name, "
        "default_branch=excluded.default_branch",
        (name, full_name, default_branch),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM repos WHERE name = ?", (name,)).fetchone()
    return row["id"]


def get_repo_last_scanned(conn: sqlite3.Connection, repo_name: str) -> str | None:
    row = conn.execute(
        "SELECT last_scanned_at FROM repos WHERE name = ?", (repo_name,)
    ).fetchone()
    return row["last_scanned_at"] if row else None


def update_repo_scanned(conn: sqlite3.Connection, repo_name: str, ts: str) -> None:
    conn.execute(
        "UPDATE repos SET last_scanned_at = ? WHERE name = ?", (ts, repo_name)
    )
    conn.commit()


def update_repo_analyzed(conn: sqlite3.Connection, repo_id: int,
                         sha: str, ts: str) -> None:
    conn.execute(
        "UPDATE repos SET last_analyzed_sha = ?, last_analyzed_at = ? WHERE id = ?",
        (sha, ts, repo_id),
    )
    conn.commit()


def ensure_alias(conn: sqlite3.Connection, email: str | None,
                  login: str | None, name: str | None) -> None:
    """Register an author email if not already mapped. Uses login or name as default."""
    if not email:
        return
    existing = conn.execute(
        "SELECT 1 FROM author_aliases WHERE email = ?", (email,)
    ).fetchone()
    if existing:
        return
    canonical = login or name or email
    conn.execute(
        "INSERT OR IGNORE INTO author_aliases (email, canonical_name) VALUES (?, ?)",
        (email, canonical),
    )


def insert_commit(conn: sqlite3.Connection, repo_id: int, sha: str,
                  author_name: str | None, author_email: str | None,
                  author_login: str | None, committed_at: str,
                  message: str | None, is_merge: bool, is_bot: bool) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO commits "
        "(repo_id, sha, author_name, author_email, author_login, committed_at, "
        "message, is_merge, is_bot) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (repo_id, sha, author_name, author_email, author_login, committed_at,
         message, int(is_merge), int(is_bot)),
    )


def get_unanalyzed_commits(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, sha, repo_id, message FROM commits "
        "WHERE analyzed_at IS NULL ORDER BY committed_at"
    ).fetchall()


def update_commit_analysis(conn: sqlite3.Connection, commit_id: int,
                           ai_assisted: int, ai_tool: str, ai_confidence: float,
                           bug_count: int, feature_count: int,
                           analysis_mode: str, analyzed_at: str) -> None:
    conn.execute(
        "UPDATE commits SET ai_assisted=?, ai_tool=?, ai_confidence=?, "
        "bug_count=?, feature_count=?, analysis_mode=?, analyzed_at=? "
        "WHERE id=?",
        (ai_assisted, ai_tool, ai_confidence, bug_count, feature_count,
         analysis_mode, analyzed_at, commit_id),
    )


# --- Dashboard queries ---

def weekly_ai_stats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT strftime('%Y-W%W', committed_at) AS week,
               COUNT(*) AS total,
               SUM(CASE WHEN ai_assisted = 1 THEN 1 ELSE 0 END) AS ai_count
        FROM commits
        WHERE is_bot = 0 AND analyzed_at IS NOT NULL
        GROUP BY week
        ORDER BY week
    """).fetchall()


def weekly_bugfix_feature_stats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT strftime('%Y-W%W', committed_at) AS week,
               SUM(COALESCE(bug_count, 0)) AS bugs,
               SUM(COALESCE(feature_count, 0)) AS features
        FROM commits
        WHERE is_bot = 0 AND analyzed_at IS NOT NULL
        GROUP BY week
        ORDER BY week
    """).fetchall()


_AUTHOR_EXPR = "COALESCE(a.canonical_name, c.author_login, c.author_name)"
_AUTHOR_JOIN = "LEFT JOIN author_aliases a ON c.author_email = a.email"


def author_stats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(f"""
        SELECT {_AUTHOR_EXPR} AS author,
               COUNT(*) AS total,
               SUM(CASE WHEN c.ai_assisted = 1 THEN 1 ELSE 0 END) AS ai_count,
               SUM(COALESCE(c.bug_count, 0)) AS bugs,
               SUM(COALESCE(c.feature_count, 0)) AS features
        FROM commits c
        {_AUTHOR_JOIN}
        WHERE c.is_bot = 0 AND c.analyzed_at IS NOT NULL
        GROUP BY author
        ORDER BY total DESC
    """).fetchall()


def summary_stats(conn: sqlite3.Connection) -> dict:
    row = conn.execute(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN c.ai_assisted = 1 THEN 1 ELSE 0 END) AS ai_count,
               SUM(COALESCE(c.bug_count, 0)) AS bugs,
               SUM(COALESCE(c.feature_count, 0)) AS features,
               COUNT(DISTINCT {_AUTHOR_EXPR}) AS contributors
        FROM commits c
        {_AUTHOR_JOIN}
        WHERE c.is_bot = 0 AND c.analyzed_at IS NOT NULL
    """).fetchone()
    return dict(row)
