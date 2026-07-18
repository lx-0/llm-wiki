"""Substrate-scope resolution — the privacy boundary of the reports feature.

This module owns *which* of the operator's substrate an inference agent is
allowed to read. It is the seam behind the whole reports subsystem's
privacy story: the clinical-screen glob set + the mtime-window walk that
turns a vault root into a concrete file list.

Both adapters of that seam import from here:

  - production: `runner.py` resolves the substrate set it lists in the
    inference prompt, and records the glob set in report frontmatter.
  - probe: `audit_scope.py` walks the same set to token-budget it.

The probe imports production, never the reverse — the contract lives in
one owning, greppable module, so a `git grep resolve_substrate_files`
finds the privacy boundary instead of turning up a one-shot audit script.
Per-instrument `scope:` blocks (a wider substrate set for personality
instruments) are the post-wedge extension point; the clinical default
below is what the wedge ships.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path


# Default substrate subset for clinical-screen instruments. Scoped to the
# substrates that legitimately surface clinical-screen signals (sleep /
# mood / engagement / concentration). Wider per-instrument scopes will be
# declared in items.yaml `scope:` blocks post-wedge.
CLINICAL_DEFAULT_SUBSTRATE_GLOBS: tuple[str, ...] = (
    "daily/*.md",
    "raw/notes/voice/**/*.md",
    "raw/notes/health/**/*.md",
    "raw/transcripts/**/*.md",
    "raw/notes/sessions/**/*.md",
)


def resolve_substrate_files(
    vault_root: Path,
    globs: tuple[str, ...],
    lookback_days: int,
) -> list[Path]:
    """Return files matching any glob whose mtime falls in the window.

    The lookback window is `lookback_days` ending now; a file matching
    multiple globs is de-duplicated. This is the single definition of
    "which files an inference run may read" — both the production runner
    and the audit probe call it.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    cutoff_epoch = cutoff.timestamp()
    found: dict[Path, float] = {}
    for pattern in globs:
        for path in vault_root.glob(pattern):
            if not path.is_file():
                continue
            mtime = path.stat().st_mtime
            if mtime < cutoff_epoch:
                continue
            # Dedup if the file matches multiple globs.
            found[path] = mtime
    return sorted(found.keys())
