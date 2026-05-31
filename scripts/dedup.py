"""`wiki dedup` — interactive entity deduplication for transcription-noise duplicates.

STT transcribers (Jamie, voice) introduce *consistent* spelling noise that
creates silent duplicate entity pages: `josefine-bartsch.md` vs `josephine-bartc.md`
(same person), `veltari.md` vs `veltary.md` (real GmbH vs phantom). These split
knowledge across two pages, plant phantom wikilink targets, and contaminate
future compile passes.

This module is the detection + interactive-merge layer. Detection is
**stdlib-only and $0** — no `rapidfuzz` / `jellyfish` C-extension dependency:

  1. fuzzy string distance (`difflib.SequenceMatcher`) on normalized titles,
  2. a German-aware phonetic key (vowel-dropping + consonant folding, NOT
     English-biased Soundex/Metaphone — the failure mode is German names),
  3. shared `compiled_from` sources (two pages citing the same transcript).

The merge is **operator-guided** — every merge requires explicit confirmation,
never automatic. On confirm it folds B's Timeline / Action Items / Open Threads
into A, unions frontmatter (`aliases` + `compiled_from`), backs up + deletes B,
rewrites every `[[wikilink]]` B→A across `knowledge/` (via `core.links`, the
single wikilink resolver — never a second hand-rolled rewriter), and records a
canonical-name hard fact via `facts.correct` so lint flags any reappearance.

Spec: `.ytstack/backlog/entity-dedup.md` (issue #3).

Usage:
    wiki dedup                       detect + interactive loop (default)
    wiki dedup --suggest-only        print candidate list, no loop
    wiki dedup --dry-run             walk without writing
    wiki dedup merge B --into A      standalone known-pair merge
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml

from core.links import WIKILINK_RE, relative_target, resolve_link, strip_table_escape

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("dedup")

# Entity buckets dedup operates on. People + projects + areas are the
# free-form named-entity pages STT noise duplicates; concepts/facts/takes/qa
# are not person-named and are out of scope.
ENTITY_KINDS = ("people", "projects", "areas")

# Above this per-bucket size, skip the within-bucket fuzzy O(k²) scan and log
# it (per CLAUDE.md: surface every coverage cap, never silently truncate). The
# phonetic-collision + shared-source signals still apply to large buckets.
MAX_FUZZY_BUCKET = 400

# A phonetic key shorter than this is too lossy to trust on a *fuzzy* (non-exact)
# match — vowel-drop collapses spelling and short keys collide spuriously.
MIN_PHONETIC_KEY_LEN = 4

# Exact-collision proposals need a key of at least this length. `Veltari`/
# `Veltary` → `fltr` (4) is a legit collision worth surfacing; `Tim`/`Tom` → `tm`
# (2) is a single-consonant collapse that would just be noise.
MIN_PHONETIC_EXACT_LEN = 3

# German-aware phonetic folding, applied longest-first on the normalized
# (lowercased, de-accented, alpha-only) string. Tuned for the real failure
# mode — German names mistranscribed by an English-leaning STT model.
_PHONETIC_SUBS: tuple[tuple[str, str], ...] = (
    ("sch", "s"),
    ("tsch", "s"),
    ("ph", "f"),
    ("th", "t"),
    ("ck", "k"),
    ("tz", "ts"),
    ("dt", "t"),
    ("qu", "k"),
    ("ch", "k"),
    ("z", "ts"),
    ("c", "k"),
    ("v", "f"),
    ("w", "f"),
    ("y", "i"),
)


# ── Normalization + phonetic key ─────────────────────────────────────


def _strip_accents(s: str) -> str:
    """Decompose + drop combining marks: ä→a, é→e, ñ→n. ß→ss handled first."""
    s = s.replace("ß", "ss")
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize(name: str) -> str:
    """Lowercase, de-accent, keep only [a-z0-9]. Slug separators collapse out
    so `josefine-bartsch` and `Josefine Bartsch` normalize identically."""
    s = _strip_accents(name.lower())
    return "".join(c for c in s if c.isalnum())


def phonetic_key(name: str) -> str:
    """A German-aware phonetic fingerprint. Two names with the same key are
    near-certain transcription variants of each other.

    Pipeline: normalize → apply consonant-folding substitutions → drop all
    vowels except a leading one → collapse consecutive duplicates. Vowel-drop
    is what makes `veltari`→`fltr` and `veltary`→`fltr` collide despite
    different spellings; the consonant folds catch `ph/f`, `c/k`, `tz/ts`,
    `sch/s`."""
    s = normalize(name)
    if not s:
        return ""
    for old, new in _PHONETIC_SUBS:
        s = s.replace(old, new)
    vowels = set("aeiou")
    out: list[str] = []
    for i, ch in enumerate(s):
        if ch in vowels and i != 0:
            continue
        if out and out[-1] == ch:  # collapse doubles
            continue
        out.append(ch)
    return "".join(out)


def title_similarity(a: str, b: str) -> float:
    """0..1 fuzzy ratio on normalized titles (difflib, stdlib)."""
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


# ── Entity model ─────────────────────────────────────────────────────


@dataclass
class EntityPage:
    path: Path
    slug: str
    kind: str  # people | projects | areas
    title: str
    aliases: list[str] = field(default_factory=list)
    compiled_from: list[str] = field(default_factory=list)

    @property
    def names(self) -> list[str]:
        """Title + every alias — all the strings that should match a variant."""
        return [self.title, *self.aliases]


def split_frontmatter(text: str) -> tuple[dict, str]:
    """(frontmatter dict, body). Tolerant — returns ({}, text) when absent."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    try:
        fm = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, text[end + 5 :]


