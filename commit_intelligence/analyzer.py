"""Commit classification -- heuristic patterns and Ollama LLM."""

import json
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

# --- Bug / feature patterns ---

BUG_PATTERNS = [
    r"(?i)\bfix(?:e[ds])?\b",
    r"(?i)\bbug(?:fix)?\b",
    r"(?i)\bpatch(?:e[ds])?\b",
    r"(?i)\bhotfix\b",
    r"(?i)\bresolve[ds]?\b",
    r"(?i)\bclose[ds]?\s+#\d+",
    r"(?i)\bfix(?:e[ds])?\s+#\d+",
]

FEATURE_PATTERNS = [
    r"(?i)\bfeat(?:ure)?(?:\(|\b)",
    r"(?i)\badd(?:e?d|s)?\s+\w",
    r"(?i)\bimplement(?:e?d|s)?\b",
    r"(?i)\bintroduce[ds]?\b",
    r"(?i)\bnew\s+\w",
]

# Patterns to exclude from bug/feature matching (noise)
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

    # AI detection
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

    # Skip bug/feature counting for noise commits
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, message):
            return result

    # Bug counting
    bug_signals = _count_matches(message, BUG_PATTERNS)
    if bug_signals > 0:
        # Count issue refs separately for more accurate count
        issue_refs = len(re.findall(r"#\d+", message))
        # Use max of pattern matches and issue refs, minimum 1
        result["bug_count"] = max(1, min(bug_signals, 5))

    # Feature counting
    feature_signals = _count_matches(message, FEATURE_PATTERNS)
    if feature_signals > 0:
        result["feature_count"] = max(1, min(feature_signals, 5))

    return result


OLLAMA_PROMPT = """Analyze this git commit message and respond with JSON only.

Commit message:
{message}

Determine:
1. ai_assisted (boolean): Was this commit likely authored with AI coding tools (GitHub Copilot, Claude, Cursor, Codex, Windsurf, etc.)? Look for co-authored-by trailers, explicit mentions, or other signals.
2. ai_tool (string): Which tool? One of: copilot, claude, codex, cursor, windsurf, other, none
3. ai_confidence (float 0-1): How confident are you?
4. bug_count (integer): How many distinct bugs does this commit fix? 0 if none.
5. feature_count (integer): How many distinct features does this commit add? 0 if none.

Respond with ONLY valid JSON, no other text:
{{"ai_assisted": true/false, "ai_tool": "...", "ai_confidence": 0.0, "bug_count": 0, "feature_count": 0}}"""


def _parse_ollama_response(text: str) -> dict | None:
    # Try direct JSON parse
    try:
        data = json.loads(text)
        return _validate_ollama_result(data)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try extracting JSON from markdown code block or surrounding text
    match = re.search(r"\{[^}]+\}", text)
    if match:
        try:
            data = json.loads(match.group())
            return _validate_ollama_result(data)
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _validate_ollama_result(data: dict) -> dict:
    return {
        "ai_assisted": 1 if data.get("ai_assisted") else 0,
        "ai_tool": str(data.get("ai_tool", "none")),
        "ai_confidence": float(data.get("ai_confidence", 0.5)),
        "bug_count": max(0, int(data.get("bug_count", 0))),
        "feature_count": max(0, int(data.get("feature_count", 0))),
    }


def analyze(model: str = "qwen2.5:3b") -> None:
    import ollama as ollama_client

    conn = db.get_connection()
    db.init_db(conn)
    commits = db.get_unanalyzed_commits(conn)

    if not commits:
        print("No unanalyzed commits.")
        conn.close()
        return

    print(f"Analyzing {len(commits)} commits with Ollama ({model})...")

    now = datetime.now(timezone.utc).isoformat()
    success = 0
    failed = 0
    last_by_repo: dict[int, str] = {}  # repo_id -> last sha

    for i, commit in enumerate(commits):
        message = commit["message"] or "(empty commit message)"
        prompt = OLLAMA_PROMPT.format(message=message)

        try:
            response = ollama_client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                format="json",
            )
            text = response["message"]["content"]
            result = _parse_ollama_response(text)

            if result is None:
                result = classify_heuristic(commit["message"])
                mode = "heuristic-fallback"
                failed += 1
            else:
                mode = "ollama"
                success += 1

        except Exception as e:
            print(f"  Ollama error on commit {commit['id']}: {e}")
            result = classify_heuristic(commit["message"])
            mode = "heuristic-fallback"
            failed += 1

        db.update_commit_analysis(
            conn, commit["id"],
            ai_assisted=result["ai_assisted"],
            ai_tool=result["ai_tool"],
            ai_confidence=result["ai_confidence"],
            bug_count=result["bug_count"],
            feature_count=result["feature_count"],
            analysis_mode=mode,
            analyzed_at=now,
        )
        last_by_repo[commit["repo_id"]] = commit["sha"]

        if (i + 1) % 10 == 0:
            conn.commit()
            print(f"  {i + 1}/{len(commits)} analyzed")

    conn.commit()

    # Update last analyzed pointer per repo
    for repo_id, sha in last_by_repo.items():
        db.update_repo_analyzed(conn, repo_id, sha, now)

    conn.close()
    print(f"Analysis complete: {success} via LLM, {failed} fell back to heuristic.")
