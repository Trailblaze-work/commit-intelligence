"""Commit classification -- heuristic pattern matching."""

import re
from datetime import datetime, timezone

from . import db

# --- AI detection patterns ---

AI_TOOL_PATTERNS = {
    "copilot": [
        r"(?i)co-authored-by:.*copilot",
        r"(?i)github\s*copilot",
        r"(?i)generated\s+by\s+copilot",
    ],
    "claude": [
        r"(?i)co-authored-by:.*claude",
        r"(?i)generated\s+by\s+claude",
        r"(?i)created\s+with\s+claude",
        r"(?i)\bclaude\s+(code|ai)\b",
    ],
    "codex": [
        r"(?i)co-authored-by:.*codex",
        r"(?i)openai\s*codex",
        r"(?i)generated\s+by\s+codex",
    ],
    "cursor": [
        r"(?i)co-authored-by:.*cursor",
        r"(?i)generated\s+by\s+cursor",
        r"(?i)\bcursor\s+(ai|ide)\b",
    ],
    "windsurf": [
        r"(?i)co-authored-by:.*windsurf",
        r"(?i)generated\s+by\s+windsurf",
        r"(?i)\bwindsurf\b",
    ],
}

GENERIC_AI_PATTERNS = [
    r"(?i)co-authored-by:.*\b(ai|bot|assistant)\b",
    r"(?i)generated\s+by\s+(ai|llm|gpt)",
    r"(?i)created\s+with\s+(ai|llm|gpt)",
    r"(?i)\bai[- ]generated\b",
    r"(?i)\bai[- ]assisted\b",
]

# --- Conventional commit prefix detection ---
# If message starts with a known prefix like "fix(...): " or "feat: ",
# use that as the authoritative signal instead of keyword scanning.

_CC_PREFIX = re.compile(
    r"^(?P<type>[a-z]+)"        # type: fix, feat, chore, etc.
    r"\s*"                      # optional space before scope
    r"(?:\([^)]*\))?"           # optional scope: (BUP-1234)
    r"(?:!)?"                   # optional breaking change marker
    r"\s*:\s*",                 # colon with optional surrounding whitespace
    re.IGNORECASE,
)

# Prefixes that indicate a bug fix
_CC_BUG_TYPES = {"fix", "bugfix", "hotfix"}
# Prefixes that indicate a feature
_CC_FEAT_TYPES = {"feat", "feature"}
# Prefixes that are never bugs or features (skip keyword scanning)
_CC_NEUTRAL_TYPES = {"chore", "ci", "docs", "style", "refactor", "perf",
                     "test", "tests", "build", "deploy", "release"}

# --- Fallback keyword patterns (used when no conventional commit prefix) ---

BUG_PATTERNS = [
    r"(?i)\bfix(?:e[ds])?\b",
    r"(?i)\bbug(?:fix)?\b",
    r"(?i)\bpatch(?:e[ds])?\b",
    r"(?i)\bhotfix\b",
    r"(?i)\bresolve[ds]?\b",
    r"(?i)\bclose[ds]?\s+#\d+",
    r"(?i)\bfix(?:e[ds])?\s+#\d+",
    r"(?i)\bcorrect(?:ions?|ed|s)?\b",
    r"(?i)\btypo\b",
]

FEATURE_PATTERNS = [
    r"(?i)\bfeat(?:ure)?(?:\(|[:\s!]|$)",
    r"(?i)\badd(?:e?d|s)?\s+\w",
    r"(?i)\bimplement(?:e?d|s)?\b",
    r"(?i)\bintroduce[ds]?\b",
    r"(?i)\bnew\s+\w",
]

# Patterns to exclude from keyword-based bug/feature matching (noise)
EXCLUDE_PATTERNS = [
    r"(?i)\bmerge\b",
    r"(?i)\brevert\b",
]


def _count_matches(message: str, patterns: list[str]) -> int:
    if not message:
        return 0
    count = 0
    for pattern in patterns:
        count += len(re.findall(pattern, message))
    return count