def _first_h1(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _as_str_list(value: object) -> list[str]:
    """Coerce a frontmatter value to list[str]. Guards JSON-column shapes —
    a scalar becomes a 1-list, a list keeps only str items."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return []


def load_entity(path: Path, kind: str) -> EntityPage:
    text = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    title = (
        (fm.get("title") or fm.get("name") or "").strip()
        or _first_h1(body)
        or path.stem.replace("-", " ")
    )
    return EntityPage(
        path=path,
        slug=path.stem,
        kind=kind,
        title=title,
        aliases=_as_str_list(fm.get("aliases")),
        compiled_from=_as_str_list(fm.get("compiled_from")),
    )


def load_entities(knowledge_dir: Path) -> list[EntityPage]:
    """Every entity page under knowledge/{people,projects,areas}/."""
    out: list[EntityPage] = []
    for kind in ENTITY_KINDS:
        d = knowledge_dir / kind
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.md")):
            if path.name.startswith("."):
                continue
            try:
                out.append(load_entity(path, kind))
            except OSError:
                continue
    return out


# ── Candidate detection ──────────────────────────────────────────────


@dataclass
class CandidatePair:
    a: EntityPage
    b: EntityPage
    confidence: float
    reasons: list[str]

    @property
    def key(self) -> frozenset[str]:
        return frozenset((self.a.slug, self.b.slug))


def _best_name_similarity(a: EntityPage, b: EntityPage) -> float:
    """Max fuzzy ratio over the cross-product of both pages' names (title +
    aliases) — an alias on one side may match the other's title."""
    return max(
        (title_similarity(na, nb) for na in a.names for nb in b.names),
        default=0.0,
    )


