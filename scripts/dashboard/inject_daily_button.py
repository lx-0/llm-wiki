"""Inject a per-day Summarize button into existing daily log files.

Idempotent walk over `daily/*.md`. Inserts a marker-bracketed Meta-Bind button
block right after the H1 if the markers are not already present. Re-running
produces no diff. Live operator edits outside the marker region are untouched.

Usage:
    uv run python scripts/dashboard/inject_daily_button.py                # add buttons to all daily/*.md
    uv run python scripts/dashboard/inject_daily_button.py --dry-run      # show what would change
    uv run python scripts/dashboard/inject_daily_button.py --remove       # strip the button regions

The button uses the existing shell command `agent-summarize-day-here` which
substitutes `{{file_basename}}` (the date) into `wiki agent summarize-day --var
date=…`, so each daily file's button summarises THAT day, not today.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.paths import DAILY_DIR


BEGIN = "<!-- summarize-button:begin -->"
END = "<!-- summarize-button:end -->"

BUTTON_BLOCK = f"""\
{BEGIN}
```meta-bind-button
label: 📅 Summarize this day
hidden: false
class: ""
tooltip: "Run summarize-day agent against this day's log."
id: btn-summarize-here
style: primary
actions:
  - type: command
    command: "Shell commands: Wiki: agent summarize this day"
```
{END}"""


_REGION_RE = re.compile(rf"\n*{re.escape(BEGIN)}.*?{re.escape(END)}\n*", re.DOTALL)
_H1_RE = re.compile(r"^(# .*?\n)", re.MULTILINE)


def _has_region(text: str) -> bool:
    return BEGIN in text and END in text


def insert_button(text: str) -> tuple[str, bool]:
    """Return (new_text, changed). Idempotent — no-op if region already present."""
    if _has_region(text):
        return text, False
    m = _H1_RE.search(text)
    if not m:
        # No H1 — prepend button block at start of file.
        return f"{BUTTON_BLOCK}\n\n{text}", True
    end = m.end()
    return text[:end] + "\n" + BUTTON_BLOCK + "\n" + text[end:], True


def remove_button(text: str) -> tuple[str, bool]:
    """Strip the button region. Returns (new_text, changed)."""
    if not _has_region(text):
        return text, False
    return _REGION_RE.sub("\n", text), True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--remove", action="store_true", help="strip button regions instead of inserting")
    args = parser.parse_args()

    if not DAILY_DIR.exists():
        print(f"daily dir not found: {DAILY_DIR}", file=sys.stderr)
        return 1

    files = sorted(DAILY_DIR.glob("*.md"))
    if not files:
        print("no daily/*.md files yet — nothing to do")
        return 0

    op = remove_button if args.remove else insert_button
    label = "remove" if args.remove else "inject"

    changed = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        new_text, did = op(text)
        if not did:
            continue
        changed += 1
        if args.dry_run:
            print(f"  would {label}: {path.relative_to(DAILY_DIR.parent)}")
        else:
            path.write_text(new_text, encoding="utf-8")
            print(f"  {label}ed: {path.relative_to(DAILY_DIR.parent)}")

    suffix = " (dry-run)" if args.dry_run else ""
    print(f"\n{label}ed {changed}/{len(files)} files{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
