"""Dream-cycle: periodic cross-time re-synthesis of entity pages (M014 MVP).

Where `compile.py` is per-file distillation (one substrate file → one or more
knowledge/ updates), dream-cycle is cross-time synthesis: it picks ONE entity
(person / project / area), greps all substrate mentioning that entity (or
naming it as `author:`), and rewrites the entity's State block + appends to
Timeline from the full corpus.

The cross-time view surfaces recurring themes, drifting roles, and emerging
concept-clusters that per-file compile cannot see (each compile pass sees ONE
file + index.md).

CLI surface:

    wiki dream-entity <slug>            # re-synthesize one entity
    wiki dream --all-entities           # sweep everyone, respecting cooldown
    wiki dream-entity <slug> --dry-run  # print corpus + estimated cost, no SDK call

Piggyback wiring: see `flush.py:_LEGACY_PIGGYBACK_COMMANDS["dream_cycle"]`.
The piggyback shells out to `dream.py --piggyback`, which sweeps the N
most-overdue entities under the per-run cost cap.

Cost gates (real, hard, no silent skips):

  - Per-entity cap: `CONFIG.limits.dream_entity_max_cost_usd`. Pre-flight
    estimate from prompt-char count; reject if estimate > cap.
  - Per-run cap (piggyback / --all): `CONFIG.limits.dream_cycle_max_cost_per_run_usd`.
    Stop sweeping once cumulative cost crosses the cap.

Cooldown: `CONFIG.scheduling.dream_cooldown_days` (default 7). Entities with
`last_synthesized_at:` newer than that are skipped.

Provider: Claude Agent SDK only — never Ollama. (See feedback memory
`feedback_no_silent_provider_fallback`.)
"""

from __future__ import annotations

import json

import os

os.environ.setdefault("CLAUDE_INVOKED_BY", "dream")

import argparse
import asyncio
import logging
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    query,
)

from core.config import CONFIG
from core.paths import (
    AREAS_DIR,
    INDEX_FILE,
    KNOWLEDGE_DIR,
    LOG_FILE,
    PEOPLE_DIR,
    PROJECTS_DIR,
    RAW_DIR,
    ROOT_DIR,
    STATE_DIR,
    DAILY_DIR,
)
from core.prompts import render
from core.sdk_helpers import (
    StderrCapture,
    log_sdk_failure,
    make_path_scope_gate,
    prompt_stream,
)
from core.utils import now_iso, today_iso


from core.console import setup_console_logging  # noqa: E402
log = setup_console_logging("dream")


# ── Constants ─────────────────────────────────────────────────────────

# Rough Opus pricing: input $15/Mtok, output $75/Mtok (Opus 4.7 published rates).
# Dream-cycle prompts are input-dominated (large corpus, small output).
# Estimate: input_chars / 4 chars/token × $15/Mtok + small fixed output budget.
# Conservative — actual cost can be 1.5-2× higher with tool-turn fan-out.
_INPUT_USD_PER_MTOK = 15.0
_OUTPUT_USD_PER_MTOK = 75.0
_OUTPUT_BUDGET_TOKENS = 6000  # generous ceiling for a State+Timeline rewrite
_CHARS_PER_TOKEN = 4.0  # English/German mix; conservative

# Map entity-kind (the folder slug) to the kind's directory + type-frontmatter
# value. Areas use the M005 areas-bucket folder (knowledge/areas/) and a
# flatter shape — dream-cycle still works because the prompt explicitly
# handles that case (no Action Items section).
_ENTITY_KINDS: dict[str, tuple[Path, str]] = {
    "people": (PEOPLE_DIR, "person"),
    "projects": (PROJECTS_DIR, "project"),
    "areas": (AREAS_DIR, "area"),
}


# ── Helpers ────────────────────────────────────────────────────────────


