"""Shared utilities for the personal knowledge base."""

import hashlib
import json
import re
from pathlib import Path

import yaml

from config import (
    CONCEPTS_DIR,
    CONNECTIONS_DIR,
    DAILY_DIR,
    FACTS_DIR,
    INDEX_FILE,
    KNOWLEDGE_DIR,
    LOG_FILE,
    PEOPLE_DIR,
    PROJECTS_DIR,
    QA_DIR,
    RAW_DIR,
    STATE_DIR,
    STATE_FILE,
    now_iso,
)


# ── State management ──────────────────────────────────────────────────

def load_json_state(path: Path, default: dict | None = None) -> dict:
    """Load a JSON state file, returning `default` (or {}) when missing."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return dict(default) if default else {}


def save_json_state(path: Path, state: dict) -> None:
    """Write a JSON state file (indent=2, default=str for datetime etc.)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


_DEFAULT_STATE = {"ingested": {}, "query_count": 0, "last_lint": None, "total_cost": 0.0}


def load_state() -> dict:
    """Load the compiler's primary state.json."""
    return load_json_state(STATE_FILE, _DEFAULT_STATE)


def save_state(state: dict) -> None:
    """Save the compiler's primary state.json."""
    save_json_state(STATE_FILE, state)


# ── Append-only event history (M003-S05) ──────────────────────────────

def append_history(event_type: str, **fields) -> None:
    """Append one JSON line to STATE_DIR/history.jsonl.

    Auto-injects `ts` (ISO timestamp) and `type`. Per-line atomic write so
    concurrent compile + flush events never tear. Best-effort: failures are
    silently ignored (history is observability, not the source of truth)."""
    history_file = STATE_DIR / "history.jsonl"
    try:
        history_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ts": now_iso(), "type": event_type, **fields}
        with history_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except OSError:
        pass


def read_history(limit: int | None = None) -> list[dict]:
    """Read STATE_DIR/history.jsonl. Skips malformed/blank lines silently.
    Returns events in append order (oldest-first); slice tail with `limit`."""
    history_file = STATE_DIR / "history.jsonl"
    if not history_file.exists():
        return []
    events: list[dict] = []
    for line in history_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if limit is not None:
        return events[-limit:]
    return events


# ── File hashing ──────────────────────────────────────────────────────

