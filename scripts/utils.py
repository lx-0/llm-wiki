"""Shared utilities for the personal knowledge base."""

import hashlib
import json
import re
from pathlib import Path

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
    STATE_FILE,
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


def read_hard_facts() -> str:
    """Read all knowledge/facts/*.md and join them into one prompt-ready block.

    Returns an empty placeholder when no facts exist, so prompts that
    inject `${facts_md}` always get a non-empty string.
    """
    if not FACTS_DIR.exists():
        return "(no hard facts recorded)"
    parts = []
    for md_file in sorted(FACTS_DIR.glob("*.md")):
        rel = md_file.relative_to(KNOWLEDGE_DIR)
        content = md_file.read_text(encoding="utf-8")
        parts.append(f"### {rel}\n\n{content}")
    if not parts:
        return "(no hard facts recorded)"
    return "\n\n".join(parts)


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