def classify_heuristic(message: str | None) -> dict:
    result = {
        "ai_assisted": 0,
        "ai_tool": "none",
        "ai_confidence": 0.0,
        "bug_count": 0,
        "feature_count": 0,
    }
    if not message:
        return result

    # AI detection (always runs, regardless of commit type)
    for tool, patterns in AI_TOOL_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, message):
                result["ai_assisted"] = 1
                result["ai_tool"] = tool
                result["ai_confidence"] = 0.9
                break
        if result["ai_assisted"]:
            break

    if not result["ai_assisted"]:
        for pattern in GENERIC_AI_PATTERNS:
            if re.search(pattern, message):
                result["ai_assisted"] = 1
                result["ai_tool"] = "other"
                result["ai_confidence"] = 0.7
                break

    # Conventional commit prefix: authoritative signal (takes priority)
    cc = _CC_PREFIX.match(message)
    if cc:
        cc_type = cc.group("type").lower()
        if cc_type in _CC_BUG_TYPES:
            result["bug_count"] = 1
        elif cc_type in _CC_FEAT_TYPES:
            result["feature_count"] = 1
        # Neutral types (chore, deploy, docs, etc.): no bug/feature
        return result

    # No conventional commit prefix: fall back to keyword scanning.
    # Skip noise commits (merge/revert) from keyword scanning only.
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, message):
            return result

    bug_signals = _count_matches(message, BUG_PATTERNS)
    if bug_signals > 0:
        result["bug_count"] = max(1, min(bug_signals, 5))

    feature_signals = _count_matches(message, FEATURE_PATTERNS)
    if feature_signals > 0:
        result["feature_count"] = max(1, min(feature_signals, 5))

    return result


def analyze() -> None:
    conn = db.get_connection()
    db.init_db(conn)
    commits = db.get_unanalyzed_commits(conn)

    if not commits:
        print("No unanalyzed commits.")
        conn.close()
        return

    print(f"Analyzing {len(commits)} commits with heuristics...")

    now = datetime.now(timezone.utc).isoformat()
    total_done = 0
    total = len(commits)
    last_by_repo: dict[int, str] = {}

    for c in commits:
        r = classify_heuristic(c["message"])

        db.update_commit_analysis(
            conn, c["id"],
            ai_assisted=r["ai_assisted"],
            ai_tool=r["ai_tool"],
            ai_confidence=r["ai_confidence"],
            bug_count=r["bug_count"],
            feature_count=r["feature_count"],
            analysis_mode="heuristic",
            analyzed_at=now,
        )
        last_by_repo[c["repo_id"]] = c["sha"]

        total_done += 1
        if total_done % 100 == 0:
            conn.commit()
            print(f"  {total_done}/{total} analyzed")

    conn.commit()

    for repo_id, sha in last_by_repo.items():
        db.update_repo_analyzed(conn, repo_id, sha, now)

    conn.close()
    ai_count = sum(1 for c in commits if classify_heuristic(c["message"])["ai_assisted"])
    print(f"Analysis complete: {total} commits, {ai_count} AI-assisted.")


def deduplicate_authors() -> None:
    conn = db.get_connection()
    db.init_db(conn)

    rows = conn.execute("""
        SELECT DISTINCT author_name, author_email, author_login
        FROM commits
        WHERE author_email IS NOT NULL AND is_bot = 0
        ORDER BY author_email
    """).fetchall()

    if not rows:
        print("No authors to deduplicate.")
        conn.close()
        return

    print(f"Deduplicating {len(rows)} author identities with heuristics...")

    # Build all (email, login, name) triples
    identities: list[dict] = []
    for r in rows:
        identities.append({
            "email": r["author_email"],
            "login": r["author_login"],
            "name": r["author_name"],
        })

    # Group by normalized identity signals
    groups = _group_identities(identities)

    updated = 0
    for canonical, emails in groups.items():
        for email in emails:
            conn.execute(
                "INSERT INTO author_aliases (email, canonical_name) VALUES (?, ?) "
                "ON CONFLICT(email) DO UPDATE SET canonical_name = excluded.canonical_name",
                (email, canonical),
            )
            updated += 1

    conn.commit()
    conn.close()

    group_count = sum(1 for emails in groups.values() if len(emails) > 1)
    print(f"Deduplication complete: {group_count} merged groups, {updated} aliases.")


