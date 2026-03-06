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
            is_first_parent INTEGER DEFAULT 0,
            ai_assisted INTEGER,
            ai_tool TEXT,
            ai_confidence REAL,
            bug_count INTEGER,
            feature_count INTEGER,
            analysis_mode TEXT,
            analyzed_at TEXT,
            lines_added INTEGER,
            lines_removed INTEGER,
            files_changed TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_commits_date ON commits(committed_at);
        CREATE INDEX IF NOT EXISTS idx_commits_analyzed ON commits(analyzed_at);
        CREATE INDEX IF NOT EXISTS idx_commits_first_parent ON commits(is_first_parent);

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


def _normalize_name(name: str) -> str:
    """Normalize a name for fuzzy matching: lowercase, strip accents, remove separators."""
    import unicodedata
    # NFD decompose, strip combining marks (accents)
    nfkd = unicodedata.normalize("NFKD", name.lower())
    ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Remove common separators
    for ch in "-_. ":
        ascii_name = ascii_name.replace(ch, "")
    return ascii_name


def ensure_alias(conn: sqlite3.Connection, email: str | None,
                  login: str | None, name: str | None) -> None:
    """Register an author email if not already mapped.
    Auto-merges with existing aliases when the email local part or author name
    matches an existing canonical name (fuzzy)."""
    if not email:
        return
    existing = conn.execute(
        "SELECT 1 FROM author_aliases WHERE email = ?", (email,)
    ).fetchone()
    if existing:
        return

    canonical = login or name or email

    # Try to find an existing alias with a matching name
    all_aliases = conn.execute(
        "SELECT canonical_name FROM author_aliases"
    ).fetchall()
    norm_candidates = {_normalize_name(r["canonical_name"]): r["canonical_name"]
                       for r in all_aliases}

    # Check if any existing canonical name matches the new name, login, or email local part
    email_local = email.split("@")[0].split("+")[-1]  # strip noreply prefix like 12345+user
    for probe in [name, login, email_local]:
        if probe:
            norm = _normalize_name(probe)
            if norm and norm in norm_candidates:
                canonical = norm_candidates[norm]
                break

    conn.execute(
        "INSERT OR IGNORE INTO author_aliases (email, canonical_name) VALUES (?, ?)",
        (email, canonical),
    )


def insert_commit(conn: sqlite3.Connection, repo_id: int, sha: str,
                  author_name: str | None, author_email: str | None,
                  author_login: str | None, committed_at: str,
                  message: str | None, is_merge: bool, is_bot: bool,
                  is_first_parent: bool = False) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO commits "
        "(repo_id, sha, author_name, author_email, author_login, committed_at, "
        "message, is_merge, is_bot, is_first_parent) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (repo_id, sha, author_name, author_email, author_login, committed_at,
         message, int(is_merge), int(is_bot), int(is_first_parent)),
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
        SELECT date(committed_at, 'weekday 0', '-6 days') AS week,
               COUNT(*) AS total,
               SUM(CASE WHEN ai_assisted = 1 THEN 1 ELSE 0 END) AS ai_count
        FROM commits
        WHERE is_bot = 0 AND is_merge = 0 AND analyzed_at IS NOT NULL
              AND committed_at >= '2026-01-01'
        GROUP BY week
        ORDER BY week
    """).fetchall()


def weekly_bugfix_feature_stats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT date(committed_at, 'weekday 0', '-6 days') AS week,
               SUM(COALESCE(bug_count, 0)) AS bugs,
               SUM(COALESCE(feature_count, 0)) AS features
        FROM commits
        WHERE is_bot = 0 AND is_merge = 0 AND analyzed_at IS NOT NULL
              AND committed_at >= '2026-01-01'
        GROUP BY week
        ORDER BY week
    """).fetchall()


_AUTHOR_EXPR = "COALESCE(a.canonical_name, c.author_login, c.author_name)"
_AUTHOR_JOIN = "LEFT JOIN author_aliases a ON c.author_email = a.email"
_WHERE_HUMAN = "c.is_bot = 0 AND c.is_merge = 0 AND c.analyzed_at IS NOT NULL AND c.committed_at >= '2026-01-01'"


