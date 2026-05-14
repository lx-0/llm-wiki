"""Manage hard-fact corrections that override LLM-compiled wiki content.

Hard facts live in `knowledge/facts/<slug>.md`. They carry the highest
authority during compile + query: when a source claim contradicts a fact, the
fact wins.

Usage:
    uv run python scripts/facts/correct.py add "Senkrechtstarter award" \
        --status negation \
        --trust confirmed \
        --source "https://handelsblatt.de/..." \
        --source "raw/clippings/2026-04-12-mail.md" \
        --term "senkrechtstarter award" --term "won the senkrechtstarter" \
        "We did NOT win the Senkrechtstarter award."

    # user-only fact (default trust = asserted):
    uv run python scripts/facts/correct.py add "Office hours" \
        --status clarification \
        --source "user:2026-05-03" \
        "Office opens at 10am starting Monday."

    uv run python scripts/facts/correct.py list
    uv run python scripts/facts/correct.py remove <slug>
    uv run python scripts/facts/correct.py edit <slug>
    uv run python scripts/facts/correct.py path <slug>     # print absolute path
"""

import os
os.environ.setdefault("CLAUDE_INVOKED_BY", "correct")

import argparse
import logging
import os as _os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from core.paths import FACTS_DIR
from core.utils import slugify, today_iso

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("correct")

VALID_STATUS = {"negation", "disambiguation", "clarification"}
VALID_TRUST = ("confirmed", "asserted", "provisional")
DEFAULT_TRUST = "asserted"


def _fact_path(slug: str) -> Path:
    return FACTS_DIR / f"{slug}.md"


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak.{ts}")
    shutil.copy2(path, bak)
    return bak


def _read_frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    block = text[4:end]
    body = text[end + 5 :]
    try:
        fm = yaml.safe_load(block) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


def _write_fact(path: Path, frontmatter: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True
    ).rstrip()
    path.write_text(f"---\n{serialized}\n---\n\n{body.strip()}\n", encoding="utf-8")


def _list_facts() -> list[Path]:
    if not FACTS_DIR.exists():
        return []
    return sorted(FACTS_DIR.glob("*.md"))


def cmd_add(args: argparse.Namespace) -> int:
    status = args.status
    if status not in VALID_STATUS:
        log.error("--status must be one of %s", sorted(VALID_STATUS))
        return 2

    title = args.title.strip()
    if not title:
        log.error("title must not be empty")
        return 2

    body = args.body.strip()
    if not body:
        log.error("body must not be empty")
        return 2

    sources = [s.strip() for s in (args.source or []) if s and s.strip()]
    if not sources:
        log.error(
            "at least one --source is required. Use a URL, vault-relative path, "
            "or a sentinel like 'user:<context>', 'screenshot:<file>', 'hearsay:<who>'."
        )
        return 2

    trust = args.trust
    if trust not in VALID_TRUST:
        log.error("--trust must be one of %s", list(VALID_TRUST))
        return 2

    slug = args.slug.strip() if args.slug else slugify(title)
    if not slug:
        log.error("could not derive a slug from title %r", title)
        return 2

    path = _fact_path(slug)
    today = today_iso()

    if path.exists() and not args.force:
        log.error(
            "%s already exists. Use `facts/correct.py edit %s` or pass --force.",
            path,
            slug,
        )
        return 1

    bak = _backup(path)
    if bak:
        log.info("Backed up existing %s -> %s", path.name, bak.name)

    frontmatter = {
        "title": title,
        "type": "fact",
        "status": status,
        "trust": trust,
        "sources": sources,
        "created": today,
        "updated": today,
        "applied": False,
        "negation_terms": list(args.term or []),
    }
    _write_fact(path, frontmatter, body)
    print(str(path))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    facts = _list_facts()
    if not facts:
        print("(no hard facts yet)")
        return 0
    for path in facts:
        fm, _ = _read_frontmatter(path)
        title = fm.get("title", "(untitled)")
        status = fm.get("status", "?")
        trust = fm.get("trust", DEFAULT_TRUST)
        sources = fm.get("sources") or []
        terms = fm.get("negation_terms") or []
        slug = path.stem
        src_hint = f" [{len(sources)} src]" if sources else " [0 src]"
        terms_hint = f" [{len(terms)} term(s)]" if terms else ""
        print(f"{slug:40s} {status:14s} {trust:11s} {title}{src_hint}{terms_hint}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    slug = args.slug.strip()
    path = _fact_path(slug)
    if not path.exists():
        log.error("no such fact: %s", slug)
        return 1
    bak = _backup(path)
    path.unlink()
    log.info("Removed %s (backup at %s)", path, bak)
    return 0


def cmd_edit(args: argparse.Namespace) -> int:
    slug = args.slug.strip()
    path = _fact_path(slug)
    if not path.exists():
        log.error("no such fact: %s", slug)
        return 1
    editor = _os.environ.get("EDITOR") or _os.environ.get("VISUAL") or "vi"
    bak = _backup(path)
    log.info("Backup: %s", bak)
    return subprocess.call([editor, str(path)])


def cmd_path(args: argparse.Namespace) -> int:
    slug = args.slug.strip()
    path = _fact_path(slug)
    if not path.exists():
        log.error("no such fact: %s", slug)
        return 1
    print(str(path))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="add a new hard fact")
    p_add.add_argument("title", help='short title, e.g. "Senkrechtstarter award"')
    p_add.add_argument("body", help="freitext truth (the LLM reads this verbatim)")
    p_add.add_argument(
        "--status",
        default="negation",
        choices=sorted(VALID_STATUS),
        help="negation = strike a false claim; disambiguation = clarify a name; clarification = anything else",
    )
    p_add.add_argument(
        "--term",
        action="append",
        default=[],
        help="exact substring lint should grep for (repeatable). For status=negation only.",
    )
    p_add.add_argument(
        "--source",
        action="append",
        default=[],
        required=False,
        help="evidence source for this fact (repeatable, REQUIRED). URL, vault-relative path, "
        "or sentinel like 'user:<context>', 'screenshot:<file>', 'hearsay:<who>'.",
    )
    p_add.add_argument(
        "--trust",
        default=DEFAULT_TRUST,
        choices=list(VALID_TRUST),
        help=f"trust tier (default: {DEFAULT_TRUST}). confirmed = externally verifiable artifact; "
        "asserted = user direct statement; provisional = hearsay / needs verification.",
    )
    p_add.add_argument(
        "--slug",
        default=None,
        help="override the auto-derived slug (default: slugify(title))",
    )
    p_add.add_argument(
        "--force",
        action="store_true",
        help="overwrite if the fact already exists",
    )
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="list all hard facts")
    p_list.set_defaults(func=cmd_list)

    p_remove = sub.add_parser("remove", help="remove a hard fact")
    p_remove.add_argument("slug", help="fact slug (filename without .md)")
    p_remove.set_defaults(func=cmd_remove)

    p_edit = sub.add_parser("edit", help="open a hard fact in $EDITOR")
    p_edit.add_argument("slug", help="fact slug")
    p_edit.set_defaults(func=cmd_edit)

    p_path = sub.add_parser("path", help="print absolute path of a fact")
    p_path.add_argument("slug", help="fact slug")
    p_path.set_defaults(func=cmd_path)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
