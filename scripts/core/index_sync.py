"""Deterministic knowledge/index.md sync (M031-S02).

The catalog table is ENGINE bookkeeping, not LLM work: the compile prompt's
"add or update the table row" step could never upsert (the same prompt forbids
reading the ~550 KB index in full), so the live index drifted to 362 duplicate
rows and 561 missing articles. This pass reconciles the table against the
corpus deterministically — same family as the relativize and backlinks passes:

- prose/header above the table survives byte-for-byte
- existing rows keep their position and cell content (summaries are curated
  LLM output — never regenerated here)
- duplicate rows for one article: the LAST occurrence wins (compile appended
  newest last), earlier ones are removed
- rows whose article no longer resolves are dropped
- articles without a row are appended: summary = first body paragraph
  (frontmatter stripped, links collapsed to text, pipes escaped), source =
  first frontmatter ``sources`` entry (else an em dash), date = today
"""
from __future__ import annotations

import re
from pathlib import Path

from . import frontmatter
from .links import WIKILINK_RE, iter_articles, resolve_link, strip_table_escape

_PIPE_SENTINEL = "\x00"
_HEADER_ROW = "| Article |"


def _row_target(line: str, index_file: Path, vault: Path, knowledge_root: Path) -> str | None:
    """Resolve a table row's Article cell to a knowledge-relative rel, or None."""
    safe = line.replace(r"\|", _PIPE_SENTINEL)
    cols = [c.strip().replace(_PIPE_SENTINEL, r"\|") for c in safe.split("|")]
    if len(cols) < 6:
        return None
    match = WIKILINK_RE.search(cols[1])
    if not match:
        return None
    clean, _esc = strip_table_escape(match.group(2), match.group(4))
    resolved = resolve_link(clean, index_file, vault)
    if resolved is None:
        return None
    try:
        return resolved.relative_to(knowledge_root.resolve()).as_posix()
    except ValueError:
        return None


def _cell_text(text: str) -> str:
    """Collapse article prose into one index cell: links → reader text,
    whitespace joined, raw pipes escaped."""

    def _sub(m: re.Match) -> str:
        _bang, target, _heading, alias = m.groups()
        clean, _esc = strip_table_escape(target, alias)
        if alias:
            alias_text = alias[1:].strip()
            if alias_text:
                return alias_text
        return clean

    flat = " ".join(WIKILINK_RE.sub(_sub, text).split())
    return flat.replace("|", r"\|")


def _summary_and_source(path: Path) -> tuple[str, str]:
    body = path.read_text(encoding="utf-8")
    try:
        fm, content = frontmatter.parse(body)
    except frontmatter.FrontmatterError:
        fm, content = {}, body
    summary = ""
    for para in re.split(r"\n\s*\n", content):
        lines = [ln.strip() for ln in para.splitlines() if ln.strip()]
        text_lines = [ln for ln in lines if not ln.startswith("#")]
        if not text_lines:
            continue
        summary = _cell_text(" ".join(text_lines))
        if summary:
            break
    if not summary:
        summary = path.stem
    sources = fm.get("sources") if isinstance(fm, dict) else None
    source = ""
    if isinstance(sources, list) and sources:
        source = str(sources[0])
    elif isinstance(sources, str) and sources:
        source = sources
    return summary, source or "—"


def sync_index(knowledge_dir: Path, vault: Path, *, today: str, apply: bool = True) -> dict:
    """Reconcile ``knowledge/index.md`` against the corpus. Returns stats;
    writes only when something changed (and ``apply`` is True — ``False`` is
    the dry-run used by ``wiki reindex --dry-run``)."""
    index_file = knowledge_dir / "index.md"
    original = index_file.read_text(encoding="utf-8") if index_file.exists() else ""
    lines = original.split("\n")
    knowledge_root = knowledge_dir

    corpus = {
        p.relative_to(knowledge_dir).as_posix(): p for p in iter_articles(knowledge_dir)
    }

    # First sweep: find each target's LAST row occurrence.
    last_occurrence: dict[str, int] = {}
    rows_before = 0
    row_targets: dict[int, str | None] = {}
    for i, line in enumerate(lines):
        if not line.startswith("| ") or line.startswith(_HEADER_ROW) or line.startswith("|-"):
            continue
        rows_before += 1
        target = _row_target(line, index_file, vault, knowledge_root)
        row_targets[i] = target
        if target is not None:
            last_occurrence[target] = i

    kept = deduped = dropped = 0
    seen: set[str] = set()
    out: list[str] = []
    for i, line in enumerate(lines):
        if i not in row_targets:
            out.append(line)
            continue
        target = row_targets[i]
        if target is None or target not in corpus:
            dropped += 1
            continue
        if last_occurrence[target] != i:
            deduped += 1
            continue
        seen.add(target)
        kept += 1
        out.append(line)

    appended = 0
    missing = sorted(set(corpus) - seen)
    if missing:
        while out and out[-1] == "":
            out.pop()
        for rel in missing:
            summary, source = _summary_and_source(corpus[rel])
            slug = rel[:-3] if rel.endswith(".md") else rel
            out.append(f"| [[{slug}]] | {summary} | {source} | {today} |")
            appended += 1
        out.append("")

    new_text = "\n".join(out)
    changed = new_text != original
    if changed and apply:
        index_file.write_text(new_text, encoding="utf-8")

    return {
        "rows_before": rows_before,
        "kept": kept,
        "deduped": deduped,
        "dropped_dangling": dropped,
        "appended": appended,
        "changed": changed,
    }
