"""Dream-cycle entity model — which pages are dream entities, and when each was
last synthesized.

The base that `dream_corpus.py` (what one synthesis reads) and `dream_priority.py`
(which entities a sweep picks) share with `dream.py` (the cycle itself), so neither
of them imports `dream.py` — the module `wiki dream` runs as `__main__`. Tests patch
the dream modules' names through `tests/_dream_paths.py:patch_dream_path`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from core import frontmatter
from core.config import CONFIG
from core.paths import AREAS_DIR, PEOPLE_DIR, PROJECTS_DIR

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
            out.append(EntityRef(slug=slug, kind=kind, page=page, type_value=type_value))
    return out


# ── Cooldown ──────────────────────────────────────────────────────────


def _parse_iso_date(value: object) -> datetime | None:
    """Best-effort ISO date parse. Accepts date, datetime, or ISO string."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        # datetime.date — promote to UTC midnight
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None
    return None


def _last_synth_age_days(entity: EntityRef, *, now: datetime | None = None) -> float | None:
    """Return age in days since last synthesis, or None if never synthesized."""
    if not entity.page.exists():
        return None
    fm, _body = frontmatter.parse(entity.page.read_text(encoding="utf-8"))
    when = _parse_iso_date(fm.get("last_synthesized_at"))
    if when is None:
        return None
    ref = now or datetime.now(UTC)
    return max(0.0, (ref - when).total_seconds() / 86400.0)


def is_within_cooldown(entity: EntityRef, *, cooldown_days: int | None = None) -> bool:
    """True iff the entity was synthesized within the cooldown window."""
    days = cooldown_days if cooldown_days is not None else CONFIG.scheduling.dream_cooldown_days
    if days <= 0:
        return False
    age = _last_synth_age_days(entity)
    return age is not None and age < days
