"""compile_role frontmatter axis (M007-S01).

Defines how `compile.py` treats a vault page:

- `source-only`     — substrate; distill into knowledge/ (today's default behavior)
- `source-and-final`— the page IS the final form; index for backlinks + knowledge/index.md,
                      but do NOT produce a separate knowledge/concepts/<title>.md
- `final-only`      — engine-skip; hand-curated; reachable via grep/graph/search but
                      hidden from MOC auto-includes and dashboard active surfaces

Default-by-location inference applies when frontmatter omits `compile_role:`.
Explicit override in frontmatter always wins.

Pure module — no global config dependency. Callers (T02 wires CONFIG knob in).
"""

from pathlib import Path
from typing import Literal

CompileRole = Literal["source-only", "source-and-final", "final-only"]

VALID_ROLES: frozenset[str] = frozenset({"source-only", "source-and-final", "final-only"})

# Location-class → inferred role when frontmatter omits compile_role.
# knowledge/ pages default to source-only because they're compile OUTPUT; a re-run
# distills (effectively a no-op when up-to-date). Operator marks them final-only
# explicitly in frontmatter to archive a page from active surfaces.
LOCATION_DEFAULTS: dict[str, CompileRole] = {
    "raw": "source-only",
    "daily": "source-only",
    "inbox": "source-only",
    "knowledge": "source-only",
}


def infer_compile_role(
    path: Path,
    frontmatter: dict,
    *,
    default_by_location: bool = True,
    vault_root: Path | None = None,
) -> CompileRole:
    """Return the compile_role for a vault page.

    Args:
        path: Path to the page. May be absolute or relative; if `vault_root` is given,
              `path` is made relative to it before location-class lookup.
        frontmatter: Parsed YAML frontmatter dict.
        default_by_location: If True, fall back to LOCATION_DEFAULTS when the file omits
                             `compile_role:`. If False, fall back to "source-only".
        vault_root: Optional vault root for making `path` relative.

    Raises:
        ValueError: when frontmatter contains an invalid `compile_role` value.
    """
    explicit = frontmatter.get("compile_role")
    if explicit is not None:
        if explicit not in VALID_ROLES:
            raise ValueError(f"invalid compile_role: {explicit!r}")
        return explicit  # type: ignore[return-value]

    if not default_by_location:
        return "source-only"

    location_class = _location_class(path, vault_root)
    return LOCATION_DEFAULTS.get(location_class, "source-only")


def _location_class(path: Path, vault_root: Path | None) -> str:
    """Return the first known top-level segment (raw/daily/knowledge/inbox), or ''."""
    if vault_root is not None:
        try:
            parts = path.relative_to(vault_root).parts
        except ValueError:
            parts = path.parts
    else:
        parts = path.parts
    for part in parts:
        if part in LOCATION_DEFAULTS:
            return part
    return ""
