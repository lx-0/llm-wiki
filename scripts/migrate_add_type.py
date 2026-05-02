"""Backfill the `type:` frontmatter field on knowledge/ articles.

Pre-existing articles compiled before the schema change had no `type:` field
(folder name was the only substrate-type signal). New compiles set the field
correctly; this script brings legacy articles in line so Dataview / lint /
charts treat them uniformly.

Cheap operation — pure folder→type mapping, no LLM call. Idempotent.

Usage:
    uv run python scripts/migrate_add_type.py             # write
    uv run python scripts/migrate_add_type.py --dry-run   # preview only
"""

from __future__ import annotations

import os

os.environ["CLAUDE_INVOKED_BY"] = "migrate_add_type"

import argparse
import logging
import re
import sys
from pathlib import Path

from config import KNOWLEDGE_DIR
from utils import list_wiki_articles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("migrate-add-type")

FOLDER_TO_TYPE = {
    "concepts": "concept",
    "connections": "connection",
    "qa": "qa",
    "people": "person",
    "projects": "project",
    "MOCs": "moc",
}

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_TYPE_LINE_RE = re.compile(r"^type:\s*(.+)$", re.MULTILINE)


def expected_type_for(article: Path) -> str | None:
    rel = article.relative_to(KNOWLEDGE_DIR)
    parts = rel.parts
    if len(parts) < 2:
        return None
    return FOLDER_TO_TYPE.get(parts[0])


def needs_migration(content: str, expected: str) -> tuple[bool, str]:
    """Return (yes/no, reason). reason is the action label for logging."""
    fm_match = _FRONTMATTER_RE.match(content)
    if not fm_match:
        return True, "add-frontmatter"
    fm = fm_match.group(1)
    type_match = _TYPE_LINE_RE.search(fm)
    if not type_match:
        return True, "add-type"
    actual = type_match.group(1).strip().strip('"').strip("'")
    if actual != expected:
        return True, f"correct-type ({actual} → {expected})"
    return False, ""


def apply_migration(content: str, expected: str) -> str:
    """Insert or correct the `type:` field. Preserves all other frontmatter."""
    fm_match = _FRONTMATTER_RE.match(content)
    if not fm_match:
        # No frontmatter at all — wrap the whole file in a minimal block.
        return f"---\ntype: {expected}\n---\n{content}"
    fm = fm_match.group(1)
    body = content[fm_match.end():]
    if _TYPE_LINE_RE.search(fm):
        new_fm = _TYPE_LINE_RE.sub(f"type: {expected}", fm, count=1)
    else:
        # Insert after `title:` if present, else at the top of the block.
        title_match = re.search(r"^title:.*$", fm, re.MULTILINE)
        if title_match:
            insert_at = title_match.end()
            new_fm = fm[:insert_at] + f"\ntype: {expected}" + fm[insert_at:]
        else:
            new_fm = f"type: {expected}\n{fm}"
    return f"---\n{new_fm}\n---\n{body}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    articles = [a for a in list_wiki_articles() if a.name not in ("index.md", "log.md")]
    log.info("Inspecting %d articles in %s", len(articles), KNOWLEDGE_DIR)

    counts = {"unchanged": 0, "would-fix": 0, "fixed": 0, "skipped-unknown-folder": 0}
    for article in articles:
        expected = expected_type_for(article)
        if expected is None:
            counts["skipped-unknown-folder"] += 1
            continue
        try:
            content = article.read_text(encoding="utf-8")
        except OSError:
            log.warning("Could not read %s — skipping", article)
            continue
        change, reason = needs_migration(content, expected)
        if not change:
            counts["unchanged"] += 1
            continue
        rel = article.relative_to(KNOWLEDGE_DIR)
        if args.dry_run:
            counts["would-fix"] += 1
            log.info("would fix %s — %s", rel, reason)
            continue
        new_content = apply_migration(content, expected)
        article.write_text(new_content, encoding="utf-8")
        counts["fixed"] += 1
        log.info("fixed %s — %s", rel, reason)

    log.info("Summary: %s", counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