def _group_identities(identities: list[dict]) -> dict[str, list[str]]:
    """Group author identities by matching signals.

    Matches on:
    - GitHub noreply username extracted from 12345+user@users.noreply.github.com
    - Email local part (first.last or username) across domains
    - Normalized author name (accent-stripped, lowercased)
    - Org-stripped GitHub usernames (e.g. "jane-acme" -> "jane") matched against
      first names from firstname.lastname@ emails at the same org domain
    """
    from .db import _normalize_name

    # Union-find for grouping emails
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Detect the org domain: most common non-freemail, non-noreply domain
    _FREEMAIL = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
                 "protonmail.com", "icloud.com", "live.com", "aol.com"}
    domain_counts: dict[str, int] = {}
    for ident in identities:
        domain = ident["email"].split("@")[-1].lower()
        if domain not in _FREEMAIL and "noreply" not in domain and "local" not in domain:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
    org_domain = max(domain_counts, key=domain_counts.get) if domain_counts else ""
    org_name = org_domain.split(".")[0] if org_domain else ""

    # Build lookup indexes
    by_noreply_user: dict[str, list[str]] = {}  # github username -> emails
    by_local_part: dict[str, list[str]] = {}    # normalized local part -> emails
    by_norm_name: dict[str, list[str]] = {}     # normalized name -> emails
    by_first_name: dict[str, list[str]] = {}    # first name from firstname.lastname -> emails
    email_to_best_name: dict[str, str] = {}     # email -> best display name
    noreply_stripped: dict[str, list[str]] = {}  # org-stripped gh username -> noreply emails

    for ident in identities:
        email = ident["email"]
        name = ident["name"] or ""
        login = ident["login"] or ""

        # Store best display name (prefer real name with spaces/accents over login)
        candidate = name or login or email
        prev = email_to_best_name.get(email, "")
        if not prev or (" " in candidate and " " not in prev) or \
                (" " in candidate and len(candidate.encode("utf-8")) > len(prev.encode("utf-8"))):
            email_to_best_name[email] = candidate

        parent.setdefault(email, email)

        # Extract GitHub noreply username
        if "noreply.github.com" in email:
            local = email.split("@")[0]
            gh_user = local.split("+")[-1] if "+" in local else local
            gh_user_norm = _normalize_name(gh_user)
            by_noreply_user.setdefault(gh_user_norm, []).append(email)

            # Strip org name from GitHub username for first-name matching
            # e.g. "jane-acme" with org "acme" -> "jane"
            if org_name:
                stripped = gh_user_norm.replace(_normalize_name(org_name), "")
                if stripped and len(stripped) > 2 and stripped != gh_user_norm:
                    noreply_stripped.setdefault(stripped, []).append(email)

        # Normalized email local part
        local = email.split("@")[0]
        local_clean = local.split("+")[-1] if "+" in local else local
        local_norm = _normalize_name(local_clean)
        if local_norm and len(local_norm) > 2:
            by_local_part.setdefault(local_norm, []).append(email)

        # Index first name from firstname.lastname@ or firstname-lastname@ emails
        domain = email.split("@")[-1].lower()
        if domain == org_domain and ("." in local_clean or "-" in local_clean):
            parts = re.split(r"[.\-_]", local_clean)
            if len(parts) >= 2:
                first = _normalize_name(parts[0])
                if first and len(first) > 2:
                    by_first_name.setdefault(first, []).append(email)

        # Normalized author name
        if name:
            name_norm = _normalize_name(name)
            if name_norm and len(name_norm) > 2:
                by_norm_name.setdefault(name_norm, []).append(email)
            # Also index first name from "Firstname Lastname" display names
            name_parts = name.split()
            if len(name_parts) >= 2:
                first = _normalize_name(name_parts[0])
                if first and len(first) > 2:
                    by_first_name.setdefault(first, []).append(email)

        # Also index login as a name
        if login:
            login_norm = _normalize_name(login)
            if login_norm and len(login_norm) > 2:
                by_norm_name.setdefault(login_norm, []).append(email)

    # --- Merge passes ---

    # 1. GitHub noreply username matching email local parts or names
    for gh_user, gh_emails in by_noreply_user.items():
        if gh_user in by_local_part:
            all_emails = gh_emails + by_local_part[gh_user]
            for e in all_emails[1:]:
                union(all_emails[0], e)
        if gh_user in by_norm_name:
            all_emails = gh_emails + by_norm_name[gh_user]
            for e in all_emails[1:]:
                union(all_emails[0], e)

    # 2. Org-stripped GitHub username matching first names
    #    e.g. noreply "jane-acme" stripped to "jane" matches "jane.doe@acme.com"
    #    Only merge if the first name is unique (avoid merging different people)
    for stripped, gh_emails in noreply_stripped.items():
        if stripped in by_first_name:
            # Count unique people with this first name (by distinct email domains)
            first_name_emails = by_first_name[stripped]
            unique_people = len({e.split("@")[-1] for e in first_name_emails
                                 if "noreply" not in e})
            if unique_people <= 1:
                all_emails = gh_emails + first_name_emails
                for e in all_emails[1:]:
                    union(all_emails[0], e)

    # 3. Exact normalized name
    for name_norm, emails in by_norm_name.items():
        if len(emails) > 1:
            for e in emails[1:]:
                union(emails[0], e)

    # 4. Local part across domains
    for local_norm, emails in by_local_part.items():
        if len(emails) > 1:
            for e in emails[1:]:
                union(emails[0], e)

    # Build final groups
    groups_by_root: dict[str, list[str]] = {}
    for ident in identities:
        email = ident["email"]
        root = find(email)
        groups_by_root.setdefault(root, []).append(email)

    # Pick canonical name for each group
    result: dict[str, list[str]] = {}
    for emails in groups_by_root.values():
        emails = list(dict.fromkeys(emails))
        canonical = _pick_canonical_name(emails, email_to_best_name)
        result[canonical] = emails

    return result


