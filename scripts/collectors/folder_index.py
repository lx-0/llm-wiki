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

Scope: walker + data model (T01) + digest render/write to
`raw/index/<root-id>.md` (T02). Delta logic is T03; CLI/registry wiring
(incl. lifting `max_depth`/`recent_n`/`max_tree_entries` to config knobs +
migration, and the `folder-index` compile-skip entry) is T03/T04.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path

if __package__ in (None, ""):  # direct execution via `wiki index`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.paths import RAW_DIR, STATE_DIR

log = logging.getLogger(__name__)

# One MD digest per watched root (single consumer: the S03 producer).
# Local convention, sibling of curiosity/backends/email.py's DEEP_SCAN_DIR.
INDEX_DIR = RAW_DIR / "index"

# Delta side-state: {root_id: {"signature": str, "last_indexed_at": iso}}.
STATE_FILE = STATE_DIR / "folder-index.json"


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


def _human_size(size: int | None) -> str:
    if size is None:
        return ""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{int(size)} B"  # pragma: no cover - unreachable


def _mtime_date(mtime: float) -> str:
    return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")


def render_index(index: FolderIndex, *, max_tree_entries: int) -> str:
    """Render one FolderIndex as the markdown digest the producer consumes.

    Pure function of the dataclass — same index in, byte-same markdown out
    (T03's delta-skip compares content; note `generated_at` varies per walk,
    so T03 must hash modulo frontmatter or reuse walk-level signals).
    Names land verbatim — unmasked per DECISIONS 2026-06-07.
    """
    truncated = len(index.tree) > max_tree_entries
    lines: list[str] = []
    lines.append("---")
    lines.append("type: folder-index")
    lines.append(f"root_id: {index.root_id}")
    lines.append(f"root_path: {json.dumps(index.root_path, ensure_ascii=False)}")
    lines.append(f'generated_at: "{index.generated_at.isoformat()}"')
    for key in ("files", "dirs", "skipped_excluded", "skipped_depth", "errors"):
        lines.append(f"{key}: {index.counts.get(key, 0)}")
    lines.append(f"truncated: {'true' if truncated else 'false'}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Folder index — {index.root_id}")
    lines.append("")
    lines.append(
        f"**Root:** `{index.root_path}` · {index.counts.get('files', 0)} files · "
        f"{index.counts.get('dirs', 0)} dirs · {index.counts.get('errors', 0)} errors"
    )
    lines.append("")
    lines.append("## Recent changes")
    lines.append("")
    if index.recent:
        for e in index.recent:
            lines.append(
                f"- `{e.rel_path}` — {_mtime_date(e.mtime)} · {_human_size(e.size)}"
            )
    else:
        lines.append("_No files._")
    lines.append("")
    lines.append("## Tree")
    lines.append("")
    for e in index.tree[:max_tree_entries]:
        depth = e.rel_path.count(os.sep)
        name = os.path.basename(e.rel_path)
        suffix = "/" if e.is_dir else f" · {_human_size(e.size)}"
        lines.append(f"{'  ' * depth}- `{name}`{suffix}")
    if truncated:
        omitted = len(index.tree) - max_tree_entries
        lines.append("")
        lines.append(f"_… {omitted} more entries omitted (size cap)_")
    return "\n".join(lines) + "\n"


def write_index(index: FolderIndex, *, max_tree_entries: int) -> Path:
    """Render and write the digest to `raw/index/<root-id>.md` (overwrite)."""
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    path = INDEX_DIR / f"{index.root_id}.md"
    path.write_text(render_index(index, max_tree_entries=max_tree_entries),
                    encoding="utf-8")
    return path


@dataclass
class SyncResult:
    written: bool
    path: Path | None
    reason: str | None
    signature: str


def index_signature(index: FolderIndex) -> str:
    """Content signature of the walked tree — mtime/size/structure only.

    Deliberately EXCLUDES generated_at and counts (T02 carry: the digest
    frontmatter varies per walk; the delta must not). Same tree state in,
    same signature out.
    """
    h = hashlib.sha256()
    for e in sorted(index.tree, key=lambda e: e.rel_path):
        h.update(
            f"{e.rel_path}\x00{int(e.is_dir)}\x00{e.size}\x00{e.mtime}\n".encode()
        )
    return h.hexdigest()


def _load_state() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}  # missing/corrupt -> full rebuild, fail-soft


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def sync_root(
    entry: dict,
    *,
    max_depth: int,
    recent_n: int,
    max_tree_entries: int,
    force: bool = False,
) -> SyncResult:
    """Walk one root and write its digest only when the tree changed.

    Skip requires BOTH an unchanged signature AND the digest file still on
    disk — an operator-deleted digest is re-written even when unchanged.
    `force=True` always re-writes (escape hatch, also for changed walk
    params over an identical tree).
    """
    index = walk_root(entry, max_depth=max_depth, recent_n=recent_n)
    signature = index_signature(index)
    digest_path = INDEX_DIR / f"{index.root_id}.md"
    state = _load_state()
    previous = state.get(index.root_id) or {}
    if (
        not force
        and previous.get("signature") == signature
        and digest_path.exists()
    ):
        return SyncResult(
            written=False, path=digest_path, reason="unchanged", signature=signature
        )
    path = write_index(index, max_tree_entries=max_tree_entries)
    state[index.root_id] = {
        "signature": signature,
        "last_indexed_at": index.generated_at.isoformat(),
    }
    _save_state(state)
    return SyncResult(written=True, path=path, reason=None, signature=signature)


def main(argv: list[str] | None = None) -> int:
    """`wiki index` entry-point — sync digests for watched local roots.

    CONFIG is imported lazily so the walker stays importable without
    config-load side effects (tests, future S03 producer use).
    """
    parser = argparse.ArgumentParser(
        prog="wiki index",
        description="Body-blind folder-index digests for personal.watched_folders.",
    )
    parser.add_argument(
        "root_id", nargs="?", help="sync only this watched_folders entry"
    )
    parser.add_argument(
        "--force", action="store_true", help="re-write even when unchanged"
    )
    args = parser.parse_args(argv)

    from core.config import CONFIG

    entries = list(CONFIG.personal.watched_folders or [])
    local = [e for e in entries if e.get("kind") == "local"]
    smb = [e for e in entries if e.get("kind") == "smb"]

    if args.root_id:
        if any(e.get("id") == args.root_id for e in smb):
            log.error(
                "root %r is kind=smb — NAS indexing lands in S06.", args.root_id
            )
            return 1
        local = [e for e in local if e.get("id") == args.root_id]
        if not local:
            known = ", ".join(str(e.get("id")) for e in entries) or "(none)"
            log.error("unknown watched_folders id %r — known: %s", args.root_id, known)
            return 1
        smb = []

    for e in smb:
        log.info("skipping %s (kind=smb — NAS indexing lands in S06)", e.get("id"))
    if not local:
        log.info(
            "no kind=local watched_folders configured — add entries under "
            "personal.watched_folders (see config.example.yaml)."
        )
        return 0

    failed = 0
    for e in local:
        try:
            result = sync_root(
                e,
                max_depth=CONFIG.limits.folder_index_max_depth,
                recent_n=CONFIG.limits.folder_index_recent_n,
                max_tree_entries=CONFIG.limits.folder_index_max_tree_entries,
                force=args.force,
            )
        except (ValueError, OSError) as exc:
            log.warning("root %s failed: %s", e.get("id"), exc)
            failed += 1
            continue
        if result.written:
            log.info("%s: written %s", e.get("id"), result.path)
        else:
            log.info("%s: unchanged — skipped", e.get("id"))
    return 1 if failed else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
