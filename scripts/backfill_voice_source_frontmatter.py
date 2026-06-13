"""One-shot backfill for daily voice rollups written before the
frontmatter-source-ref change (2026-06-13).

Older `daily/<date>/voice.md` files carry the source reference as an in-body
wikilink (`- **HH:MM** · … → [[voice-…]]`). Obsidian ignores `raw/`, so that
link renders dead. The live collector now drops the body link and records the
source under a `sources:` frontmatter list instead. This backfill brings
existing files to the same shape:

- Every body line ending in ` → [[<stem>]]` has the suffix stripped.
- `<stem>` is mapped to `raw/voice/<stem>.md` and merged into the file's
  `sources:` frontmatter list (dedup, append order, existing entries kept).

Idempotent: a file already migrated (no body wikilinks left) produces no
change. Non-voice daily files are never touched. Frontmatter that is not the
`sources:` block is preserved verbatim.

Usage:
    wiki backfill voice-source-frontmatter            # apply
    wiki backfill voice-source-frontmatter --dry-run  # show what would change
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import daily_capture  # noqa: E402
from core.paths import ROOT_DIR  # noqa: E402

log = logging.getLogger("backfill-voice-source-frontmatter")

# Matches a trailing ` → [[stem]]` (the legacy in-body source link).
_WIKILINK_RE = re.compile(r"\s*→\s*\[\[([^\]]+)\]\]\s*$")


def _migrate_text(text: str) -> tuple[str, int]:
    """Return (new_text, links_lifted). 0 links lifted = no change."""
    sources, body = daily_capture._read_sources_and_body(text)
    lifted = 0
    out_lines: list[str] = []
    for line in body.splitlines():
        m = _WIKILINK_RE.search(line)
        if m:
            ref = f"raw/voice/{m.group(1)}.md"
            if ref not in sources:
                sources.append(ref)
            line = _WIKILINK_RE.sub("", line).rstrip()
            lifted += 1
        out_lines.append(line)

    if lifted == 0:
        return text, 0

    new_body = "\n".join(out_lines)
    if new_body and not new_body.endswith("\n"):
        new_body += "\n"
    fm = "---\nsources:\n" + "".join(f"  - {s}\n" for s in sources) + "---\n"
    return fm + new_body, lifted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing.")
    args = parser.parse_args()

    daily_dir = ROOT_DIR / "daily"
    files = sorted(daily_dir.glob("*/voice.md"))
    if not files:
        log.info("no daily/*/voice.md files found under %s", daily_dir)
        return 0

    changed = 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        new_text, lifted = _migrate_text(text)
        if lifted == 0:
            continue
        changed += 1
        log.info("%s: %d source link(s) → frontmatter", f.relative_to(ROOT_DIR), lifted)
        if not args.dry_run:
            f.write_text(new_text, encoding="utf-8")

    if changed == 0:
        log.info("all %d voice rollup(s) already migrated — no change.", len(files))
    elif args.dry_run:
        log.info("[dry-run] %d file(s) would change. Re-run without --dry-run to apply.", changed)
    else:
        log.info("migrated %d file(s).", changed)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main())