def find_candidates(
    entities: list[EntityPage], *, threshold: float
) -> list[CandidatePair]:
    """Ranked duplicate-candidate pairs. Three signals, deduped by pair:

    1. phonetic-key collision (within same kind)    → strong base 0.9
    2a. fuzzy title ratio ≥ threshold (within kind, bucketed by first letter
        to bound the O(k²) scan)
    2b. phonetic-key fuzzy ≥ (threshold − 0.05), keys ≥ MIN_PHONETIC_KEY_LEN —
        catches `josefine-bartsch`/`josephine-bartc` where the spelling diverges in
        the last consonant (`sch`/`c`) so raw fuzzy dips below threshold but
        the noise-stripped keys stay close
    3. shared `compiled_from` source                → BOOST-ONLY

    Pairs are scored by max name-signal. Cross-kind pairs are never proposed.

    Shared-source is deliberately boost-only (deviation from issue #3, which
    listed it as a standalone signal): on real vaults two *different* project
    pages routinely share a `compiled_from` daily-digest that merely mentions
    both — co-occurrence, not duplication. Validated against the lxw vault
    2026-05-31: standalone shared-source produced ~20 false pairs (llm-wiki ⨯
    sunoflow, …). It now only *boosts* a pair already surfaced by name
    similarity (a name match that ALSO shares a source is extra-likely a dup).
    """
    phonetic_floor = max(0.0, threshold - 0.05)
    pairs: dict[frozenset[str], CandidatePair] = {}

    def _bump(a: EntityPage, b: EntityPage, conf: float, reason: str) -> None:
        k = frozenset((a.slug, b.slug))
        existing = pairs.get(k)
        if existing is None:
            pairs[k] = CandidatePair(a=a, b=b, confidence=conf, reasons=[reason])
            return
        existing.confidence = min(1.0, max(existing.confidence, conf))
        if reason not in existing.reasons:
            existing.reasons.append(reason)

    by_kind: dict[str, list[EntityPage]] = {}
    for e in entities:
        by_kind.setdefault(e.kind, []).append(e)

    for kind, group in by_kind.items():
        # Signal 1 — phonetic-key collision buckets.
        phon: dict[str, list[EntityPage]] = {}
        for e in group:
            key = phonetic_key(e.title)
            if key:
                phon.setdefault(key, []).append(e)
        for key, bucket in phon.items():
            if len(bucket) < 2 or len(key) < MIN_PHONETIC_EXACT_LEN:
                continue
            for a, b in combinations(bucket, 2):
                _bump(a, b, 0.9, "phonetic-key match")

        # Signal 2 — fuzzy title ratio, bucketed by first normalized letter to
        # bound the pairwise scan (CLAUDE.md O(N²) rule).
        first: dict[str, list[EntityPage]] = {}
        for e in group:
            n = normalize(e.title)
            first.setdefault(n[:1], []).append(e)
        for letter, bucket in first.items():
            if len(bucket) > MAX_FUZZY_BUCKET:
                log.warning(
                    "fuzzy scan skipped for %s/'%s*' bucket (%d entities > %d cap); "
                    "phonetic + shared-source signals still apply",
                    kind, letter, len(bucket), MAX_FUZZY_BUCKET,
                )
                continue
            for a, b in combinations(bucket, 2):
                ratio = _best_name_similarity(a, b)
                if ratio >= threshold:
                    _bump(a, b, ratio, f"fuzzy title {ratio:.2f}")
                    continue
                # Phonetic-key fuzzy — spelling-noise-stripped near-match.
                pk_a, pk_b = phonetic_key(a.title), phonetic_key(b.title)
                if min(len(pk_a), len(pk_b)) < MIN_PHONETIC_KEY_LEN:
                    continue
                pratio = SequenceMatcher(None, pk_a, pk_b).ratio()
                if pratio >= phonetic_floor and pk_a != pk_b:
                    _bump(a, b, pratio, f"phonetic near-match {pratio:.2f}")

        # Signal 3 — shared compiled_from source. BOOST-ONLY: only annotate +
        # raise confidence on pairs an earlier signal already surfaced. A
        # shared source alone is co-occurrence, not duplication (see docstring).
        by_source: dict[str, list[EntityPage]] = {}
        for e in group:
            for src in e.compiled_from:
                by_source.setdefault(src, []).append(e)
        for bucket in by_source.values():
            if len(bucket) < 2:
                continue
            for a, b in combinations(bucket, 2):
                k = frozenset((a.slug, b.slug))
                existing = pairs.get(k)
                if existing is None:
                    continue  # don't create a candidate from co-occurrence
                existing.confidence = min(1.0, existing.confidence + 0.05)
                if "shared source" not in existing.reasons:
                    existing.reasons.append("shared source")

    ranked = sorted(pairs.values(), key=lambda p: p.confidence, reverse=True)
    return ranked


