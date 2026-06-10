"""Body-blind folder-index walker (M027-S02-T01).

Pure walk logic over one `personal.watched_folders` entry (kind=local,
S01 shape `{id, kind, path, include?, exclude?}`). Builds the
minimum-viable digest: a depth-capped directory tree + a top-N
recent-changes list.

Hard invariants:

- **Body-blind:** the walker NEVER opens a file. `os.scandir` +
  `entry.stat(follow_symlinks=False)` only — no `open()`, no hashing,
  no content sniffing anywhere in this module.
- **No sanitization:** paths/names land in the model as-is (DECISIONS
  2026-06-07 — the human-approval walk is the content gate, not masking).
- **Symlinks are never followed** (no cycle risk, no escape from the
  root); they are recorded as plain entries with `is_dir=False`.
- **Deterministic:** per-directory entries sorted dirs-first then name,
  `recent` ties broken by rel_path — same fixture in, same model out
  (T02/T03 depend on this for delta hashing).
- **Fail-soft:** PermissionError/OSError on a dir listing or stat skips
  that entry and increments `counts["errors"]`; a nonexistent root
  raises ValueError (caller's config problem, loud).

Scope: walker + data model ONLY. Rendering/writing is T02, delta logic
T03, CLI/registry wiring (incl. lifting `max_depth`/`recent_n` to config
knobs + migration) is T04.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path


@dataclass
class IndexEntry:
    rel_path: str  # relative to root, as-is (NO sanitization)
    is_dir: bool
    size: int | None  # files only
    mtime: float
    ext: str  # lowercased suffix incl. dot, "" for dirs


@dataclass
class FolderIndex:
    root_id: str
    root_path: str
    tree: list[IndexEntry]  # depth-capped, dirs-first per level
    recent: list[IndexEntry]  # top-N files by mtime desc
    counts: dict[str, int]  # files/dirs/skipped_excluded/skipped_depth/errors
    generated_at: datetime


def _matches(rel_path: str, globs: list[str]) -> bool:
    return any(fnmatch(rel_path, g) for g in globs)


def walk_root(entry: dict, *, max_depth: int, recent_n: int) -> FolderIndex:
    """Walk one watched-folder entry body-blind and return its index.

    `include` globs filter files only (dirs are always traversed so
    nested matches are reachable); `exclude` wins over `include` and an
    excluded dir is not descended into. Depth counts root children as 1;
    a dir at depth == max_depth is enumerated but not descended
    (`counts["skipped_depth"]` per such dir).
    """
    root = Path(os.path.expanduser(str(entry.get("path") or "")))
    if not root.is_dir():
        raise ValueError(
            f"watched_folders entry {entry.get('id')!r}: "
            f"root path does not exist or is not a directory: {root}"
        )
    include = [str(g) for g in (entry.get("include") or [])]
    exclude = [str(g) for g in (entry.get("exclude") or [])]
    counts = {
        "files": 0,
        "dirs": 0,
        "skipped_excluded": 0,
        "skipped_depth": 0,
        "errors": 0,
    }
    tree: list[IndexEntry] = []
    files: list[IndexEntry] = []

    def _walk(dir_path: str, depth: int) -> None:
        try:
            with os.scandir(dir_path) as it:
                children = list(it)
        except OSError:
            counts["errors"] += 1
            return
        dirs: list[os.DirEntry] = []
        nondirs: list[os.DirEntry] = []
        for child in children:
            try:
                # follow_symlinks=False: a symlink (even to a dir) is a non-dir.
                (dirs if child.is_dir(follow_symlinks=False) else nondirs).append(
                    child
                )
            except OSError:
                counts["errors"] += 1
        dirs.sort(key=lambda c: c.name)
        nondirs.sort(key=lambda c: c.name)

        for child in dirs:
            rel = os.path.relpath(child.path, root)
            if _matches(rel, exclude):
                counts["skipped_excluded"] += 1
                continue  # not descended either
            try:
                st = child.stat(follow_symlinks=False)
            except OSError:
                counts["errors"] += 1
                continue
            tree.append(
                IndexEntry(
                    rel_path=rel, is_dir=True, size=None, mtime=st.st_mtime, ext=""
                )
            )
            counts["dirs"] += 1
            if depth + 1 >= max_depth:
                counts["skipped_depth"] += 1
            else:
                _walk(child.path, depth + 1)

        for child in nondirs:
            rel = os.path.relpath(child.path, root)
            if _matches(rel, exclude):
                counts["skipped_excluded"] += 1
                continue
            if include and not _matches(rel, include):
                continue
            try:
                st = child.stat(follow_symlinks=False)
            except OSError:
                counts["errors"] += 1
                continue
            ie = IndexEntry(
                rel_path=rel,
                is_dir=False,
                size=st.st_size,
                mtime=st.st_mtime,
                ext=os.path.splitext(child.name)[1].lower(),
            )
            tree.append(ie)
            files.append(ie)
            counts["files"] += 1

    _walk(str(root), depth=0)
    recent = sorted(files, key=lambda e: (-e.mtime, e.rel_path))[:recent_n]
    return FolderIndex(
        root_id=str(entry.get("id") or ""),
        root_path=str(root),
        tree=tree,
        recent=recent,
        counts=counts,
        generated_at=datetime.now(timezone.utc),
    )
