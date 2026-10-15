"""Dream-cycle sweep priority (M017) — which entities a sweep picks, and why.

`compute_entity_priority` resolves one entity's weight (frontmatter → config paths
→ config formula); `build_sweep_candidates` computes every gate verdict once for both
consumers — the sweep in `dream.py` and `wiki dream list-candidates`;
`_select_for_sweep` picks N of them.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatch as _fnmatch

from core import frontmatter
from core.config import CONFIG
from core.paths import ROOT_DIR
from dream_corpus import is_within_insufficient_backoff
from dream_model import EntityRef, _last_synth_age_days, _list_all_entities

# ── M017 dream-priority resolution ──────────────────────────────────


def compute_entity_priority(entity: EntityRef) -> tuple[float, str]:
    """Resolve M017 weighted-priority for one entity. Returns (weight, source).

    Resolution order:
      1. entity frontmatter `dream_priority:` (absolute precedence — even 0)
      2. config `paths:` glob match (first-match wins via fnmatch)
      3. config formula: default × domain_mul × tag_mul × status_mul

    The `source` string describes which rule fired (for `--list-candidates`).
    """
    cfg = CONFIG.scheduling.dream_priority
    fm, _ = frontmatter.parse(entity.page.read_text(encoding="utf-8"))

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
    N: int,  # noqa: N803  N = the sample size, the docstring's notation
    mode: str,
    *,
    seed: int | None = None,
) -> list[tuple[float, EntityRef, str]]:
    """Pick N entities from weighted candidates. Mode = probabilistic | greedy.

    Filters out zero-weight entities (priority:0 means excluded).
    Probabilistic = weighted-random sample (diverse over time).
    Greedy = top-N by weight (deterministic).
    `seed` pins the RNG so probabilistic runs are reproducible for
    debugging "why was X picked over Y?" investigations.
    """
    _rng = random.Random(seed) if seed is not None else random
    eligible = [t for t in candidates if t[0] > 0]
    if not eligible:
        return []
    if mode == "greedy":
        return sorted(eligible, key=lambda t: t[0], reverse=True)[:N]
    # probabilistic (default): weighted-random-sample without replacement
    weights = [w for w, _, _ in eligible]
    picked: list[tuple[float, EntityRef, str]] = []
    pool = list(zip(weights, eligible, strict=False))
    for _ in range(min(N, len(eligible))):
        if not pool:
            break
        total = sum(w for w, _ in pool)
        if total <= 0:
            break
        r = _rng.uniform(0, total)
        cum = 0.0
        for i, (w, item) in enumerate(pool):
            cum += w
            if r <= cum:
                picked.append(item)
                pool.pop(i)
                break
    return picked


@dataclass
class SweepCandidate:
    """One entity with EVERY sweep-selection verdict computed once.

    The single source of truth both consumers read: ``dream_all_entities``
    filters on ``cooldown_active`` + ``backoff_active`` (and applies selection
    jitter to ``weight``), while ``list_candidates`` renders the full row —
    so the operator debug view surfaces the insufficient-corpus backoff state,
    not just cooldown. ``weight`` is the deterministic base (priority × age);
    the sweep multiplies in per-run jitter itself.
    """

    entity: EntityRef
    priority: float
    source: str
    age_days: float | None
    cooldown_active: bool
    backoff_active: bool
    excluded: bool  # priority <= 0 → never auto-swept
    weight: float


def build_sweep_candidates(
    *,
    cooldown_days: int | None = None,
    now: datetime | None = None,
) -> list[SweepCandidate]:
    """Every entity with every gate verdict resolved once. Neither filters nor
    ranks — the two consumers do (see SweepCandidate). Fixes the historical
    duplication where the sweep filtered insufficient-corpus backoff but
    list_candidates was blind to it."""
    cd = cooldown_days if cooldown_days is not None else CONFIG.scheduling.dream_cooldown_days
    ref = now or datetime.now(UTC)
    rows: list[SweepCandidate] = []
    for ent in _list_all_entities():
        priority, source = compute_entity_priority(ent)
        age = _last_synth_age_days(ent, now=ref)
        cooldown_active = cd > 0 and age is not None and age < cd
        backoff_active = is_within_insufficient_backoff(ent, now=ref)
        age_for_weight = age if age is not None else 365.0
        rows.append(
            SweepCandidate(
                entity=ent,
                priority=priority,
                source=source,
                age_days=age,
                cooldown_active=cooldown_active,
                backoff_active=backoff_active,
                excluded=priority <= 0,
                weight=priority * age_for_weight,
            )
        )
    return rows


def list_candidates(*, cooldown_days: int | None = None) -> list[dict]:
    """Return ranked candidate list for `wiki dream --list-candidates` UI.

    Consumes the shared build_sweep_candidates so every gate the sweep applies
    is surfaced here — including the insufficient-corpus backoff the debug view
    was previously blind to (it only flagged cooldown).
    """
    rows = [
        {
            "slug": c.entity.slug,
            "kind": c.entity.kind,
            "rel_path": str(c.entity.page.relative_to(ROOT_DIR)),
            "priority": round(c.priority, 3),
            "age_days": round(c.age_days, 1) if c.age_days is not None else None,
            "weight": round(c.weight, 2),
            "source": c.source,
            "cooldown_active": c.cooldown_active,
            "backoff_active": c.backoff_active,
            "excluded": c.excluded,
        }
        for c in build_sweep_candidates(cooldown_days=cooldown_days)
    ]
    # Sort by priority (descending), then by weight (descending), then by slug.
    # Operator wants to see high-priority entities at top regardless of recent
    # synthesis — debug view of WHAT RULES FIRE, not WHAT GOT PICKED THIS RUN.
    # (Selection-this-run weight = priority × age × jitter, with cooldown +
    # backoff filters; that's `wiki dream piggyback --dry-run`, not this view.)
    rows.sort(key=lambda r: (-r["priority"], -r["weight"], r["slug"]))
    return rows