def file_hash(path: Path) -> str:
    """SHA-256 hash of a file (first 16 hex chars)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# ── Slug / naming ─────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


# ── Wikilink helpers ──────────────────────────────────────────────────

def extract_wikilinks(content: str) -> list[str]:
    """Extract all [[wikilinks]] from markdown content."""
    return re.findall(r"\[\[([^\]]+)\]\]", content)


def wiki_article_exists(link: str) -> bool:
    """Check if a wikilinked article exists on disk."""
    path = KNOWLEDGE_DIR / f"{link}.md"
    return path.exists()


# ── Wiki content helpers ──────────────────────────────────────────────

WIKI_SUBDIRS = [CONCEPTS_DIR, CONNECTIONS_DIR, QA_DIR, PEOPLE_DIR, PROJECTS_DIR, FACTS_DIR]


def read_wiki_index() -> str:
    """Read the knowledge base index file."""
    if INDEX_FILE.exists():
        return INDEX_FILE.read_text(encoding="utf-8")
    return (
        "# Knowledge Base Index\n\n"
        "| Article | Summary | Compiled From | Updated |\n"
        "|---------|---------|---------------|---------|"
    )


def read_all_wiki_content() -> str:
    """Read index + all wiki articles into a single string for context."""
    parts = [f"## INDEX\n\n{read_wiki_index()}"]

    for subdir in WIKI_SUBDIRS:
        if not subdir.exists():
            continue
        for md_file in sorted(subdir.glob("*.md")):
            rel = md_file.relative_to(KNOWLEDGE_DIR)
            content = md_file.read_text(encoding="utf-8")
            parts.append(f"## {rel}\n\n{content}")

    return "\n\n---\n\n".join(parts)


_TRUST_RANK = {"confirmed": 0, "asserted": 1, "provisional": 2}
_LEGACY_TRUST = "asserted"
_LEGACY_SOURCE = "user:legacy-pre-trust-schema"


def _parse_fact_frontmatter(md_file: Path) -> tuple[dict, str]:
    """Return (frontmatter_dict, raw_text). Tolerates malformed YAML."""
    text = md_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    block = text[4:end]
    try:
        fm = yaml.safe_load(block) or {}
    except yaml.YAMLError:
        fm = {}
    return (fm if isinstance(fm, dict) else {}), text


def read_hard_facts() -> str:
    """Read all knowledge/facts/*.md and join them into one prompt-ready block.

    Facts are sorted by trust tier (confirmed > asserted > provisional), then by
    `updated` (most recent first) as tiebreaker. Each fact is rendered with a
    `[trust: ...]` header and a `Sources:` line so the LLM can weigh authority.

    Returns an empty placeholder when no facts exist, so prompts that
    inject `${facts_md}` always get a non-empty string.
    """
    if not FACTS_DIR.exists():
        return "(no hard facts recorded)"

    entries = []
    for md_file in sorted(FACTS_DIR.glob("*.md")):
        fm, raw_text = _parse_fact_frontmatter(md_file)
        trust = str(fm.get("trust") or _LEGACY_TRUST)
        if trust not in _TRUST_RANK:
            trust = _LEGACY_TRUST
        sources = fm.get("sources") or []
        if not isinstance(sources, list) or not sources:
            sources = [_LEGACY_SOURCE]
        sources = [str(s) for s in sources if s]
        updated = str(fm.get("updated") or fm.get("created") or "")
        rel = md_file.relative_to(KNOWLEDGE_DIR)
        entries.append((trust, updated, rel, sources, raw_text))

    if not entries:
        return "(no hard facts recorded)"

    # Sort: trust tier ASC (rank 0 first), then updated DESC (most recent first).
    entries.sort(key=lambda e: (_TRUST_RANK.get(e[0], 99), -_str_sort_key(e[1])))

    parts = []
    for trust, _updated, rel, sources, raw_text in entries:
        sources_line = ", ".join(sources)
        parts.append(
            f"### {rel}  [trust: {trust}]\n\n"
            f"> Sources: {sources_line}\n\n"
            f"{raw_text}"
        )
    return "\n\n".join(parts)


def _str_sort_key(s: str) -> int:
    """Map an ISO-ish date string to a sortable int. Empty / unparseable → 0."""
    digits = "".join(c for c in s if c.isdigit())
    return int(digits[:14]) if digits else 0


def list_wiki_articles() -> list[Path]:
    """List all wiki article files."""
    articles = []
    for subdir in WIKI_SUBDIRS:
        if subdir.exists():
            articles.extend(sorted(subdir.glob("*.md")))
    return articles


def list_raw_files() -> list[Path]:
    """List all daily log files AND raw source files."""
    files = []
    if DAILY_DIR.exists():
        files.extend(sorted(DAILY_DIR.glob("*.md")))
    if RAW_DIR.exists():
        files.extend(sorted(RAW_DIR.rglob("*.md")))
    return files


# ── Index helpers ─────────────────────────────────────────────────────

def count_inbound_links(target: str, exclude_file: Path | None = None) -> int:
    """Count how many wiki articles link to a given target."""
    count = 0
    for article in list_wiki_articles():
        if article == exclude_file:
            continue
        content = article.read_text(encoding="utf-8")
        if f"[[{target}]]" in content:
            count += 1
    return count


def get_article_word_count(path: Path) -> int:
    """Count words in an article, excluding YAML frontmatter."""
    content = path.read_text(encoding="utf-8")
    # Strip frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:]
    return len(content.split())


def build_index_entry(rel_path: str, summary: str, sources: str, updated: str) -> str:
    """Build a single index table row."""
    link = rel_path.replace(".md", "")
    return f"| [[{link}]] | {summary} | {sources} | {updated} |"