# ── Markdown section merge ───────────────────────────────────────────

# H2 sections whose bullet content is appended from B into A on merge. `State`
# is prose, not list-shaped — it's left as A's (B's is preserved in the .bak).
MERGEABLE_SECTIONS = ("Timeline", "Action Items", "Open Threads")


def _split_sections(body: str) -> list[tuple[str | None, list[str]]]:
    """Split a markdown body into (h2_title_or_None, lines) blocks. The first
    block (None) is the preamble before any `## ` heading."""
    blocks: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in body.splitlines():
        if line.startswith("## "):
            blocks.append((line[3:].strip(), [line]))
        else:
            blocks[-1][1].append(line)
    return blocks


def _section_bullets(lines: list[str]) -> list[str]:
    """Non-empty content lines of a section (excluding its `## ` heading)."""
    return [ln for ln in lines[1:] if ln.strip()]


def merge_bodies(body_a: str, body_b: str) -> str:
    """Fold B's mergeable-section bullets into A. Existing bullets (by stripped
    text) are not duplicated. Sections present in B but not A are appended."""
    a_blocks = _split_sections(body_a)
    b_sections = {
        title: _section_bullets(lines)
        for title, lines in _split_sections(body_b)
        if title in MERGEABLE_SECTIONS
    }

    out: list[str] = []
    seen_titles: set[str] = set()
    for title, lines in a_blocks:
        if title in MERGEABLE_SECTIONS and title in b_sections:
            seen_titles.add(title)
            existing = {ln.strip() for ln in _section_bullets(lines)}
            additions = [ln for ln in b_sections[title] if ln.strip() not in existing]
            block_lines = list(lines)
            while block_lines and not block_lines[-1].strip():
                block_lines.pop()
            block_lines.extend(additions)
            out.append("\n".join(block_lines))
        else:
            out.append("\n".join(lines))

    # Sections in B but absent from A — append as new H2 blocks.
    for title in MERGEABLE_SECTIONS:
        if title in b_sections and title not in seen_titles:
            out.append(f"## {title}\n" + "\n".join(b_sections[title]))

    return "\n".join(out).rstrip() + "\n"


def _union_preserve(base: list[str], extra: list[str]) -> list[str]:
    seen = set(base)
    merged = list(base)
    for item in extra:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


# ── Wikilink rewrite B → A ───────────────────────────────────────────


def rewrite_links(
    knowledge_dir: Path,
    vault: Path,
    target: Path,
    new_slug_path: str,
    *,
    dry_run: bool,
) -> list[Path]:
    """Rewrite every wikilink across knowledge/ that resolves to ``target`` so
    it points at ``new_slug_path`` (e.g. ``people/josefine-bartsch``), rendered
    relative to each source. Reuses `core.links.resolve_link` — the single
    resolver — so behaviour never drifts from the relativize/backlinks passes.

    Returns the list of files changed (or that *would* change under dry-run)."""
    target = target.resolve()
    new_resolved = (knowledge_dir / f"{new_slug_path}.md").resolve()
    changed: list[Path] = []

    for path in sorted(knowledge_dir.rglob("*.md")):
        if any(p.startswith(".") for p in path.relative_to(knowledge_dir).parts):
            continue
        if path.resolve() == target:
            continue  # B is being deleted; don't bother rewriting it
        try:
            original = path.read_text(encoding="utf-8")
        except OSError:
            continue

        def _sub(m: "object") -> str:
            bang, tgt, heading, alias = m.groups()
            clean, esc = strip_table_escape(tgt, alias)
            resolved = resolve_link(clean, path, vault)
            if resolved is None or resolved.resolve() != target:
                return m.group(0)
            new_target = relative_target(new_resolved, path, original_has_ext=False)
            return f"{bang}[[{new_target}{heading or ''}{esc}{alias or ''}]]"

        new_text = WIKILINK_RE.sub(_sub, original)
        if new_text != original:
            changed.append(path)
            if not dry_run:
                path.write_text(new_text, encoding="utf-8")
    return changed