def author_stats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(f"""
        SELECT {_AUTHOR_EXPR} AS author,
               COUNT(*) AS total,
               SUM(CASE WHEN c.ai_assisted = 1 THEN 1 ELSE 0 END) AS ai_count,
               SUM(COALESCE(c.bug_count, 0)) AS bugs,
               SUM(COALESCE(c.feature_count, 0)) AS features
        FROM commits c
        {_AUTHOR_JOIN}
        WHERE {_WHERE_HUMAN}
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
        WHERE {_WHERE_HUMAN}
    """).fetchone()
    return dict(row)


def date_range(conn: sqlite3.Connection) -> dict:
    """Return the earliest and latest commit dates in the analyzed dataset."""
    row = conn.execute(f"""
        SELECT MIN(c.committed_at) AS earliest,
               MAX(c.committed_at) AS latest
        FROM commits c
        {_AUTHOR_JOIN}
        WHERE {_WHERE_HUMAN}
    """).fetchone()
    return {"earliest": row["earliest"], "latest": row["latest"]}


def repo_list(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM repos ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def contributor_list(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(f"""
        SELECT DISTINCT {_AUTHOR_EXPR} AS author
        FROM commits c
        {_AUTHOR_JOIN}
        WHERE {_WHERE_HUMAN}
        ORDER BY author
    """).fetchall()
    return [r["author"] for r in rows]


def per_repo_weekly_ai_stats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(f"""
        SELECT r.name AS repo,
               {_AUTHOR_EXPR} AS author,
               date(c.committed_at, 'weekday 0', '-6 days') AS week,
               COUNT(*) AS total,
               SUM(CASE WHEN c.ai_assisted = 1 THEN 1 ELSE 0 END) AS ai_count
        FROM commits c
        JOIN repos r ON c.repo_id = r.id
        {_AUTHOR_JOIN}
        WHERE {_WHERE_HUMAN}
        GROUP BY repo, author, week
        ORDER BY repo, author, week
    """).fetchall()


def per_repo_weekly_ai_tool_stats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(f"""
        SELECT r.name AS repo,
               {_AUTHOR_EXPR} AS author,
               date(c.committed_at, 'weekday 0', '-6 days') AS week,
               c.ai_tool AS tool,
               COUNT(*) AS count
        FROM commits c
        JOIN repos r ON c.repo_id = r.id
        {_AUTHOR_JOIN}
        WHERE {_WHERE_HUMAN}
              AND c.ai_assisted = 1
              AND c.ai_tool IS NOT NULL AND c.ai_tool != 'none'
        GROUP BY repo, author, week, tool
        ORDER BY repo, author, week, tool
    """).fetchall()


def per_repo_weekly_bf_stats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(f"""
        SELECT r.name AS repo,
               {_AUTHOR_EXPR} AS author,
               date(c.committed_at, 'weekday 0', '-6 days') AS week,
               SUM(COALESCE(c.bug_count, 0)) AS bugs,
               SUM(COALESCE(c.feature_count, 0)) AS features
        FROM commits c
        JOIN repos r ON c.repo_id = r.id
        {_AUTHOR_JOIN}
        WHERE {_WHERE_HUMAN}
        GROUP BY repo, author, week
        ORDER BY repo, author, week
    """).fetchall()


def per_repo_author_stats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(f"""
        SELECT r.name AS repo,
               {_AUTHOR_EXPR} AS author,
               COUNT(*) AS total,
               SUM(CASE WHEN c.ai_assisted = 1 THEN 1 ELSE 0 END) AS ai_count,
               SUM(COALESCE(c.bug_count, 0)) AS bugs,
               SUM(COALESCE(c.feature_count, 0)) AS features
        FROM commits c
        JOIN repos r ON c.repo_id = r.id
        {_AUTHOR_JOIN}
        WHERE {_WHERE_HUMAN}
        GROUP BY repo, author
        ORDER BY repo, total DESC
    """).fetchall()


def per_repo_summary(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(f"""
        SELECT r.name AS repo,
               {_AUTHOR_EXPR} AS author,
               COUNT(*) AS total,
               SUM(CASE WHEN c.ai_assisted = 1 THEN 1 ELSE 0 END) AS ai_count,
               SUM(COALESCE(c.bug_count, 0)) AS bugs,
               SUM(COALESCE(c.feature_count, 0)) AS features
        FROM commits c
        JOIN repos r ON c.repo_id = r.id
        {_AUTHOR_JOIN}
        WHERE {_WHERE_HUMAN}
        GROUP BY repo, author
        ORDER BY total DESC
    """).fetchall()


def per_repo_weekly_commit_size(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(f"""
        SELECT r.name AS repo,
               {_AUTHOR_EXPR} AS author,
               date(c.committed_at, 'weekday 0', '-6 days') AS week,
               AVG(COALESCE(c.lines_added, 0) + COALESCE(c.lines_removed, 0)) AS avg_size,
               SUM(COALESCE(c.lines_added, 0)) AS total_added,
               SUM(COALESCE(c.lines_removed, 0)) AS total_removed,
               COUNT(*) AS commit_count
        FROM commits c
        JOIN repos r ON c.repo_id = r.id
        {_AUTHOR_JOIN}
        WHERE {_WHERE_HUMAN}
              AND c.lines_added IS NOT NULL
        GROUP BY repo, author, week
        ORDER BY repo, author, week
    """).fetchall()


def per_repo_author_frequency(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Per author per week: commit count."""
    return conn.execute(f"""
        SELECT r.name AS repo,
               {_AUTHOR_EXPR} AS author,
               date(c.committed_at, 'weekday 0', '-6 days') AS week,
               COUNT(*) AS commits
        FROM commits c
        JOIN repos r ON c.repo_id = r.id
        {_AUTHOR_JOIN}
        WHERE {_WHERE_HUMAN}
        GROUP BY repo, author, week
        ORDER BY repo, author, week
    """).fetchall()


FIX_AFTER_COMMIT_WINDOW_HOURS = 48

def fix_after_commit_stats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """For each repo+author+week, count commits that were followed by a fix commit
    (classified as bug_count > 0) touching the same files within 48 hours."""
    return conn.execute(f"""
        SELECT r.name AS repo,
               COALESCE(a.canonical_name, c1.author_login, c1.author_name) AS author,
               date(c1.committed_at, 'weekday 0', '-6 days') AS week,
               COUNT(DISTINCT c1.sha) AS total_commits,
               COUNT(DISTINCT CASE
                   WHEN c1.files_changed IS NOT NULL AND EXISTS (
                       SELECT 1 FROM commits c2
                       WHERE c2.repo_id = c1.repo_id
                         AND c2.committed_at > c1.committed_at
                         AND (julianday(c2.committed_at) - julianday(c1.committed_at)) * 24
                             <= {FIX_AFTER_COMMIT_WINDOW_HOURS}
                         AND c2.bug_count > 0
                         AND c2.is_bot = 0 AND c2.is_first_parent = 1
                         AND c2.files_changed IS NOT NULL
                         AND EXISTS (
                             SELECT value FROM json_each(c2.files_changed)
                             WHERE value IN (SELECT value FROM json_each(c1.files_changed))
                         )
                   ) THEN c1.sha END
               ) AS followed_by_fix
        FROM commits c1
        JOIN repos r ON c1.repo_id = r.id
        LEFT JOIN author_aliases a ON c1.author_email = a.email
        WHERE c1.is_bot = 0 AND c1.is_first_parent = 1 AND c1.analyzed_at IS NOT NULL
              AND c1.committed_at >= '2026-01-01'
        GROUP BY repo, author, week
        ORDER BY repo, author, week
    """).fetchall()


def update_commit_size(conn: sqlite3.Connection, sha: str,
                       lines_added: int, lines_removed: int,
                       files_changed: str | None) -> None:
    conn.execute(
        "UPDATE commits SET lines_added=?, lines_removed=?, files_changed=? WHERE sha=?",
        (lines_added, lines_removed, files_changed, sha),
    )
