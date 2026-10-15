"""Round-robin config.yaml backup — the ONE helper both write paths share.

`core.config._set_in_yaml` (engine writes via `wiki config set`) and
`migrations.migrate_config_keys` (schema migration on `wiki update`) snapshot
the operator's config to the same place with the same naming and keep-count:
`<.wiki>/state/config-backups/config-<UTC YYYYmmdd-HHMMSS-ffffff>.yaml`, last N retained.
The name is fixed-width because the prune goes by name: name order has to be time order.

Side-effect-free at import (pathlib/datetime/shutil only) so the migration —
which must NOT import `core.config` (that module runs `load()` against the
global CONFIG_FILE at import) — can share it instead of carrying its own copy.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

BACKUP_DIR_NAME = "config-backups"
BACKUP_KEEP_LAST = 10


def backup_dir_for(config_path: Path) -> Path:
    """Where round-robin backups live for a given config file: `<.wiki>/state/config-backups/`."""
    return config_path.parent / "state" / BACKUP_DIR_NAME


def backup_config_file(config_path: Path, *, keep_last: int = BACKUP_KEEP_LAST) -> Path | None:
    """Snapshot `config_path` to a timestamped file, pruning beyond `keep_last`.

    Returns the backup path on success, None when there is nothing to back up
    or the snapshot failed. Failures never raise — losing a backup is better
    than blocking the config write that follows.
    """
    if not config_path.exists():
        return None
    try:
        bdir = backup_dir_for(config_path)
        bdir.mkdir(parents=True, exist_ok=True)
        # Microseconds always, fixed width: a suffix added only on a same-second clash made
        # `config-T-<µs>.yaml` sort before `config-T.yaml`, and the prune below dropped
        # the newer snapshots.
        stamp = datetime.now(UTC)
        out = bdir / f"config-{stamp:%Y%m%d-%H%M%S-%f}.yaml"
        while out.exists():  # the same microsecond: next one, still in order
            stamp += timedelta(microseconds=1)
            out = bdir / f"config-{stamp:%Y%m%d-%H%M%S-%f}.yaml"
        out.write_bytes(config_path.read_bytes())

        # Prune oldest beyond keep-count.
        existing = sorted(bdir.glob("config-*.yaml"))
        if len(existing) > keep_last:
            for stale in existing[:-keep_last]:
                with contextlib.suppress(OSError):
                    stale.unlink()
        return out
    except OSError:
        return None