# ── Hard-fact registration ───────────────────────────────────────────


def record_canonical_fact(
    wrong_name: str, correct_name: str, *, source_slug: str, dry_run: bool
) -> Path | None:
    """Register a `status: negation` hard fact so lint flags any future
    reappearance of the mistranscribed name. Reuses `facts.correct` writers."""
    if dry_run:
        return None
    from core.utils import slugify, today_iso
    from facts.correct import _backup, _fact_path, _write_fact

    slug = slugify(f"transcription-error-{wrong_name}")
    path = _fact_path(slug)
    _backup(path)
    today = today_iso()
    frontmatter = {
        "title": f"{wrong_name!r} is a transcription error",
        "type": "fact",
        "status": "negation",
        "trust": "confirmed",
        "sources": [f"dedup:merge:{source_slug}"],
        "created": today,
        "updated": today,
        "applied": False,
        "negation_terms": [wrong_name.lower()],
    }
    body = (
        f"`{wrong_name}` is a transcription/spelling error for **{correct_name}**. "
        f"The two were merged via `wiki dedup`; never re-create a separate "
        f"`{wrong_name}` entity page."
    )
    _write_fact(path, frontmatter, body)
    return path


# ── Merge operation ──────────────────────────────────────────────────


@dataclass
class MergeResult:
    keep: Path
    removed: Path
    backup: Path | None
    links_rewritten: list[Path]
    fact: Path | None
    dry_run: bool


def merge_pages(
    keep: EntityPage,
    drop: EntityPage,
    *,
    canonical_name: str,
    knowledge_dir: Path,
    vault: Path,
    dry_run: bool,
) -> MergeResult:
    """Merge ``drop`` into ``keep``. Folds B's mergeable sections + frontmatter
    into A, rewrites wikilinks B→A, backs up + deletes B, records a hard fact.

    Idempotent on the section/frontmatter side (re-running dedups by content).
    Never a hard `rm` — B is copied to `<file>.bak.<ts>` first."""
    if keep.kind != drop.kind:
        raise ValueError(f"refusing cross-kind merge: {keep.kind} vs {drop.kind}")

    keep_text = keep.path.read_text(encoding="utf-8")
    drop_text = drop.path.read_text(encoding="utf-8")
    keep_fm, keep_body = split_frontmatter(keep_text)
    drop_fm, drop_body = split_frontmatter(drop_text)

    # Section + frontmatter merge.
    merged_body = merge_bodies(keep_body, drop_body)
    merged_fm = dict(keep_fm)
    new_aliases = _union_preserve(
        _as_str_list(keep_fm.get("aliases")),
        [drop.title, *_as_str_list(drop_fm.get("aliases"))],
    )
    # The canonical title stays out of its own alias list.
    new_aliases = [a for a in new_aliases if normalize(a) != normalize(canonical_name)]
    if new_aliases:
        merged_fm["aliases"] = new_aliases
    merged_compiled = _union_preserve(
        _as_str_list(keep_fm.get("compiled_from")),
        _as_str_list(drop_fm.get("compiled_from")),
    )
    if merged_compiled:
        merged_fm["compiled_from"] = merged_compiled
    if canonical_name.strip():
        merged_fm["title"] = canonical_name.strip()

    if not dry_run:
        serialized = yaml.safe_dump(
            merged_fm, sort_keys=False, allow_unicode=True
        ).rstrip()
        keep.path.write_text(
            f"---\n{serialized}\n---\n\n{merged_body.lstrip()}", encoding="utf-8"
        )

    # Wikilink rewrite B → A (canonical knowledge-relative slug path).
    new_slug_path = f"{keep.kind}/{keep.slug}"
    links = rewrite_links(
        knowledge_dir, vault, drop.path, new_slug_path, dry_run=dry_run
    )

    # Back up + delete B.
    backup: Path | None = None
    if not dry_run:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = drop.path.with_suffix(drop.path.suffix + f".bak.{ts}")
        shutil.copy2(drop.path, backup)
        drop.path.unlink()

    # Canonical-name hard fact.
    fact = record_canonical_fact(
        drop.title, canonical_name, source_slug=keep.slug, dry_run=dry_run
    )

    return MergeResult(
        keep=keep.path,
        removed=drop.path,
        backup=backup,
        links_rewritten=links,
        fact=fact,
        dry_run=dry_run,
    )


