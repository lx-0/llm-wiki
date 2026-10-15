"""The engine's one backup helper: a copy before a write, named to the second and never over
an earlier one.

Two backups within one second shared a name, and the second replaced the first, which was
the pre-change original. Recording the bash hooks oracle found it (M034-S03-T02), and five
Python writers had it too: a batch of Thunderbird filter rules or All-Inkl procmail recipes
writes the same file within milliseconds. A clash takes -2, -3, …, as
`lib/common.sh:backup_file` does.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def stamp() -> str:
    """The compact local timestamp in backup names: ``YYYYmmdd-HHMMSS``."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def backup_path(directory: Path, stem: str, ext: str = "") -> Path:
    """``<directory>/<stem><stamp><ext>``, or with -2, -3, … before ``ext`` while that name
    is taken."""
    base = f"{stem}{stamp()}"
    target = directory / f"{base}{ext}"
    n = 1
    while target.exists():
        n += 1
        target = directory / f"{base}-{n}{ext}"
    return target


def backup(path: Path) -> Path | None:
    """A sibling copy ``<name>.bak.<stamp>[-n]`` with the file's metadata; ``None`` when
    ``path`` is missing."""
    if not path.exists():
        return None
    target = backup_path(path.parent, f"{path.name}.bak.")
    shutil.copy2(path, target)
    return target