@dataclass
class EntityRef:
    slug: str
    kind: str  # "people" | "projects" | "areas"
    page: Path  # absolute
    type_value: str  # "person" | "project" | "area"

    @property
    def title(self) -> str:
        return self.slug.replace("-", " ").title()

    @property
    def link(self) -> str:
        return f"knowledge/{self.kind}/{self.slug}"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a markdown file into (frontmatter dict, body). Tolerant."""
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
    if not isinstance(fm, dict):
        fm = {}
    return fm, body


def _resolve_entity(slug: str) -> EntityRef | None:
    """Find the entity page under knowledge/{people,projects,areas}/<slug>.md."""
    for kind, (dir_, type_value) in _ENTITY_KINDS.items():
        page = dir_ / f"{slug}.md"
        if page.exists():
            return EntityRef(slug=slug, kind=kind, page=page, type_value=type_value)
    return None


def _list_all_entities() -> list[EntityRef]:
    """Walk knowledge/{people,projects,areas}/ for every entity page."""
    out: list[EntityRef] = []
    for kind, (dir_, type_value) in _ENTITY_KINDS.items():
        if not dir_.exists():
            continue
        for page in sorted(dir_.glob("*.md")):
            slug = page.stem
            out.append(
                EntityRef(slug=slug, kind=kind, page=page, type_value=type_value)
            )
    return out


# ── Cooldown ──────────────────────────────────────────────────────────


def _parse_iso_date(value: object) -> datetime | None:
    """Best-effort ISO date parse. Accepts date, datetime, or ISO string."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        # datetime.date — promote to UTC midnight
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
        except ValueError:
            return None
    return None


def _last_synth_age_days(entity: EntityRef, *, now: datetime | None = None) -> float | None:
    """Return age in days since last synthesis, or None if never synthesized."""
    if not entity.page.exists():
        return None
    fm, _body = _parse_frontmatter(entity.page.read_text(encoding="utf-8"))
    when = _parse_iso_date(fm.get("last_synthesized_at"))
    if when is None:
        return None
    ref = now or datetime.now(timezone.utc)
    return max(0.0, (ref - when).total_seconds() / 86400.0)


def is_within_cooldown(entity: EntityRef, *, cooldown_days: int | None = None) -> bool:
    """True iff the entity was synthesized within the cooldown window."""
    days = cooldown_days if cooldown_days is not None else CONFIG.scheduling.dream_cooldown_days
    if days <= 0:
        return False
    age = _last_synth_age_days(entity)
    return age is not None and age < days


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


_SUBSTRATE_ROOTS: tuple[Path, ...] = (RAW_DIR, DAILY_DIR)

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
    ("raw/memories/",                3.0),
    ("raw/transcripts/jamie/",       2.0),
    ("raw/transcripts/gmeet/",       2.0),
    ("raw/notes/longform/",          1.5),
    ("raw/notes/email/",             1.0),
    ("raw/notes/calendar/",          1.0),
    ("raw/notes/screenshots/",       0.8),
)

# Sentinel for "this file has never been dreamed" — large enough that any
# never-stamped file beats any stamped one on the dreams_since_last_seen term.
_NEVER_DREAMED_DAYS = 1_000_000.0

# Tier-1 / Tier-2 per-file truncation cap. Big enough to carry the load-bearing
# content of typical substrate (meeting transcripts run 5-15 KB; longform
# articles 10-30 KB) without letting one pathological 500 KB file dominate
# the budget alone.
_PER_FILE_TRUNCATION_CHARS = 8_000


def _is_substrate_file(path: Path) -> bool:
    if path.suffix.lower() != ".md":
        return False
    rel = path.resolve()
    for root in _SUBSTRATE_ROOTS:
        try:
            rel.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


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
# raw/ stays byte-identical (raw-is-immutable rule).
_DREAM_ACTIVATION_FILE = STATE_DIR / "dream-activation.json"