# ── CLI ──────────────────────────────────────────────────────────────


def _print_candidates(cands: list[CandidatePair]) -> None:
    if not cands:
        print("No duplicate candidates found.")
        return
    print(f"Found {len(cands)} candidate pair(s):\n")
    for i, c in enumerate(cands, 1):
        print(f"[{i}] {c.confidence:.2f}  {c.a.kind}/")
        print(f"      A: {c.a.slug:32s} \"{c.a.title}\"")
        print(f"      B: {c.b.slug:32s} \"{c.b.title}\"")
        print(f"      → {', '.join(c.reasons)}\n")


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def _interactive_loop(
    cands: list[CandidatePair], *, knowledge_dir: Path, vault: Path, dry_run: bool
) -> int:
    merged = 0
    total = len(cands)
    for i, c in enumerate(cands, 1):
        print(f"\n[{i}/{total}] potential duplicate ({c.confidence:.2f} · {', '.join(c.reasons)}):")
        print(f"  A: {c.a.kind}/{c.a.slug}  \"{c.a.title}\"")
        print(f"  B: {c.b.kind}/{c.b.slug}  \"{c.b.title}\"")
        ans = _ask("  → same entity? [y/N/skip/quit] ").lower()
        if ans in ("q", "quit"):
            break
        if ans not in ("y", "yes"):
            continue
        which = _ask(f"  → correct name? [A=\"{c.a.title}\" / B=\"{c.b.title}\" / type] ").strip()
        if which.lower() in ("a", ""):
            keep, drop, canonical = c.a, c.b, c.a.title
        elif which.lower() == "b":
            keep, drop, canonical = c.b, c.a, c.b.title
        else:
            keep, drop, canonical = c.a, c.b, which
        confirm = _ask(
            f"  → merge {drop.slug} INTO {keep.slug} as \"{canonical}\"? "
            f"{'(dry-run) ' if dry_run else ''}[y/N] "
        ).lower()
        if confirm not in ("y", "yes"):
            continue
        res = merge_pages(
            keep, drop, canonical_name=canonical,
            knowledge_dir=knowledge_dir, vault=vault, dry_run=dry_run,
        )
        _report_merge(res, keep, drop)
        merged += 1
    print(f"\nDone. {merged} merge(s){' (dry-run, nothing written)' if dry_run else ''}.")
    return 0


def _report_merge(res: MergeResult, keep: EntityPage, drop: EntityPage) -> None:
    tag = "(dry-run) " if res.dry_run else ""
    print(f"  {tag}✓ merged {drop.slug} → {keep.slug}")
    print(f"      links rewritten in {len(res.links_rewritten)} file(s)")
    if res.backup:
        print(f"      B backed up → {res.backup.name}, deleted")
    if res.fact:
        print(f"      hard fact → {res.fact.name}")


