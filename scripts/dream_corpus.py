"""Dream-cycle corpus layer — what one entity's synthesis reads (M016 sampled activation).

The tiered corpus assembly (`collect_corpus_tiered` + its prompt render), the
activation side-state that records which substrate a dream has already seen, and
the insufficient-corpus backoff that keeps a no-op entity out of the sweep.
`ROOT_DIR` is read here, in `dream.py` and in `dream_priority.py` — tests patch it
through `tests/_dream_paths.py:patch_dream_path`, never on one module.
"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from core import frontmatter
from core.config import CONFIG
from core.paths import ROOT_DIR, STATE_DIR
from core.state_store import StateStore, store_for
from dream_model import EntityRef, _parse_iso_date

log = logging.getLogger("dream")


# ── Corpus assembly ──────────────────────────────────────────────────
#
# M016 sampled-activation: a 4-tier corpus assembly that bounds prompt size
# by construction (target ~600 KB total, independent of vault size). Replaces
# the M014 "load every mentioning file" approach that hit context overflow
# on the operator's own entity page (~475 files / 2.3 MB → SDK kind=unknown).
#
# Tier 1 (always-in, ~200 KB):
#   - entity page itself
#   - operator-authored content (author: slug, compile_role: source-and-final)
#   - last N most-recent substrate files mentioning slug
#   - last M daily/<date>.md digests
# Tier 2 (weighted-sample older substrate, ~400 KB):
#   - score = importance × recency_decay × dreams_since_last_seen × (1+noise)
#   - top-K by score
# Tier 3 (conflict-aware reshape — prompt-side, not code-side):
#   - see prompts/dream_entity.md Step 2 mandate
# Tier 4 (hierarchical digest):
#   - daily/<date>.md is the M001 digest substrate; covered by Tier 1's
#     digest-day inclusion. Recursive weekly/monthly building deferred to M017.
#
# See `.ytstack/backlog/dream-sampled-activation.md` for the full design.


# Knowledge subfolders that hold operator-authored content (compile_role:
# source-and-final). Dream-cycle walks these too — operator's hand-curated
# concepts, areas, etc. ARE part of the entity's corpus even though they live
# in knowledge/ (which is engine-output otherwise). Amplification-loop guard:
# only files with `author:` matching the entity slug (or compiled_from match)
# are included — the regular compile-output concepts (no author) are skipped.
_OPERATOR_AUTHORED_ROOTS: tuple[str, ...] = ("concepts", "areas", "people", "projects")

# Importance weights for Tier-2 scoring. Path-prefix-keyed (matched in order,
# longest prefix wins). Default fallback 1.0. See research grounding in the
# spec doc — these are heuristics, not learned weights (A-Mem MoE gating
# is future work). Calibrated by operator-eye on lxw substrate.
_IMPORTANCE_RULES: tuple[tuple[str, float], ...] = (
    ("raw/memories/", 3.0),
    ("raw/transcripts/jamie/", 2.0),
    ("raw/transcripts/gmeet/", 2.0),
    ("raw/notes/longform/", 1.5),
    ("raw/notes/email/", 1.0),
    ("raw/notes/calendar/", 1.0),
    ("raw/notes/screenshots/", 0.8),
)

# Sentinel for "this file has never been dreamed" — large enough that any
# never-stamped file beats any stamped one on the dreams_since_last_seen term.
_NEVER_DREAMED_DAYS = 1_000_000.0

# Tier-1 / Tier-2 per-file truncation cap. Big enough to carry the load-bearing
# content of typical substrate (meeting transcripts run 5-15 KB; longform
# articles 10-30 KB) without letting one pathological 500 KB file dominate
# the budget alone.
_PER_FILE_TRUNCATION_CHARS = 8_000


def _mentions_entity(text: str, slug: str) -> bool:
    """Match slug as a whole word OR as the value of author/compiled_from."""
    pattern = re.compile(rf"(?<![a-z0-9_-]){re.escape(slug)}(?![a-z0-9_-])", re.IGNORECASE)
    return bool(pattern.search(text))


def _importance_for(rel_path: str) -> float:
    """Look up the importance weight for a substrate path (rel to vault root).

    Path-prefix match; longest prefix wins via _IMPORTANCE_RULES ordering
    (the tuple is hand-ordered most-specific first, so the first hit wins).
    Returns 1.0 if no rule matches.
    """
    norm = rel_path.replace("\\", "/")
    for prefix, weight in _IMPORTANCE_RULES:
        if norm.startswith(prefix):
            return weight
    return 1.0


def _recency_decay(mtime: float, *, now: float | None = None) -> float:
    """Soft 90-day half-life decay: 1 / (1 + days_since_mtime / 90).

    Older content competes but doesn't vanish — at 90 days, weight = 0.5;
    at 180, 0.33; at 365, 0.20.
    """
    ref = now if now is not None else time.time()
    days = max(0.0, (ref - mtime) / 86400.0)
    return 1.0 / (1.0 + days / 90.0)


# Side-state file for dream-cycle activation tracking. Keyed by
# vault-relative path -> ISO date. Kept OUT of substrate frontmatter so
# raw/ stays byte-identical (raw-is-immutable rule). Storage goes through
# the core.state_store facade (locked atomic writes + load-once cache) —
# the sweep consults this store once per SCORED file, so an uncached
# per-call disk parse was the recorded O(N²) hang shape.
_DREAM_ACTIVATION_FILE = STATE_DIR / "dream-activation.json"


def _activation_store() -> StateStore:
    """The activation map's StateStore. Resolved per call (not at import) so
    tests can monkeypatch `_DREAM_ACTIVATION_FILE`; format knobs keep the
    pre-facade serialization (sort_keys + trailing newline) byte-stable."""
    return store_for(_DREAM_ACTIVATION_FILE, sort_keys=True, trailing_newline=True)


def _load_dream_activation() -> dict[str, str]:
    """Cached snapshot of the activation map (read-only — writes go through
    `_stamp_last_dreamed_at`)."""
    return _activation_store().load()


# ── Insufficient-corpus backoff ─────────────────────────────────────
#
# When a dream RUNS but the agent returns the `INSUFFICIENT_CORPUS` sentinel
# (no synthesizable claims for the entity in the current corpus — common on
# generic-noun slugs whose mention-scan false-matches unrelated text, e.g.
# `kontakte` hitting the German word "Kontakte" in email metadata), the entity
# would otherwise be re-selected on EVERY sweep and re-burn a full SDK call
# (~$1) on a guaranteed no-op. We record each consecutive no-op and back the
# entity off with an exponential window (base = dream_cooldown_days, doubling
# per consecutive no-op, capped at scheduling.dream_insufficient_corpus_backoff_max_days).
# A successful synthesis clears the entry, so the entity returns to the normal
# cadence the moment real substrate lands. Applies to the SWEEP only — an
# explicit `wiki dream <slug>` bypasses it, same as cooldown. Keyed by slug.
_DREAM_INSUFFICIENT_FILE = STATE_DIR / "dream-insufficient-corpus.json"


def _insufficient_store() -> StateStore:
    """The backoff store's StateStore (same facade + format as the activation
    map; resolved per call so tests can monkeypatch the file constant)."""
    return store_for(_DREAM_INSUFFICIENT_FILE, sort_keys=True, trailing_newline=True)


def _load_insufficient_state() -> dict[str, dict]:
    """Cached snapshot of the backoff store (read-only — writes go through
    `_record_insufficient_corpus` / `_clear_insufficient_corpus`)."""
    return _insufficient_store().load()


def _record_insufficient_corpus(slug: str, *, when: datetime | None = None) -> int:
    """Bump the consecutive-INSUFFICIENT_CORPUS counter for `slug`, stamp the
    time, and return the new count. Tolerant — state-write failure logs and
    returns 0 so a backoff-bookkeeping hiccup never aborts a dream."""
    ref = when or datetime.now(UTC)
    result = {"count": 0}

    def _bump(data: dict) -> None:
        entry = data.get(slug) if isinstance(data.get(slug), dict) else {}
        count = int(entry.get("count", 0)) + 1
        data[slug] = {"count": count, "last_at": ref.isoformat()}
        result["count"] = count

    try:
        _insufficient_store().update(_bump)
        return result["count"]
    except OSError as exc:
        log.warning("  could not record insufficient-corpus backoff for %s: %s", slug, exc)
        return 0


def _clear_insufficient_corpus(slug: str) -> bool:
    """Drop any backoff entry for `slug` (called after a successful synthesis).
    Returns True if an entry was removed."""
    removed = {"v": False}

    def _drop(data: dict) -> None:
        if slug in data:
            del data[slug]
            removed["v"] = True

    try:
        if slug not in _insufficient_store().load():
            return False  # cached fast-path — skip a pointless locked rewrite
        _insufficient_store().update(_drop)
    except OSError as exc:
        log.warning("  could not clear insufficient-corpus backoff for %s: %s", slug, exc)
    return removed["v"]


def _insufficient_backoff_days(count: int, *, base_days: int, max_days: int) -> float:
    """Exponential backoff window in days: base * 2^(count-1), capped at max_days."""
    if count <= 0:
        return 0.0
    window = base_days * (2 ** (count - 1))
    return float(min(window, max_days))


def is_within_insufficient_backoff(
    entity: EntityRef,
    *,
    now: datetime | None = None,
    base_days: int | None = None,
    max_days: int | None = None,
) -> bool:
    """True iff `entity` is inside its insufficient-corpus backoff window.

    `max_days <= 0` disables the mechanism entirely (every entity passes)."""
    base = base_days if base_days is not None else CONFIG.scheduling.dream_cooldown_days
    cap = (
        max_days
        if max_days is not None
        else CONFIG.scheduling.dream_insufficient_corpus_backoff_max_days
    )
    if cap <= 0:
        return False
    entry = _load_insufficient_state().get(entity.slug)
    if not isinstance(entry, dict):
        return False
    count = int(entry.get("count", 0))
    last = _parse_iso_date(entry.get("last_at"))
    if count <= 0 or last is None:
        return False
    window = _insufficient_backoff_days(count, base_days=max(1, base), max_days=cap)
    ref = now or datetime.now(UTC)
    age_days = (ref - last).total_seconds() / 86400.0
    return age_days < window


def _get_last_dreamed_at(path: Path) -> datetime | None:
    """Read `last_dreamed_at` for a substrate file.

    Lookup order:
      1. Side-state file (state/dream-activation.json) — canonical since
         the raw-is-immutable fix.
      2. Legacy frontmatter `last_dreamed_at:` — back-compat for files
         polluted before the fix landed. Never written; orphan keys in
         raw/ frontmatter are left untouched by design.
    Returns None if neither source has a parseable value.
    """
    try:
        rel = str(path.relative_to(ROOT_DIR))
    except ValueError:
        rel = str(path)
    activation = _load_dream_activation()
    state_value = activation.get(rel)
    if state_value:
        parsed = _parse_iso_date(state_value)
        if parsed is not None:
            return parsed
    # Legacy frontmatter fall-back (read-only).
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    fm, _body = frontmatter.parse(text)
    return _parse_iso_date(fm.get("last_dreamed_at"))


def _dreams_since_last_seen_days(path: Path, *, now: datetime | None = None) -> float:
    """Return days since the file's last_dreamed_at, or sentinel if never."""
    stamp = _get_last_dreamed_at(path)
    if stamp is None:
        return _NEVER_DREAMED_DAYS
    ref = now or datetime.now(UTC)
    days = (ref - stamp).total_seconds() / 86400.0
    return max(1.0, days)


