"""Pre-compile sweep of `<vault>/Clippings/` into `<vault>/raw/articles/`.

The Obsidian Web Clipper extension drops new clippings into the vault-root
`Clippings/` folder by default — and that folder is invisible to the engine's
source-glob (which scans `raw/**` and `daily/**`). This module moves clipped
articles into `raw/articles/` so the next compile picks them up.

Designed to be called once at the top of every `compile.py` run. Cheap when
`Clippings/` is empty or absent. Idempotent: never overwrites an existing
target file (collisions skip with a warning).

A one-shot hint is emitted on first non-empty sweep per vault, gated by a
marker file at `<.wiki>/state/clippings-hint-shown`. The hint tells the
operator they can reconfigure the Web Clipper extension to drop files
directly into `raw/articles/` and skip this sweep entirely.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from core.config import RAW_ARTICLES_DIR, ROOT_DIR, STATE_DIR

log = logging.getLogger(__name__)

CLIPPINGS_DIR = ROOT_DIR / "Clippings"
HINT_MARKER = STATE_DIR / "clippings-hint-shown"

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_filename(name: str) -> str:
    """Slug-safe filename: keep alnum, dot, underscore, hyphen; collapse the rest."""
    stem = Path(name).stem
    suffix = Path(name).suffix or ".md"
    safe_stem = _SAFE_NAME_RE.sub("-", stem).strip("-") or "clipping"
    return f"{safe_stem}{suffix}"


def _emit_hint() -> None:
    """One-shot per vault: tell the operator how to skip this sweep next time."""
    if HINT_MARKER.exists():
        return
    HINT_MARKER.parent.mkdir(parents=True, exist_ok=True)
    HINT_MARKER.write_text("shown\n", encoding="utf-8")
    log.info(
        "Tip: in the Obsidian Web Clipper browser extension, set the default "
        "folder to `raw/articles` directly — this sweep then becomes a no-op. "
        "Settings → General → Note location."
    )


def sweep() -> int:
    """Move every `Clippings/*.md` into `raw/articles/`. Returns the count moved.

    Skip+warn on filename collision (never overwrite). Files at sub-paths
    (`Clippings/<subdir>/*.md`) are NOT swept — the operator probably grouped
    those intentionally.
    """
    if not CLIPPINGS_DIR.is_dir():
        return 0

    candidates = sorted(p for p in CLIPPINGS_DIR.glob("*.md") if p.is_file())
    if not candidates:
        return 0

    RAW_ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    moved = 0
    for src in candidates:
        target_name = _sanitize_filename(src.name)
        dst = RAW_ARTICLES_DIR / target_name
        if dst.exists():
            log.warning(
                "Clippings sweep: target %s already exists; leaving %s in place. "
                "Resolve the collision manually.",
                dst.relative_to(ROOT_DIR),
                src.relative_to(ROOT_DIR),
            )
            continue
        src.rename(dst)
        log.info("Clippings sweep: %s → %s", src.relative_to(ROOT_DIR), dst.relative_to(ROOT_DIR))
        moved += 1

    if moved > 0:
        _emit_hint()

    return moved


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    n = sweep()
    if n == 0:
        print("clippings-sweep: nothing to move")
    else:
        print(f"clippings-sweep: moved {n} file(s) into raw/articles/")


if __name__ == "__main__":
    main()