def _load_dream_activation() -> dict[str, str]:
    try:
        return json.loads(_DREAM_ACTIVATION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_dream_activation(data: dict[str, str]) -> None:
    """Atomic-replace write so a crash mid-write can't corrupt the file."""
    _DREAM_ACTIVATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _DREAM_ACTIVATION_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    tmp.replace(_DREAM_ACTIVATION_FILE)


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
    fm, _body = _parse_frontmatter(text)
    return _parse_iso_date(fm.get("last_dreamed_at"))


def _dreams_since_last_seen_days(path: Path, *, now: datetime | None = None) -> float:
    """Return days since the file's last_dreamed_at, or sentinel if never."""
    stamp = _get_last_dreamed_at(path)
    if stamp is None:
        return _NEVER_DREAMED_DAYS
    ref = now or datetime.now(timezone.utc)
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


def _write_last_dreamed_at(path: Path, when: datetime | None = None) -> bool:
    """Record `last_dreamed_at` for a substrate file in the side-state
    file (`state/dream-activation.json`). NEVER touches the substrate
    file itself — raw/ is immutable (engine reads, never writes).

    Returns True if the side-state was updated. Idempotent — same-day
    stamp is a no-op (avoids churning the JSON on every dream of every
    entity). Tolerant — write failure logs and returns False so a single
    problematic file doesn't abort the rest of a dream.
    """
    stamp = (when or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    try:
        rel = str(path.relative_to(ROOT_DIR))
    except ValueError:
        rel = str(path)
    try:
        activation = _load_dream_activation()
        existing = activation.get(rel)
        if isinstance(existing, str) and existing.startswith(stamp):
            return False  # already stamped today
        activation[rel] = stamp
        _save_dream_activation(activation)
        return True
    except OSError as exc:
        log.warning("  could not stamp last_dreamed_at for %s: %s", rel, exc)
        return False


# ── Tiered corpus collection ────────────────────────────────────────


def _scan_mentioning_files(
    entity: EntityRef, *, vault_root: Path, include_authored: bool = True,
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
    fm, _body = _parse_frontmatter(text)
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
        for group in (self.tier1_authored, self.tier1_recent, self.tier1_digests, self.tier2_sampled):
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
    recent_n = tier1_recent_count if tier1_recent_count is not None else CONFIG.limits.dream_tier1_recent_count
    digest_days = tier1_digest_days if tier1_digest_days is not None else CONFIG.limits.dream_tier1_digest_days
    sample_k = tier2_sample_count if tier2_sample_count is not None else CONFIG.limits.dream_tier2_sample_count
    rng = random.Random(rng_seed) if rng_seed is not None else random.Random()

    # One filesystem walk; classify the hits.
    all_hits = _scan_mentioning_files(entity, vault_root=root, include_authored=True)
    all_paths = [p for _ts, p in all_hits]

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


def collect_corpus(entity: EntityRef, *, vault_root: Path | None = None) -> list[Path]:
    """Back-compat shim — returns the deduped path list from the tiered build.

    Kept so existing tests / callers (M014) that grab `collect_corpus()` and
    inspect the result list continue to work. New code should call
    `collect_corpus_tiered()` directly to get the tier breakdown.
    """
    return collect_corpus_tiered(entity, vault_root=vault_root).all_paths


def render_corpus_block(
    paths: list[Path], *, vault_root: Path | None = None, max_chars_per_file: int = _PER_FILE_TRUNCATION_CHARS
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
            text = text[:max_chars_per_file] + f"\n\n[... truncated at {max_chars_per_file} chars ...]\n"
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
        body = render_corpus_block(group_paths, vault_root=root, max_chars_per_file=max_chars_per_file)
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
    parts.append(_render_group(_dedup(breakdown.tier1_authored), "Tier 1 — operator-authored content"))
    parts.append(_render_group(_dedup(breakdown.tier1_digests), "Tier 1 — recent daily digests"))
    parts.append(_render_group(_dedup(breakdown.tier1_recent), "Tier 1 — most-recent substrate mentioning entity"))
    parts.append(_render_group(_dedup(breakdown.tier2_sampled), "Tier 2 — weighted-sampled older substrate"))
    return "\n".join(p for p in parts if p)


# ── Cost estimation ─────────────────────────────────────────────────


def estimate_cost_usd(prompt_chars: int) -> float:
    """Rough pre-flight cost estimate from prompt size + fixed output budget.

    Conservative — actual cost can run 1.5-2× higher when tool-turn fan-out
    re-reads articles. The estimate gates the SDK call BEFORE spend; the
    real cost is measured via ResultMessage.total_cost_usd after.
    """
    input_tokens = prompt_chars / _CHARS_PER_TOKEN
    input_cost = input_tokens * _INPUT_USD_PER_MTOK / 1_000_000.0
    output_cost = _OUTPUT_BUDGET_TOKENS * _OUTPUT_USD_PER_MTOK / 1_000_000.0
    return round(input_cost + output_cost, 4)


# ── Main entity-pass ──────────────────────────────────────────────


@dataclass
class DreamResult:
    entity: EntityRef
    corpus_count: int
    corpus_chars: int
    estimated_cost_usd: float
    actual_cost_usd: float
    input_tokens: int
    output_tokens: int
    sdk_result_text: str
    skipped: str | None = None  # None = success
    elapsed_s: float = 0.0


def _read_facts_md() -> str:
    """Lazy import — pulls in the FACTS_DIR walker."""
    from core.utils import read_hard_facts

    return read_hard_facts()


def _build_owner_block() -> str:
    """Same owner-block rendering as compile.py."""
    from compile import _build_owner_block as _from_compile

    return _from_compile()


def _build_prompt(
    entity: EntityRef,
    corpus_paths: list[Path],
    *,
    max_turns: int,
    breakdown: CorpusBreakdown | None = None,
) -> tuple[str, int]:
    """Render dream_entity.md with the entity + corpus. Returns (prompt, total_chars).

    If `breakdown` is provided, the corpus is rendered with per-tier section
    headers so the LLM sees the Tier 1 / Tier 2 split (M016). Otherwise
    falls back to the flat M014-style render (used by legacy tests / paths).
    """
    current_page = entity.page.read_text(encoding="utf-8") if entity.page.exists() else "(file does not exist yet — create it from the two-layer template)"
    if breakdown is not None:
        corpus_block = render_corpus_block_tiered(breakdown)
    else:
        corpus_block = render_corpus_block(corpus_paths)
    corpus_chars = len(corpus_block)
    title = current_page_title(current_page) or entity.title
    prompt = render(
        "dream_entity",
        entity_slug=entity.slug,
        entity_title=title,
        entity_type=entity.type_value,
        entity_page=str(entity.page.relative_to(ROOT_DIR)),
        current_page=current_page,
        corpus_block=corpus_block,
        corpus_count=len(corpus_paths),
        corpus_chars=corpus_chars,
        owner_block=_build_owner_block(),
        facts_md=_read_facts_md(),
        max_turns=max_turns,
        today=today_iso(),
        now=now_iso(),
        entity_link=entity.link,
    )
    return prompt, len(prompt)


def current_page_title(page_text: str) -> str | None:
    fm, _body = _parse_frontmatter(page_text)
    val = fm.get("title")
    return str(val) if val else None


async def dream_entity(
    entity: EntityRef,
    *,
    dry_run: bool = False,
    cost_cap_usd: float | None = None,
    max_turns: int | None = None,
) -> DreamResult:
    """Re-synthesize ONE entity page from the substrate corpus.

    Cost gate: pre-flight estimate; on overrun returns a DreamResult with
    `skipped="cost_cap_exceeded"` and zero spend (the SDK is NEVER called
    when the cap fires — no silent burn).
    """
    started = time.time()
    cap = cost_cap_usd if cost_cap_usd is not None else CONFIG.limits.dream_entity_max_cost_usd
    turns = max_turns if max_turns is not None else 20

    # M016: tiered corpus. Bounded by construction at ~600 KB total
    # regardless of vault size (the M014 flat-collect path hit context
    # overflow on 475-file alex.md → 2.3 MB).
    breakdown = collect_corpus_tiered(entity)
    corpus_paths = breakdown.all_paths
    log.info(
        "  entity=%s kind=%s — corpus: T1=%d (auth=%d/recent=%d/digests=%d) "
        "T2=%d sampled of %d-file older pool",
        entity.slug, entity.kind,
        breakdown.tier1_count,
        len(breakdown.tier1_authored),
        len(breakdown.tier1_recent),
        len(breakdown.tier1_digests),
        breakdown.tier2_count,
        breakdown.tier2_pool_size,
    )

    if not corpus_paths:
        log.warning(
            "  no substrate mentions %s — nothing to synthesize (skipping)",
            entity.slug,
        )
        return DreamResult(
            entity=entity, corpus_count=0, corpus_chars=0,
            estimated_cost_usd=0.0, actual_cost_usd=0.0,
            input_tokens=0, output_tokens=0, sdk_result_text="",
            skipped="no_substrate", elapsed_s=time.time() - started,
        )

    prompt, prompt_chars = _build_prompt(entity, corpus_paths, max_turns=turns, breakdown=breakdown)
    estimate = estimate_cost_usd(prompt_chars)
    log.info(
        "  prompt: %d chars (%.1f KB) — estimated cost $%.3f (cap $%.2f)",
        prompt_chars, prompt_chars / 1024, estimate, cap,
    )

    if cap > 0 and estimate > cap:
        msg = (
            f"COST_CAP_EXCEEDED: entity={entity.slug} estimate=${estimate:.3f} "
            f"> cap=${cap:.2f} (prompt={prompt_chars} chars, corpus={len(corpus_paths)} files). "
            "Reduce corpus by archiving old substrate, raise CONFIG.limits.dream_entity_max_cost_usd, "
            "or run with --no-cost-cap (not yet implemented — file the request)."
        )
        log.error("  %s", msg)
        return DreamResult(
            entity=entity, corpus_count=len(corpus_paths),
            corpus_chars=sum(len(p.read_text(encoding="utf-8", errors="replace")) for p in corpus_paths),
            estimated_cost_usd=estimate, actual_cost_usd=0.0,
            input_tokens=0, output_tokens=0, sdk_result_text=msg,
            skipped="cost_cap_exceeded", elapsed_s=time.time() - started,
        )

    if dry_run:
        log.info("  --dry-run: would invoke SDK with %d-char prompt", prompt_chars)
        return DreamResult(
            entity=entity, corpus_count=len(corpus_paths),
            corpus_chars=prompt_chars, estimated_cost_usd=estimate,
            actual_cost_usd=0.0, input_tokens=0, output_tokens=0,
            sdk_result_text="(dry-run)", skipped="dry_run",
            elapsed_s=time.time() - started,
        )

    # Real SDK call. Single attempt — dream is a periodic pass; if it fails,
    # the next pass picks the entity up again.
    model = CONFIG.models.compile_model
    log.info("  invoking %s (max_turns=%d, system=dream_entity_system)", model, turns)

    input_tokens = 0
    output_tokens = 0
    result_text = ""
    actual_cost = 0.0
    capture = StderrCapture()

    # Path-scope: see compile.py for the full design comment. Same shape
    # here — flag-branched to keep the rollback path one config flip away.
    common_options = dict(
        max_buffer_size=CONFIG.limits.sdk_max_buffer_size_mb * 1024 * 1024,
        cwd=str(ROOT_DIR),
        model=model,
        max_turns=turns,
        system_prompt=render("dream_entity_system"),
        setting_sources=["project"],
        stderr=capture.callback,
    )
    if CONFIG.features.compile_callback_gate:
        agent_options = ClaudeAgentOptions(
            **common_options,
            allowed_tools=["Read", "Glob", "Grep"],
            can_use_tool=make_path_scope_gate([ROOT_DIR / "knowledge"]),
            permission_mode="default",
        )
        query_prompt = prompt_stream(prompt)
    else:
        agent_options = ClaudeAgentOptions(
            **common_options,
            allowed_tools=[
                "Read", "Glob", "Grep",
                "Write(knowledge/**)",
                "Edit(knowledge/**)",
            ],
            permission_mode="acceptEdits",
        )
        query_prompt = prompt

    try:
        async for message in query(prompt=query_prompt, options=agent_options):
            if isinstance(message, AssistantMessage) and message.usage:
                input_tokens += message.usage.get("input_tokens", 0)
                output_tokens += message.usage.get("output_tokens", 0)
            if isinstance(message, ResultMessage):
                result_text = message.result or ""
                actual_cost = float(getattr(message, "total_cost_usd", 0.0) or 0.0)
    except Exception as exc:  # noqa: BLE001 — classifier handles all paths
        log_sdk_failure(
            log,
            label=f"dream_entity:{entity.slug}",
            source=str(entity.page.relative_to(ROOT_DIR)),
            model=model,
            input_chars=prompt_chars,
            started=started,
            capture=capture,
            exc=exc,
        )
        return DreamResult(
            entity=entity, corpus_count=len(corpus_paths),
            corpus_chars=prompt_chars, estimated_cost_usd=estimate,
            actual_cost_usd=0.0, input_tokens=input_tokens, output_tokens=output_tokens,
            sdk_result_text=str(exc), skipped="sdk_failure",
            elapsed_s=time.time() - started,
        )

    elapsed = time.time() - started
    log.info(
        "  done: %d input + %d output tokens, actual cost $%.4f, elapsed %.1fs",
        input_tokens, output_tokens, actual_cost, elapsed,
    )

    # M016 — stamp last_dreamed_at on every substrate file that appeared in
    # this dream's corpus. This is the activation-tracking mechanism that
    # cycles files through Tier 2 sampling over time. Per-file write
    # failures log and continue — the entity-page Write is the deliverable.
    stamped = 0
    for path in corpus_paths:
        # Skip the entity page itself (its own last_synthesized_at is
        # written by the prompt's housekeeping rule). Skip daily/<date>.md
        # digests — they're not entity-specific substrate and would churn
        # mtime on every dream of every entity.
        if path.resolve() == entity.page.resolve():
            continue
        try:
            rel = str(path.relative_to(ROOT_DIR))
        except ValueError:
            continue
        if re.fullmatch(r"daily/\d{4}-\d{2}-\d{2}\.md", rel):
            continue
        if _write_last_dreamed_at(path):
            stamped += 1
    if stamped:
        log.info("  stamped last_dreamed_at on %d substrate file(s)", stamped)

    return DreamResult(
        entity=entity, corpus_count=len(corpus_paths),
        corpus_chars=prompt_chars, estimated_cost_usd=estimate,
        actual_cost_usd=actual_cost, input_tokens=input_tokens,
        output_tokens=output_tokens, sdk_result_text=result_text,
        skipped=None, elapsed_s=elapsed,
    )


# ── Sweep across entities ─────────────────────────────────────────


# ── M017 dream-priority resolution ──────────────────────────────────


from fnmatch import fnmatch as _fnmatch


def compute_entity_priority(entity: EntityRef) -> tuple[float, str]:
    """Resolve M017 weighted-priority for one entity. Returns (weight, source).

    Resolution order:
      1. entity frontmatter `dream_priority:` (absolute precedence — even 0)
      2. config `paths:` glob match (first-match wins via fnmatch)
      3. config formula: default × domain_mul × tag_mul × status_mul

    The `source` string describes which rule fired (for `--list-candidates`).
    """
    cfg = CONFIG.scheduling.dream_priority
    fm, _ = _parse_frontmatter(entity.page.read_text(encoding="utf-8"))

    # Layer 1 — per-entity frontmatter override (absolute)
    fm_priority = fm.get("dream_priority")
    if fm_priority is not None:
        try:
            return float(fm_priority), f"frontmatter:{fm_priority}"
        except (TypeError, ValueError):
            pass  # fall through to config rules

    # Layer 2 — explicit path/glob match (first wins)
    rel_path = str(entity.page.relative_to(ROOT_DIR))
    for pattern, weight in cfg.paths.items():
        if _fnmatch(rel_path, pattern):
            return float(weight), f"paths:{pattern}={weight}"

    # Layer 3 — multiplier formula
    base = float(cfg.default)
    breakdown = [f"default:{base}"]

    domain = fm.get("domain")
    if isinstance(domain, str) and domain in cfg.domain:
        m = float(cfg.domain[domain])
        base *= m
        breakdown.append(f"domain.{domain}:{m}")

    tags = fm.get("tags") or []
    if not isinstance(tags, list):
        tags = [tags]
    tag_matches = [(str(t), float(cfg.tags[str(t)])) for t in tags if str(t) in cfg.tags]
    if tag_matches:
        if cfg.tag_strategy == "sum":
            m = sum(w for _, w in tag_matches)
            base *= m
            breakdown.append(f"tags.sum:{m}")
        elif cfg.tag_strategy == "first":
            t, m = tag_matches[0]
            base *= m
            breakdown.append(f"tags.first.{t}:{m}")
        else:  # max (default)
            t, m = max(tag_matches, key=lambda x: x[1])
            base *= m
            breakdown.append(f"tags.max.{t}:{m}")

    status = fm.get("status")
    if isinstance(status, str) and status in cfg.status:
        m = float(cfg.status[status])
        base *= m
        breakdown.append(f"status.{status}:{m}")

    return base, " × ".join(breakdown)


def _select_for_sweep(
    candidates: list[tuple[float, EntityRef, str]],
    N: int,
    mode: str,
) -> list[tuple[float, EntityRef, str]]:
    """Pick N entities from weighted candidates. Mode = probabilistic | greedy.

    Filters out zero-weight entities (priority:0 means excluded).
    Probabilistic = weighted-random sample (diverse over time).
    Greedy = top-N by weight (deterministic).
    """
    eligible = [t for t in candidates if t[0] > 0]
    if not eligible:
        return []
    if mode == "greedy":
        return sorted(eligible, key=lambda t: t[0], reverse=True)[:N]
    # probabilistic (default): weighted-random-sample without replacement
    weights = [w for w, _, _ in eligible]
    picked: list[tuple[float, EntityRef, str]] = []
    pool = list(zip(weights, eligible))
    for _ in range(min(N, len(eligible))):
        if not pool:
            break
        total = sum(w for w, _ in pool)
        if total <= 0:
            break
        r = random.uniform(0, total)
        cum = 0.0
        for i, (w, item) in enumerate(pool):
            cum += w
            if r <= cum:
                picked.append(item)
                pool.pop(i)
                break
    return picked


def list_candidates(*, cooldown_days: int | None = None) -> list[dict]:
    """Return ranked candidate list for `wiki dream --list-candidates` UI."""
    cd = cooldown_days if cooldown_days is not None else CONFIG.scheduling.dream_cooldown_days
    rows: list[dict] = []
    for ent in _list_all_entities():
        priority, source = compute_entity_priority(ent)
        age_days = _last_synth_age_days(ent)
        cooldown = age_days is not None and age_days < cd
        weight = priority * (age_days if age_days is not None else 365.0)
        rows.append({
            "slug": ent.slug,
            "kind": ent.kind,
            "rel_path": str(ent.page.relative_to(ROOT_DIR)),
            "priority": round(priority, 3),
            "age_days": round(age_days, 1) if age_days is not None else None,
            "weight": round(weight, 2),
            "source": source,
            "cooldown_active": cooldown,
            "excluded": priority <= 0,
        })
    # Sort by priority (descending), then by weight (descending), then by slug.
    # Operator wants to see high-priority entities at top regardless of recent
    # synthesis — debug view of WHAT RULES FIRE, not WHAT GOT PICKED THIS RUN.
    # (Selection-this-run weight = priority × age × jitter, with cooldown
    # filter; that's `wiki dream piggyback --dry-run`, not list-candidates.)
    rows.sort(key=lambda r: (-r["priority"], -r["weight"], r["slug"]))
    return rows


async def dream_all_entities(
    *,
    cooldown_days: int | None = None,
    per_entity_cap: float | None = None,
    per_run_cap: float | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    selection_mode: str | None = None,
) -> list[DreamResult]:
    """Sweep all entities respecting caps + cooldown + M017 priority weighting.

    Selection mode (M017):
      - "probabilistic" (default): weighted-random by priority × age — diverse
      - "greedy": top-N by weight — deterministic, predictable
    """
    cd = cooldown_days if cooldown_days is not None else CONFIG.scheduling.dream_cooldown_days
    run_cap = per_run_cap if per_run_cap is not None else CONFIG.limits.dream_cycle_max_cost_per_run_usd
    mode = selection_mode or "probabilistic"

    all_entities = _list_all_entities()
    # Build (weight, entity, source) candidates: filter cooldown, compute weight via priority × age.
    candidates: list[tuple[float, EntityRef, str]] = []
    for ent in all_entities:
        if is_within_cooldown(ent, cooldown_days=cd):
            continue
        priority, source = compute_entity_priority(ent)
        age = _last_synth_age_days(ent)
        # Never-synthesized = high age signal (365d default cap so it doesn't dominate)
        age_for_weight = age if age is not None else 365.0
        weight = priority * age_for_weight * random.uniform(0.85, 1.15)
        candidates.append((weight, ent, source))

    # M017 selection
    N = limit if limit is not None else len(candidates)
    ranked = _select_for_sweep(candidates, N, mode)

    log.info(
        "Dream sweep: %d entities total, %d candidates after cooldown+priority filter, "
        "mode=%s, run_cap=$%.2f",
        len(all_entities), len(ranked), mode, run_cap,
    )

    results: list[DreamResult] = []
    cumulative = 0.0
    for idx, (_weight, ent, _source) in enumerate(ranked, 1):
        if limit is not None and idx > limit:
            log.info("Reached --limit=%d; stopping", limit)
            break
        if run_cap > 0 and cumulative >= run_cap:
            log.info(
                "Per-run cost cap reached ($%.2f >= $%.2f) — stopping after %d entities",
                cumulative, run_cap, idx - 1,
            )
            break
        log.info("[%d/%d] dream-entity %s", idx, len(ranked), ent.slug)
        res = await dream_entity(
            ent, dry_run=dry_run, cost_cap_usd=per_entity_cap,
        )
        results.append(res)
        cumulative += res.actual_cost_usd

    log.info(
        "Dream sweep finished: %d entities processed, cumulative cost $%.4f",
        len(results), cumulative,
    )
    return results


# ── CLI ───────────────────────────────────────────────────────────


async def _async_main() -> int:
    parser = argparse.ArgumentParser(description="Dream-cycle entity re-synthesis (M014)")
    sub = parser.add_subparsers(dest="cmd")

    p_one = sub.add_parser("entity", help="Re-synthesize one entity by slug")
    p_one.add_argument("slug", help="Entity slug (e.g. alex, emmett, yesterday-os)")
    p_one.add_argument("--dry-run", action="store_true", help="Print prompt + estimate, no SDK call")
    p_one.add_argument("--cost-cap", type=float, default=None, help="Override per-entity USD cap")
    p_one.add_argument("--max-turns", type=int, default=20, help="SDK max_turns budget")
    p_one.add_argument("--ignore-cooldown", action="store_true", help="Skip the last_synthesized_at gate")

    p_all = sub.add_parser("sweep", help="Sweep all entities (--all-entities)")
    p_all.add_argument("--dry-run", action="store_true")
    p_all.add_argument("--cooldown-days", type=int, default=None)
    p_all.add_argument("--per-entity-cap", type=float, default=None)
    p_all.add_argument("--per-run-cap", type=float, default=None)
    p_all.add_argument("--limit", type=int, default=None, help="Hard cap on entity count this run")
    p_all.add_argument(
        "--selection-mode",
        choices=["probabilistic", "greedy"],
        default=None,
        help="M017: probabilistic (weighted-random) | greedy (top-N by weight). "
             "Default reads from piggybacks.dream_cycle.selection_mode config.",
    )

    p_pb = sub.add_parser("piggyback", help="Piggyback wrapper — runs sweep with config defaults")
    p_pb.add_argument("--limit", type=int, default=None)

    p_lc = sub.add_parser("list-candidates",
        help="M017: show ranked candidate list with priority + age + source breakdown")
    p_lc.add_argument("--cooldown-days", type=int, default=None)
    p_lc.add_argument("--limit", type=int, default=30, help="Top N rows (default 30)")
    p_lc.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    args = parser.parse_args()

    if args.cmd == "entity":
        ent = _resolve_entity(args.slug)
        if ent is None:
            log.error(
                "No entity page found for slug %r under knowledge/{people,projects,areas}/. "
                "Check the slug or create the page first via per-file compile.",
                args.slug,
            )
            return 2
        if not args.ignore_cooldown and is_within_cooldown(ent):
            age = _last_synth_age_days(ent)
            cooldown = CONFIG.scheduling.dream_cooldown_days
            log.info(
                "Skipping %s: last_synthesized_at is %.1f days old < cooldown %dd. "
                "Re-run with --ignore-cooldown to force.",
                ent.slug, age or 0.0, cooldown,
            )
            return 0
        res = await dream_entity(
            ent, dry_run=args.dry_run, cost_cap_usd=args.cost_cap,
            max_turns=args.max_turns,
        )
        if res.skipped == "cost_cap_exceeded":
            return 3
        if res.skipped == "sdk_failure":
            return 4
        return 0

    if args.cmd == "sweep":
        results = await dream_all_entities(
            cooldown_days=args.cooldown_days,
            per_entity_cap=args.per_entity_cap,
            per_run_cap=args.per_run_cap,
            limit=args.limit,
            dry_run=args.dry_run,
            selection_mode=args.selection_mode,
        )
        # Non-zero exit if any entity hit a real failure (cost-cap or SDK)
        for r in results:
            if r.skipped in ("cost_cap_exceeded", "sdk_failure"):
                return 5
        return 0

    if args.cmd == "piggyback":
        # M017: piggyback uses probabilistic mode by default (diversity over
        # time, every eligible entity eventually selected, biased toward
        # high-weight). Operator can override per-invocation via `sweep
        # --selection-mode greedy`.
        results = await dream_all_entities(limit=args.limit, selection_mode="probabilistic")
        for r in results:
            if r.skipped == "sdk_failure":
                return 5
        return 0

    if args.cmd == "list-candidates":
        import json as _json
        rows = list_candidates(cooldown_days=args.cooldown_days)
        if args.json:
            print(_json.dumps(rows, indent=2))
            return 0
        # Pretty table
        print(f"{'Rank':<5} {'Weight':>8}  {'Prio':>6}  {'Age':>7}  {'Slug':<40} Source")
        print("-" * 110)
        for i, r in enumerate(rows[:args.limit], 1):
            age = f"{r['age_days']}d" if r['age_days'] is not None else "never"
            flag = " (cooldown)" if r["cooldown_active"] else (" EXCLUDED" if r["excluded"] else "")
            print(f"{i:<5} {r['weight']:>8.2f}  {r['priority']:>6.2f}  {age:>7}  {r['slug']:<40} {r['source']}{flag}")
        if len(rows) > args.limit:
            print(f"... and {len(rows) - args.limit} more (raise --limit to see)")
        return 0

    parser.print_help()
    return 1


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    sys.exit(main())
