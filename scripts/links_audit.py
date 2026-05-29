"""`wiki links` — analyze (and optionally fix) broken wikilinks.

A broken link is one whose target resolves to no file on disk. They fall into
three classes, surfaced separately because each needs a different remedy:

- **media embeds** (`![[Pasted image …png]]`) — the asset is missing or lives
  somewhere the resolver can't see; check `_attachments/`.
- **doc placeholders** (`[[concepts/foo]]`, `[[…]]`) — illustrative examples
  inside articles about the wiki; not real links, leave them.
- **dangling article refs** — a real cross-reference whose target doesn't
  exist. Either slug-drift / wrong-bucket (fixable by rewriting the link) or a
  genuinely-missing article (fix = create it via compile/dream, or drop the
  link — NOT something this tool guesses at).

The fixer (`--fix`) only ever touches the first kind of dangling ref, and only
where the correction is **high-confidence**: an exact basename match in a
different bucket (`concepts/x` → `connections/x`), or a very-close string match
to an existing slug. Every correction is approved per-item by the operator —
fuzzy string distance confuses distinct entities (`people/eva` ≠ `people/alex`),
so nothing is applied blind. Rewrites land in the relative form the corpus uses.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ on path

from core.links import (  # noqa: E402
    WIKILINK_RE,
    _strip_frontmatter_and_fences,
    canonical_slug,
    has_ext,
    iter_articles,
    link_target,
    relative_link_for_slug,
    resolve_link,
    strip_table_escape,
)
from core.paths import KNOWLEDGE_DIR, ROOT_DIR  # noqa: E402
from core.utils import extract_wikilinks  # noqa: E402

# Confidence threshold for the fuzzy (non-bucket) suggestion tier. Below this,
# string distance starts confusing distinct entities, so we don't offer a fix.
FUZZY_CUTOFF = 0.85


@dataclass
class Dangling:
    target: str
    count: int
    example: str
    suggestion: str | None = None
    tier: str | None = None  # "bucket" | "fuzzy" | None


@dataclass
class Audit:
    embeds: list[tuple[str, int, str]] = field(default_factory=list)
    literals: list[tuple[str, int, str]] = field(default_factory=list)
    dangling: list[Dangling] = field(default_factory=list)

    @property
    def fixable(self) -> list[Dangling]:
        return [d for d in self.dangling if d.suggestion]


def _is_placeholder(target: str) -> bool:
    """Heuristic: illustrative example link, not a real reference."""
    if any(c in target for c in "<>…") or "..." in target:
        return True
    base = target.split("/")[-1]
    return base in {"foo", "bar", "baz", "slug", "xyz", "abc", "wikilink", "wikilinks"}


def _suggest(target: str, slugs: list[str], by_base: dict[str, list[str]]) -> tuple[str | None, str | None]:
    """Propose a correction for a dangling target. Returns (slug, tier)."""
    base = target.split("/")[-1].lower()
    # Tier 1 — exact basename in a different bucket (near-certain: wrong folder,
    # stray `knowledge/` prefix, doubled `concepts/projects/` prefix).
    bucket_hits = [s for s in by_base.get(base, []) if s != target]
    if bucket_hits:
        return min(bucket_hits, key=len), "bucket"
    # Tier 2 — very-close string match to a full slug.
    close = difflib.get_close_matches(target, slugs, n=1, cutoff=FUZZY_CUTOFF)
    if close:
        return close[0], "fuzzy"
    return None, None


def build_audit(knowledge_dir: Path, vault: Path) -> Audit:
    """Walk the corpus, find unresolved links, categorize + suggest. Read-only."""
    slugs = [s for a in iter_articles(knowledge_dir) if (s := canonical_slug(a, knowledge_dir))]
    by_base: dict[str, list[str]] = {}
    for s in slugs:
        by_base.setdefault(s.split("/")[-1].lower(), []).append(s)

    counts: Counter[str] = Counter()
    example: dict[str, str] = {}
    for art in iter_articles(knowledge_dir):
        text = art.read_text(encoding="utf-8")
        for _, line, live in _strip_frontmatter_and_fences(text.split("\n")):
            if not live:
                continue
            for raw in extract_wikilinks(line):
                t = link_target(raw)
                if resolve_link(t, art, vault) is None:
                    counts[t] += 1
                    example.setdefault(t, str(art.relative_to(knowledge_dir)))

    audit = Audit()
    for t, n in counts.most_common():
        if has_ext(t) and not t.endswith(".md"):
            audit.embeds.append((t, n, example[t]))
        elif _is_placeholder(t):
            audit.literals.append((t, n, example[t]))
        else:
            slug, tier = _suggest(t, slugs, by_base)
            audit.dangling.append(Dangling(t, n, example[t], slug, tier))
    return audit


def apply_fixes(knowledge_dir: Path, vault: Path, corrections: dict[str, str]) -> dict[str, int]:
    """Rewrite every approved broken target to its corrected slug, as a link
    relative to each source article. Preserves `!`/`#anchor`/`|alias`/`\\|`."""
    files = links = 0
    for art in iter_articles(knowledge_dir):
        original = art.read_text(encoding="utf-8")
        out_lines: list[str] = []
        changed = 0
        for _, line, live in _strip_frontmatter_and_fences(original.split("\n")):
            if not live:
                out_lines.append(line)
                continue

            def _sub(m: re.Match) -> str:
                nonlocal changed
                bang, target, heading, alias = m.groups()
                t, esc = strip_table_escape(target, alias)
                new_slug = corrections.get(t)
                if new_slug is None:
                    return m.group(0)
                changed += 1
                rel = relative_link_for_slug(new_slug, art, knowledge_dir)
                return f"{bang}[[{rel}{heading or ''}{esc}{alias or ''}]]"

            out_lines.append(WIKILINK_RE.sub(_sub, line))
        if changed:
            art.write_text("\n".join(out_lines), encoding="utf-8")
            files += 1
            links += changed
    return {"files": files, "links": links}


# ── report ──────────────────────────────────────────────────────────────


def _print_report(audit: Audit) -> None:
    n_dangling = sum(d.count for d in audit.dangling)
    print(f"Broken links: {len(audit.embeds)} media · {len(audit.literals)} placeholders · "
          f"{len(audit.dangling)} dangling refs ({n_dangling} occurrences)\n")

    if audit.fixable:
        print(f"── Fixable dangling refs ({len(audit.fixable)}) — `wiki links --fix` to apply ──")
        for d in sorted(audit.fixable, key=lambda x: (x.tier != "bucket", -x.count)):
            mark = "≡" if d.tier == "bucket" else "~"
            print(f"  {d.count:3d}x  [[{d.target}]]  {mark}→  [[{d.suggestion}]]   (e.g. {d.example})")
        print()

    missing = [d for d in audit.dangling if not d.suggestion]
    if missing:
        print(f"── Missing articles ({len(missing)}) — create via compile/dream, or drop the link ──")
        for d in sorted(missing, key=lambda x: -x.count):
            print(f"  {d.count:3d}x  [[{d.target}]]   (e.g. {d.example})")
        print()

    if audit.embeds:
        print(f"── Media embeds ({len(audit.embeds)}) — asset missing? check _attachments/ ──")
        for t, n, ex in audit.embeds:
            print(f"  {n:3d}x  ![[{t}]]   (e.g. {ex})")
        print()

    if audit.literals:
        print(f"── Doc placeholders ({len(audit.literals)}) — examples, leave them ──")
        for t, n, ex in audit.literals:
            print(f"  {n:3d}x  [[{t}]]   (e.g. {ex})")


def _run_fixer(knowledge_dir: Path, vault: Path, audit: Audit, assume_yes: bool) -> None:
    fixable = sorted(audit.fixable, key=lambda x: (x.tier != "bucket", -x.count))
    if not fixable:
        print("No high-confidence fixable links. Nothing to do.")
        return

    # `--yes` is non-interactive but only auto-approves the near-certain
    # bucket tier — fuzzy string matches confuse distinct entities
    # (`yesterday-ai` ≠ `yesterday-os`) and always need an eyeball.
    if assume_yes:
        approved = {d.target: d.suggestion for d in fixable if d.tier == "bucket"}
        skipped = [d for d in fixable if d.tier != "bucket"]
        if not approved:
            print("No bucket-tier corrections to auto-apply. Run interactively for fuzzy matches.")
            return
        stats = apply_fixes(knowledge_dir, vault, approved)
        print(f"Applied {len(approved)} bucket-tier correction(s): {stats['links']} link(s) "
              f"rewritten across {stats['files']} file(s).")
        if skipped:
            print(f"Skipped {len(skipped)} fuzzy match(es) — run `wiki links --fix` interactively to review.")
        return

    if not sys.stdin.isatty():
        print("--fix needs a TTY for per-item approval (or pass --yes for bucket-tier only). Aborting.",
              file=sys.stderr)
        sys.exit(2)

    approved: dict[str, str] = {}
    apply_all = False
    print(f"{len(fixable)} fixable links. [y]es / [n]o / [a]ll / [q]uit\n"
          "  ≡ = exact basename, different bucket (near-certain)   ~ = close string match\n")
    for d in fixable:
        mark = "≡" if d.tier == "bucket" else "~"
        if apply_all:
            approved[d.target] = d.suggestion
            continue
        ans = input(f"  {d.count:3d}x  [[{d.target}]]  {mark}→  [[{d.suggestion}]]  ? [y/n/a/q] ").strip().lower()
        if ans == "q":
            break
        if ans == "a":
            apply_all = True
            approved[d.target] = d.suggestion
        elif ans == "y":
            approved[d.target] = d.suggestion

    if not approved:
        print("\nNothing approved.")
        return
    stats = apply_fixes(knowledge_dir, vault, approved)
    print(f"\nApplied {len(approved)} correction(s): {stats['links']} link(s) rewritten "
          f"across {stats['files']} file(s).")


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze (and optionally fix) broken wikilinks.")
    ap.add_argument("--fix", action="store_true", help="Interactively rewrite high-confidence dangling refs")
    ap.add_argument("--yes", action="store_true", help="With --fix: apply all high-confidence corrections (no prompt)")
    args = ap.parse_args()

    if not KNOWLEDGE_DIR.is_dir():
        print(f"no knowledge/ under {ROOT_DIR}", file=sys.stderr)
        return 2

    audit = build_audit(KNOWLEDGE_DIR, ROOT_DIR)
    if args.fix:
        _run_fixer(KNOWLEDGE_DIR, ROOT_DIR, audit, args.yes)
    else:
        _print_report(audit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