def _compute_sampling_score(
    path: Path,
    *,
    vault_root: Path,
    rng: random.Random,
    now: float | None = None,
) -> float:
    """Tier-2 activation score: importance × recency × dreams_since × noise.

    `rng` is passed explicitly so tests can pin determinism via a seeded
    Random instance; production uses the module-global random module.
    """
    try:
        rel = str(path.relative_to(vault_root))
    except ValueError:
        rel = str(path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    importance = _importance_for(rel)
    recency = _recency_decay(mtime, now=now)
    dreams_since = _dreams_since_last_seen_days(path)
    noise = rng.uniform(0.85, 1.15)
    return importance * recency * dreams_since * noise


def _stamp_last_dreamed_at(paths: list[Path], when: datetime | None = None) -> int:
    """Record `last_dreamed_at` for many substrate files in ONE locked
    read-modify-write on the side-state file (`state/dream-activation.json`).
    NEVER touches the substrate files themselves — raw/ is immutable (engine
    reads, never writes).

    Returns the number of files newly stamped. Idempotent — same-day stamps
    are no-ops (already-stamped files are pre-filtered on the cached
    snapshot, so an all-stamped corpus doesn't even rewrite the store).
    Tolerant — a store-write failure logs and returns 0 so bookkeeping never
    aborts a dream. The per-file load+rewrite this replaces was
    O(stamped × store-size) — the recorded per-item-over-all-items hang shape.
    """
    stamp = (when or datetime.now(UTC)).strftime("%Y-%m-%d")
    rels: list[str] = []
    for path in paths:
        try:
            rels.append(str(path.relative_to(ROOT_DIR)))
        except ValueError:
            rels.append(str(path))
    store = _activation_store()
    cached = store.load()
    pending = [
        rel
        for rel in rels
        if not (isinstance(cached.get(rel), str) and cached[rel].startswith(stamp))
    ]
    if not pending:
        return 0

    stamped = {"n": 0}

    def _apply(data: dict) -> None:
        for rel in pending:
            existing = data.get(rel)
            if isinstance(existing, str) and existing.startswith(stamp):
                continue  # another process stamped it since our cached read
            data[rel] = stamp
            stamped["n"] += 1

    try:
        store.update(_apply)
    except OSError as exc:
        log.warning("  could not stamp last_dreamed_at for %d file(s): %s", len(pending), exc)
        return 0
    return stamped["n"]


def _write_last_dreamed_at(path: Path, when: datetime | None = None) -> bool:
    """Single-file form of `_stamp_last_dreamed_at`. Returns True if the
    side-state was updated (False = already stamped today or write failure)."""
    return _stamp_last_dreamed_at([path], when=when) == 1


# ── Tiered corpus collection ────────────────────────────────────────


def _scan_mentioning_files(
    entity: EntityRef,
    *,
    vault_root: Path,
    include_authored: bool = True,
) -> list[tuple[float, Path]]:
    """Walk all substrate roots once, return (mtime, path) for matches.

    Returns absolute paths sorted newest-first. Includes:
      - raw/** + daily/** where the text body mentions the slug
      - knowledge/{concepts,areas,people,projects}/** when include_authored
        AND the file matches (author: slug or compiled_from contains slug)
    Excludes the entity page itself.
    """
    found: list[tuple[float, Path]] = []
    scan_dirs: list[Path] = [vault_root / "raw", vault_root / "daily"]
    if include_authored:
        for sub in _OPERATOR_AUTHORED_ROOTS:
            scan_dirs.append(vault_root / "knowledge" / sub)
    for sub in scan_dirs:
        if not sub.exists():
            continue
        for path in sub.rglob("*.md"):
            if path.resolve() == entity.page.resolve():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if _mentions_entity(text, entity.slug):
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    mtime = 0.0
                found.append((mtime, path))
    found.sort(key=lambda t: t[0], reverse=True)
    return found


def _is_operator_authored_for(path: Path, entity: EntityRef, *, vault_root: Path) -> bool:
    """True if this file's frontmatter declares the entity as author or
    compiled_from contains the entity slug. Hard-included by Tier 1 — these
    are load-bearing operator-deliberate writings that can never be evicted.
    """
    try:
        rel = path.relative_to(vault_root)
    except ValueError:
        return False
    if not str(rel).startswith("knowledge/"):
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    fm, _body = frontmatter.parse(text)
    author = fm.get("author")
    if isinstance(author, str) and author.strip().lower() == entity.slug.lower():
        return True
    if isinstance(author, list) and any(
        isinstance(a, str) and a.strip().lower() == entity.slug.lower() for a in author
    ):
        return True
    compiled_from = fm.get("compiled_from")
    if isinstance(compiled_from, list):
        for cf in compiled_from:
            if isinstance(cf, str) and entity.slug.lower() in cf.lower():
                return True
    return False


def _recent_daily_digest_paths(vault_root: Path, *, days: int) -> list[Path]:
    """Return absolute paths to the last N daily/<date>.md rollup digests.

    The M001 daily-as-rollup architecture stores per-source captures under
    daily/<date>/ subdirs AND a digest at daily/<date>.md. We only want the
    digest (it's the compressed signal), not the per-source raw captures.
    Sorted newest-first.
    """
    if days <= 0:
        return []
    daily = vault_root / "daily"
    if not daily.exists():
        return []
    found: list[tuple[str, Path]] = []
    for path in daily.glob("*.md"):
        # daily/<YYYY-MM-DD>.md — stem is the date string; sorts lexicographically
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem):
            found.append((path.stem, path))
    found.sort(reverse=True)
    return [p for _date, p in found[:days]]


