"""Shared utilities for the personal knowledge base.

Also home to the datetime helpers `now_iso()` / `today_iso()` — they have
no config dependency, so they live here rather than in the (stateful,
YAML-driven) `config.py` module. Moved here in the 2026-05-14 config split
(architecture-deepening #2).
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .paths import (
    DAILY_DIR,
    FACTS_DIR,
    INDEX_FILE,
    KNOWLEDGE_DIR,
    RAW_DIR,
    STATE_DIR,
    STATE_FILE,
)


# ── Datetime helpers ──────────────────────────────────────────────────

def now_iso() -> str:
    """Current time in ISO 8601 format (local tz, second precision)."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def today_iso() -> str:
    """Current date as YYYY-MM-DD (local tz)."""
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")


# ── State management ──────────────────────────────────────────────────

def load_json_state(path: Path, default: dict | None = None) -> dict:
    """Load a JSON state file, returning `default` (or {}) when missing."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return dict(default) if default else {}


def save_json_state(
    path: Path,
    state: dict,
    *,
    sort_keys: bool = False,
    trailing_newline: bool = False,
) -> None:
    """Write a JSON state file atomically (tmp + os.replace).

    indent=2, default=str for datetime etc. A crash/kill mid-write can never
    leave a torn file — for state.json a torn write means a full recompile
    (~$1-2), which is why dream.py privately engineered the same pattern
    before it was hoisted here (StateStore arc). ``sort_keys`` /
    ``trailing_newline`` keep pre-existing serializations byte-stable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(state, indent=2, default=str, sort_keys=sort_keys)
    if trailing_newline:
        text += "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


_DEFAULT_STATE = {"ingested": {}, "query_count": 0, "last_lint": None, "total_cost": 0.0}


def load_state() -> dict:
    """Load the compiler's primary state.json (fresh disk read).

    Read-side only. Writers merge their own keys via
    ``core.state_store.update_state`` — a whole-dict save here would clobber
    concurrent counter writes (the pre-StateStore race)."""
    return load_json_state(STATE_FILE, _DEFAULT_STATE)


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