def _pick_canonical_name(emails: list[str],
                         email_to_best_name: dict[str, str]) -> str:
    """Pick the best display name for a group of emails.

    Prefers real names (with spaces) over usernames, and accented names
    over ASCII-only. Falls back to title-casing hyphenated usernames.
    """
    candidates = [email_to_best_name[e] for e in emails if email_to_best_name.get(e)]

    # Prefer names that look like "Firstname Lastname"
    real_names = [n for n in candidates if " " in n]
    if real_names:
        return max(real_names, key=lambda n: len(n.encode("utf-8")))

    # Try to make a display name from usernames
    for name in candidates:
        # CamelCase: "BenjaminPicard" -> "Benjamin Picard"
        # Also handles "paulmartinACME" -> "Paulmartin" (strip trailing all-caps org)
        camel_parts = re.findall(r"[A-Z][a-z]+", name)
        if len(camel_parts) >= 2 and "".join(camel_parts) == name:
            return " ".join(camel_parts)
        # "paulmartinACME" pattern: lowercase name + uppercase org suffix
        m = re.match(r"^([a-z]{3,})([A-Z]{2,})$", name)
        if m:
            return m.group(1).capitalize()

        # Hyphenated: "jane-doe" -> "Jane Doe"
        if "-" in name and not name.startswith("["):
            parts = name.split("-")
            if all(p.isalpha() for p in parts):
                return " ".join(p.capitalize() for p in parts)

    if candidates:
        return max(candidates, key=lambda n: len(n))

    return emails[0]