@dataclass
class CorpusBreakdown:
    """What landed in each tier — surfaced for logging + tests."""

    tier1_entity_page: Path | None
    tier1_authored: list[Path]
    tier1_recent: list[Path]
    tier1_digests: list[Path]
    tier2_sampled: list[Path]
    tier2_pool_size: int  # how many older-substrate files were available to sample from

    @property
    def all_paths(self) -> list[Path]:
        """Combined dedup'd path list, Tier-1 ordered first then Tier-2.

        Order within Tier 1 is determined per-section (digests then authored
        then recent), but the entity page is excluded from the corpus paths
        (it's rendered as `current_page` in the prompt, not the corpus block).
        """
        seen: set[Path] = set()
        out: list[Path] = []
        for group in (
            self.tier1_authored,
            self.tier1_recent,
            self.tier1_digests,
            self.tier2_sampled,
        ):
            for p in group:
                rp = p.resolve()
                if rp in seen:
                    continue
                seen.add(rp)
                out.append(p)
        return out

    @property
    def tier1_count(self) -> int:
        seen: set[Path] = set()
        for group in (self.tier1_authored, self.tier1_recent, self.tier1_digests):
            for p in group:
                seen.add(p.resolve())
        return len(seen)

    @property
    def tier2_count(self) -> int:
        return len(self.tier2_sampled)