def slugify(text: str, max_len: int | None = None) -> str:
    """Convert text to a filename-safe slug.

    `max_len` caps the result length (default None = no cap), so callers that
    build filenames from long titles/URLs don't need a trailing `[:N]` slice.
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")
    return text[:max_len] if max_len is not None else text


# ── Wikilink helpers ──────────────────────────────────────────────────

def extract_wikilinks(content: str) -> list[str]:
    """Extract all [[wikilinks]] from markdown content."""
    return re.findall(r"\[\[([^\]]+)\]\]", content)


# ── Wiki content helpers ──────────────────────────────────────────────


def read_wiki_index() -> str:
    """Read the knowledge base index file."""
    if INDEX_FILE.exists():
        return INDEX_FILE.read_text(encoding="utf-8")
    return (
        "# Knowledge Base Index\n\n"
        "| Article | Summary | Compiled From | Updated |\n"
        "|---------|---------|---------------|---------|"
    )


def read_wiki_index_compact() -> str:
    """Compact index for in-context-window prompt embedding.

    The full `knowledge/index.md` grows roughly linearly with the wiki —
    at 700+ articles it reaches ~550 KB (single-cell summary bodies dominate
    the size). Embedding the full file into every compile / curiosity /
    suggestion prompt pushed the total context past Opus's 200K-token
    window once a 60 KB source was added, causing the bundled CLI to
    crash silently after 4-9 min with exit-1 and empty stderr.

    The compact form keeps only the Article and Updated columns. ~90 %
    size reduction (550 KB → 51 KB). LLM still sees every article path
    + last-updated date — enough signal to dedup or detect staleness;
    full row content comes via the Read tool on demand. Obsidian
    pipe-alias syntax (`[[X\\|alias]]`) is preserved.
    """
    if not INDEX_FILE.exists():
        return (
            "# Knowledge Base Index\n\n"
            "| Article | Updated |\n"
            "|---|---|"
        )
    txt = INDEX_FILE.read_text(encoding="utf-8")
    out: list[str] = []
    in_table_head = False
    PIPE_SENTINEL = "\x00"  # placeholder for `\|` while we split on `|`
    for line in txt.splitlines():
        if line.startswith("| Article |"):
            out.append("| Article | Updated |")
            in_table_head = True
            continue
        if in_table_head and line.startswith("|---"):
            out.append("|---|---|")
            in_table_head = False
            continue
        if not line.startswith("| "):
            out.append(line)
            continue
        safe = line.replace(r"\|", PIPE_SENTINEL)
        cols = [c.strip().replace(PIPE_SENTINEL, r"\|") for c in safe.split("|")]
        # Standard shape: ['', title, summary, sources, date, '']
        if len(cols) < 6:
            out.append(line)
            continue
        out.append(f"| {cols[1]} | {cols[4]} |")
    return "\n".join(out)


def read_all_wiki_content() -> str:
    """Read index + all wiki articles into a single string for context."""
    parts = [f"## INDEX\n\n{read_wiki_index()}"]

    for md_file in list_wiki_articles():
        rel = md_file.relative_to(KNOWLEDGE_DIR)
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue
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


def list_wiki_articles(knowledge_dir: Path | None = None) -> list[Path]:
    """List all wiki article files — THE canonical enumeration (C04).

    Delegates to `core.links.iter_articles`: every `.md` under `knowledge/`
    recursively (so `MOCs/` and future buckets are included) except the root
    `index.md` and hidden files, sorted for determinism. Before C04 this was a
    hardcoded flat 8-subdir glob that silently excluded `knowledge/MOCs/` from
    every lint check and dashboard count. ``knowledge_dir`` defaults to the
    vault's KNOWLEDGE_DIR; tests pass a temp corpus instead of monkeypatching.
    """
    from .links import iter_articles

    kdir = knowledge_dir if knowledge_dir is not None else KNOWLEDGE_DIR
    if not kdir.exists():
        return []
    return sorted(iter_articles(kdir))


def is_compile_excluded_path(rel_path: str | Path) -> bool:
    """True if `rel_path` falls under a compile-excluded vault-prefix.

    Rel-path is interpreted relative to vault root, POSIX-form. Match
    is segment-anchored startswith() against
    `COMPILE_SUBSTRATE_EXCLUDED_PREFIXES` (each entry ends in '/' so a
    rel-path like 'reports/studies/x.md' matches 'reports/' but
    'raw/reports/y.md' does NOT — the prefix is segment-anchored from
    the root, not a contains() match anywhere in the path).

    Single source of truth for the compile air-gap: any walker / scope-
    checker that wants to honour the policy calls this. Tests live in
    `tests/reports/test_compile_substrate_scope.py`.
    """
    from .config import COMPILE_SUBSTRATE_EXCLUDED_PREFIXES

    rel_s = str(rel_path).replace("\\", "/")
    rel_s = rel_s.lstrip("/")
    return any(rel_s.startswith(pre) for pre in COMPILE_SUBSTRATE_EXCLUDED_PREFIXES)


def list_raw_files(
    daily_dir: Path | None = None, raw_dir: Path | None = None
) -> list[Path]:
    """List all daily log files AND raw source files, newest first by mtime.

    Order policy: mtime DESC so the compile pipeline processes recent activity
    before old backlog. Rate-limit aborts (5h Opus window) hit the tail of
    the queue rather than starving newest content. The compile path is the
    only order-sensitive caller; lint and dashboard_stats are order-agnostic.

    ``daily_dir`` / ``raw_dir`` default to the vault's DAILY_DIR / RAW_DIR;
    lint's LintContext builder passes vault-derived paths so tests run over
    temp corpora without monkeypatching module globals.

    Air-gap discipline: belt-and-braces filter via
    `is_compile_excluded_path()`. Today's walker only enters `daily/`
    and `raw/` so a `reports/` rel-path can't appear at vault-root —
    the filter is structurally redundant. It exists to defend against
    future walker expansion (e.g. a vault-root `*.md` sweep) silently
    letting `reports/` into compile.
    """
    daily = daily_dir if daily_dir is not None else DAILY_DIR
    raw = raw_dir if raw_dir is not None else RAW_DIR
    files: list[Path] = []
    if daily.exists():
        files.extend(daily.glob("*.md"))
    if raw.exists():
        files.extend(raw.rglob("*.md"))

    vault_root = daily.parent.resolve()

    def _allowed(p: Path) -> bool:
        try:
            rel = p.resolve().relative_to(vault_root)
        except ValueError:
            return True  # outside vault — let through; not our concern
        return not is_compile_excluded_path(rel)

    files = [f for f in files if _allowed(f)]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


# ── Index helpers ─────────────────────────────────────────────────────
#
# The footer-BLIND inbound-link helpers (`count_inbound_links` oracle +
# `build_inbound_count_map`) were removed in C04: they counted the
# engine-written `## Backlinks` footers as real edges, which neutralized
# `check_orphan_pages` after M020 (backlog/orphan-check-footer-masking.md).
# The footer-aware inbound map now lives in lint's LintContext builder,
# derived from `core.links.outgoing_canonical_slugs` (the one O(N) pass —
# DECISIONS 2026-05-30's single-pass rule holds; the parity oracle retired
# with the semantics it enshrined).


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