def _resolve_entity_arg(arg: str, knowledge_dir: Path) -> EntityPage | None:
    """Resolve a `merge` positional: bare slug, kind/slug, or a path."""
    p = Path(arg)
    if p.suffix == ".md" and p.exists():
        kind = p.parent.name
        return load_entity(p.resolve(), kind if kind in ENTITY_KINDS else "people")
    for e in load_entities(knowledge_dir):
        if e.slug == arg or f"{e.kind}/{e.slug}" == arg:
            return e
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--suggest-only", action="store_true",
                        help="print the candidate list and exit (no interactive loop)")
    parser.add_argument("--dry-run", action="store_true",
                        help="walk + merge without writing anything to disk")
    parser.add_argument("--threshold", type=float, default=None,
                        help="fuzzy match floor 0..1 (default: limits.dedup_fuzzy_threshold)")
    sub = parser.add_subparsers(dest="cmd")
    p_merge = sub.add_parser("merge", help="standalone merge of a known pair")
    p_merge.add_argument("drop", help="entity to merge away (slug | kind/slug | path)")
    p_merge.add_argument("--into", required=True, help="entity to keep (slug | kind/slug | path)")
    p_merge.add_argument("--name", default=None, help="canonical name (default: the kept page's title)")
    # Accept --dry-run AFTER `merge` too (operators type it last). A separate
    # dest avoids the argparse quirk where the subparser default clobbers the
    # top-level value; the two are OR-ed below.
    p_merge.add_argument("--dry-run", action="store_true", dest="merge_dry_run",
                         help="show the merge without writing")
    args = parser.parse_args(argv)
    # Honour --dry-run in either position (top-level or after `merge`).
    args.dry_run = args.dry_run or getattr(args, "merge_dry_run", False)

    from core.paths import KNOWLEDGE_DIR, ROOT_DIR

    if not KNOWLEDGE_DIR.is_dir():
        log.error("no knowledge/ directory at %s", KNOWLEDGE_DIR)
        return 1

    threshold = args.threshold
    if threshold is None:
        try:
            from core.config import CONFIG
            threshold = CONFIG.limits.dedup_fuzzy_threshold
        except Exception:  # noqa: BLE001 — config optional for detection
            threshold = 0.85

    if args.cmd == "merge":
        keep = _resolve_entity_arg(args.into, KNOWLEDGE_DIR)
        drop = _resolve_entity_arg(args.drop, KNOWLEDGE_DIR)
        if keep is None or drop is None:
            log.error("could not resolve %s",
                      args.into if keep is None else args.drop)
            return 1
        if keep.slug == drop.slug:
            log.error("refusing to merge a page into itself")
            return 1
        canonical = args.name or keep.title
        print(f"merge {drop.kind}/{drop.slug} INTO {keep.kind}/{keep.slug} as \"{canonical}\"")
        confirm = _ask(f"  → confirm? {'(dry-run) ' if args.dry_run else ''}[y/N] ").lower()
        if confirm not in ("y", "yes"):
            print("aborted.")
            return 0
        res = merge_pages(
            keep, drop, canonical_name=canonical,
            knowledge_dir=KNOWLEDGE_DIR, vault=ROOT_DIR, dry_run=args.dry_run,
        )
        _report_merge(res, keep, drop)
        return 0

    entities = load_entities(KNOWLEDGE_DIR)
    cands = find_candidates(entities, threshold=threshold)

    if args.suggest_only:
        _print_candidates(cands)
        return 0
    if not cands:
        print("No duplicate candidates found.")
        return 0
    if not sys.stdin.isatty():
        # Non-interactive caller (hook, pipe) — print, don't block on input.
        _print_candidates(cands)
        print("(non-interactive: run `wiki dedup` in a terminal to merge)")
        return 0
    return _interactive_loop(
        cands, knowledge_dir=KNOWLEDGE_DIR, vault=ROOT_DIR, dry_run=args.dry_run
    )


if __name__ == "__main__":
    sys.exit(main())