def collect_corpus_tiered(
    entity: EntityRef,
    *,
    vault_root: Path | None = None,
    tier1_recent_count: int | None = None,
    tier1_digest_days: int | None = None,
    tier2_sample_count: int | None = None,
    rng_seed: int | None = None,
) -> CorpusBreakdown:
    """4-tier corpus assembly (M016 sampled-activation).

    Bounded by construction: Tier 1 ≤ ~200 KB, Tier 2 ≤ ~400 KB.

    `rng_seed` is for test determinism. Production callers omit it; the
    score noise term uses the module-default Random instance.
    """
    root = vault_root or ROOT_DIR
    recent_n = (
        tier1_recent_count
        if tier1_recent_count is not None
        else CONFIG.limits.dream_tier1_recent_count
    )
    digest_days = (
        tier1_digest_days
        if tier1_digest_days is not None
        else CONFIG.limits.dream_tier1_digest_days
    )
    sample_k = (
        tier2_sample_count
        if tier2_sample_count is not None
        else CONFIG.limits.dream_tier2_sample_count
    )
    rng = random.Random(rng_seed) if rng_seed is not None else random.Random()

    # One filesystem walk; classify the hits.
    all_hits = _scan_mentioning_files(entity, vault_root=root, include_authored=True)

    # Partition: operator-authored knowledge vs regular substrate.
    authored: list[Path] = []
    substrate: list[tuple[float, Path]] = []
    for mtime, path in all_hits:
        if _is_operator_authored_for(path, entity, vault_root=root):
            authored.append(path)
        else:
            # Only count files that are substrate (raw/ or daily/) for the
            # recent/sampled buckets; knowledge/ matches without author=slug
            # are dropped (they're compile outputs — risk of amplification loop).
            try:
                rel = str(path.relative_to(root))
            except ValueError:
                continue
            if rel.startswith("raw/") or rel.startswith("daily/"):
                substrate.append((mtime, path))

    # Tier 1 — recent substrate (most-recent N).
    substrate_paths_newest_first = [p for _ts, p in substrate]
    tier1_recent = substrate_paths_newest_first[:recent_n]
    tier1_recent_set = {p.resolve() for p in tier1_recent}

    # Tier 1 — daily digests (last M days; pulled by date-on-name regardless
    # of whether the digest mentions the slug — digests are compressed
    # cross-substrate signal worth always-including in their own right).
    tier1_digests = _recent_daily_digest_paths(root, days=digest_days)
    tier1_digests_set = {p.resolve() for p in tier1_digests}

    # Tier 1 — operator-authored (always-include).
    authored_set = {p.resolve() for p in authored}

    # Tier 2 — sample from older substrate (substrate not already in Tier 1's
    # recent OR digest set, and not already in authored).
    tier1_all_set = tier1_recent_set | tier1_digests_set | authored_set
    older_pool = [p for _ts, p in substrate if p.resolve() not in tier1_all_set]
    if sample_k <= 0 or not older_pool:
        tier2_sampled: list[Path] = []
    else:
        scored: list[tuple[float, Path]] = [
            (_compute_sampling_score(p, vault_root=root, rng=rng), p) for p in older_pool
        ]
        scored.sort(key=lambda t: t[0], reverse=True)
        tier2_sampled = [p for _score, p in scored[:sample_k]]

    return CorpusBreakdown(
        tier1_entity_page=entity.page if entity.page.exists() else None,
        tier1_authored=authored,
        tier1_recent=tier1_recent,
        tier1_digests=tier1_digests,
        tier2_sampled=tier2_sampled,
        tier2_pool_size=len(older_pool),
    )


