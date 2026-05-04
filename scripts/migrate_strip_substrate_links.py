"""Strip `[[raw/memories/...]]` wikilinks from `knowledge/` bodies.

One-time migration enforcing the "distill, don't cite" rule (see
`prompts/compile_main.md` rule 6 and the 2026-05-04 DECISIONS entry,
narrowed by the 2026-05-04 follow-up correction).

Only `raw/memories/` is in scope: that subtree is a managed mirror
(`sync-memories.py:202`) which prunes whenever the upstream
`~/.claude/projects/<encoded>/memory/` source is gone — and that
upstream churns constantly (Claude rewrites + prunes auto-memories,
sandbox cwds vanish, /claude-cleanup discards old projects). Body
wikilinks to that subtree become ghost nodes en masse.

Other substrates are durable and remain citable:
  - `daily/*.md`           — append-only session-history; no engine prunes
  - `raw/notes/email/*`    — scan-email artefacts; durable
  - `raw/notes/screenshots/*` — vision-LLM batch reports; durable
  - `raw/notes/youtube/*`  — scan-youtube ingests; skip-existing dedup
  - `raw/articles/*`       — manually-curated; durable

Strip rules:
  - `[[raw/memories/foo|alias]]` -> `alias`            (alias preserved)
  - `[[raw/memories/foo]]`       -> `raw/memories/foo` (path as plain text)
  - `[[raw/notes/foo]]`          -> `[[raw/notes/foo]]` (left alone)
  - `[[daily/2026-…]]`           -> `[[daily/2026-…]]`  (left alone)
  - `![[raw/memories/...]]`      -> `![[raw/memories/...]]` (embeds untouched)

Frontmatter is left untouched (compiled_from is provenance, not a wikilink).
The `knowledge/facts/` subtree is also left untouched — facts are managed by
`wiki correct`, not by the compiler.

Usage:
    uv run python scripts/migrate_strip_substrate_links.py --dry-run
    uv run python scripts/migrate_strip_substrate_links.py --apply
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("migrate-strip-substrate-links")

# Match `[[raw/memories/…]]` only (the managed-mirror subtree).
# Negative lookbehind for `!` skips embed-syntax (`![[...]]`).
# `daily/`, `raw/notes/`, `raw/articles/` are durable substrates and
# stay citable.
_LINK_RE = re.compile(
    r"(?<!!)\[\[(raw/memories/[^|\]]+)(?:\|([^\]]+))?\]\]"
)


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_block_including_fences, body)."""
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end == -1:
        return "", text
    return text[: end + 5], text[end + 5 :]


def _strip_links(body: str) -> tuple[str, int]:
    """Replace substrate wikilinks; return (new_body, replacements)."""
    count = 0

    def repl(match: re.Match) -> str:
        nonlocal count
        count += 1
        target = match.group(1)
        alias = match.group(2)
        return alias if alias else target

    new_body = _LINK_RE.sub(repl, body)
    return new_body, count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path.cwd(),
        help="Vault root (must contain knowledge/). Default: current working directory.",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    parser.add_argument(
        "--include-facts",
        action="store_true",
        help="Also strip in knowledge/facts/ (default: skip — facts are managed by wiki correct)",
    )
    args = parser.parse_args()

    root = args.vault.resolve()
    knowledge_dir = root / "knowledge"
    if not knowledge_dir.exists():
        log.error("knowledge/ not found at %s — pass --vault PATH or cd to vault root", knowledge_dir)
        return 2
    log.info("vault: %s", root)

    files_touched = 0
    files_scanned = 0
    total_replacements = 0
    skipped_facts = 0

    for path in sorted(knowledge_dir.rglob("*.md")):
        rel = path.relative_to(root)
        if not args.include_facts and rel.parts[1:2] == ("facts",):
            skipped_facts += 1
            continue

        files_scanned += 1
        text = path.read_text(encoding="utf-8")
        front, body = _split_frontmatter(text)
        new_body, n = _strip_links(body)
        if n == 0:
            continue

        files_touched += 1
        total_replacements += n
        log.info("  %-60s  -%d link(s)", str(rel), n)

        if args.apply:
            path.write_text(front + new_body, encoding="utf-8")

    mode = "APPLIED" if args.apply else "DRY-RUN"
    log.info("─── %s ───", mode)
    log.info("  scanned:        %d files in knowledge/ (excl. facts)", files_scanned)
    log.info("  facts skipped:  %d", skipped_facts)
    log.info("  files touched:  %d", files_touched)
    log.info("  links stripped: %d", total_replacements)
    if not args.apply:
        log.info("  rerun with --apply to write changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
