"""One-shot corpus migration: rewrite every `[[wikilink]]` in the vault to a
path relative to its containing markdown file.

The historic engine convention wrote knowledge-internal links as
`[[concepts/foo]]` — relative to `knowledge/`, not to the article. Obsidian
resolves a slash-bearing wikilink against the vault root, so from a nested
article `[[concepts/foo]]` points at `<vault>/concepts/foo.md` (nonexistent)
and Obsidian offers to create an empty stub. This migrates the existing corpus
to the relative form; `core.links.run_relativize_pass` keeps new compiles
correct going forward.

Resolution + rewrite logic lives in `core.links` (single source of truth shared
with the compile post-pass, backlinks, and lint). This file is just the CLI.

A link whose target cannot be located on disk is left untouched and reported —
the migration never fabricates a path. Dry-run by default.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/ on path

from core.links import (  # noqa: E402
    iter_articles,
    relativize_text,
    run_relativize_pass,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vault", required=True, type=Path, help="Vault root (folder containing .obsidian/)")
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    ap.add_argument("--only", type=str, default=None, help="Limit to one file, path relative to vault")
    args = ap.parse_args()

    vault: Path = args.vault.expanduser().resolve()
    knowledge = vault / "knowledge"
    if not knowledge.is_dir():
        print(f"no knowledge/ under {vault}", file=sys.stderr)
        return 2

    # Single-file dry-run: show the diff lines.
    if args.only:
        path = vault / args.only
        original = path.read_text(encoding="utf-8")
        new_text, n, unresolved = relativize_text(original, path, vault)
        if args.apply and new_text != original:
            path.write_text(new_text, encoding="utf-8")
        elif not args.apply:
            for o, nw in zip(original.split("\n"), new_text.split("\n")):
                if o != nw:
                    print(f"  - {o}")
                    print(f"  + {nw}")
        mode = "APPLIED" if args.apply else "DRY-RUN"
        print(f"[{mode}] {args.only}: links_rewritten={n} unresolved={len(unresolved)}")
        return 0

    # Whole-corpus.
    if args.apply:
        stats = run_relativize_pass(knowledge, vault)
        print(f"[APPLIED] articles_seen={stats['articles_seen']} "
              f"articles_written={stats['articles_written']} "
              f"links_rewritten={stats['links_rewritten']}")
        return 0

    # Dry-run summary without writing.
    files_changed = links = 0
    unresolved_total: dict[str, int] = {}
    for path in iter_articles(knowledge):
        original = path.read_text(encoding="utf-8")
        new_text, n, unresolved = relativize_text(original, path, vault)
        for u in unresolved:
            unresolved_total[u] = unresolved_total.get(u, 0) + 1
        if n and new_text != original:
            files_changed += 1
            links += n
    print(f"[DRY-RUN] files_changed={files_changed} links_rewritten={links} "
          f"distinct_unresolved={len(unresolved_total)}")
    if unresolved_total:
        print("top unresolved (left untouched):")
        for tgt, cnt in sorted(unresolved_total.items(), key=lambda kv: -kv[1])[:25]:
            print(f"  {cnt:5d}  [[{tgt}]]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