def render_corpus_block(
    paths: list[Path],
    *,
    vault_root: Path | None = None,
    max_chars_per_file: int = _PER_FILE_TRUNCATION_CHARS,
) -> str:
    """Render the corpus as a single markdown block for prompt embedding.

    Each file gets a `### path` header + a triple-fenced block of its
    content. Per-file truncation cap at `max_chars_per_file` to keep one
    pathological 500 KB substrate file from blowing the budget alone.
    """
    root = vault_root or ROOT_DIR
    chunks: list[str] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(path.relative_to(root))
        if len(text) > max_chars_per_file:
            text = (
                text[:max_chars_per_file]
                + f"\n\n[... truncated at {max_chars_per_file} chars ...]\n"
            )
        chunks.append(f"### `{rel}`\n\n```markdown\n{text}\n```\n")
    return "\n".join(chunks)


def render_corpus_block_tiered(
    breakdown: CorpusBreakdown,
    *,
    vault_root: Path | None = None,
    max_chars_per_file: int = _PER_FILE_TRUNCATION_CHARS,
) -> str:
    """Render the tiered corpus with section headers (Tier 1 / Tier 2 split).

    Surfacing the tier boundary to the LLM via prompt structure helps the
    reshape rule (Tier 3) — the model can weight Tier 1 (recent + digest +
    authored) higher than Tier 2 (sampled older substrate) when adjudicating
    conflicts.
    """
    root = vault_root or ROOT_DIR

    def _render_group(group_paths: list[Path], label: str) -> str:
        if not group_paths:
            return ""
        body = render_corpus_block(
            group_paths, vault_root=root, max_chars_per_file=max_chars_per_file
        )
        return f"\n## {label} ({len(group_paths)} files)\n\n{body}"

    # Dedup for display: a file in both authored and recent shows once under
    # authored (the more-specific role).
    seen: set[Path] = set()

    def _dedup(paths: list[Path]) -> list[Path]:
        out: list[Path] = []
        for p in paths:
            rp = p.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            out.append(p)
        return out

    parts: list[str] = []
    parts.append(
        _render_group(_dedup(breakdown.tier1_authored), "Tier 1 — operator-authored content")
    )
    parts.append(_render_group(_dedup(breakdown.tier1_digests), "Tier 1 — recent daily digests"))
    parts.append(
        _render_group(
            _dedup(breakdown.tier1_recent), "Tier 1 — most-recent substrate mentioning entity"
        )
    )
    parts.append(
        _render_group(_dedup(breakdown.tier2_sampled), "Tier 2 — weighted-sampled older substrate")
    )
    return "\n".join(p for p in parts if p)
