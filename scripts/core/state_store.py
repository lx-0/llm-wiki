"""The locked/atomic JSON state seam — one home for flock + torn-write knowledge.

Before this module, ``fcntl.flock`` was hand-copied across the engine in three
idioms (blocking RMW contextmanagers in usage / capture_index /
piggyback_runner, non-blocking try-locks in compile / flush, and dream.py's
private unlocked atomic-replace pair), and ``state.json`` — the one state file
whose loss costs a full recompile — had three unlocked whole-dict writers
(compile / query / lint) racing last-writer-wins. Lock and atomicity policy
now concentrates here: a future lock-timeout or stale-lock rule is one edit,
not seven.

Three layers, smallest interface first:

1. flock primitives — ``locked`` (blocking), ``try_locked`` (non-blocking,
   yields bool), ``acquire_process_lock`` (non-blocking process-lifetime
   mutex; the kernel releases on exit).
2. ``state.json`` seam — ``update_state`` (locked read-modify-write; every
   writer merges its OWN keys into a fresh disk read, so a long-running
   compile can no longer clobber a query/lint counter written meanwhile) and
   the ingested-ledger query API (``ingested_ledger`` / ``is_ingested`` /
   ``pending_paths``). The ledger schema — ROOT_DIR-relative path → plain
   16-hex content hash, with legacy ``{"hash": ...}`` dict values tolerated —
   lives ONLY here; hand-rolled consumers drifted apart and silently killed
   flush's skip branch (see tests/test_flush_trigger.py).
3. ``StateStore`` — a load-once/locked-write facade for hot side-state files
   (dream-activation, insufficient-corpus): ``load()`` caches so per-item
   scoring stops re-parsing the store from disk (the recorded O(N²)
   per-item-over-all-items hang class), while ``update()`` always re-reads
   fresh under the lock so concurrent writers merge instead of clobber.

Reading state stays where it always was (``core.utils.load_state`` /
``load_json_state``); every WRITE path belongs here or goes through the
atomic ``core.utils.save_json_state``.
"""

from __future__ import annotations

import fcntl
import io
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from .paths import ROOT_DIR, STATE_FILE
from .utils import (
    _DEFAULT_STATE,
    file_hash,
    list_raw_files,
    load_json_state,
    save_json_state,
)

# ── flock primitives ─────────────────────────────────────────────────


def _lock_path_for(path: Path) -> Path:
    """Sibling ``<name>.lock`` file for a state file. The lock lives on a
    separate file so we never truncate the data file while holding only a
    shared view of it."""
    return path.with_name(path.name + ".lock")


@contextmanager
def locked(lock_path: Path):
    """Blocking exclusive flock on ``lock_path`` for a read-modify-write
    critical section. Parent dirs are created; the lock is released and the
    handle closed on exit (also on exception)."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        finally:
            fd.close()


@contextmanager
def try_locked(lock_path: Path):
    """Non-blocking exclusive flock: yields True when acquired, False when
    another process holds it. For first-wins/skip semantics (idempotent
    best-effort work like the dashboard refresh) where waiting is worse than
    skipping — the next run picks up the latest state anyway."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "w")
    acquired = False
    try:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError:
            pass
        yield acquired
    finally:
        if acquired:
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        fd.close()


def acquire_process_lock(lock_path: Path) -> io.IOBase | None:
    """Non-blocking process-lifetime mutex (one <task> process at a time).

    Returns the open file handle on success — the caller MUST keep the
    reference alive for the duration of the critical section; the kernel
    releases the flock automatically on process exit (or on explicit
    ``handle.close()``), so no manual unlock is needed. Returns ``None``
    when another process already holds the lock.

    Background: 2026-05-15 incident — parallel SessionEnd hooks each spawned
    ``compile.py --file daily/<X>.md`` for the same daily file, producing 3-4
    concurrent bundled-CLI subprocesses that competed for the Claude
    subscription quota and crashed mid-stream with ``kind=unknown``/empty
    stderr. A single global compile-lock prevents the storm.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fd.close()
        return None
    return fd


# ── state.json seam ──────────────────────────────────────────────────


def update_state(mutator: Callable[[dict], None]) -> dict:
    """Locked read-modify-write on the engine's primary ``state.json``.

    Takes a fresh disk read under the exclusive lock, applies ``mutator``
    (mutate in place — set/merge only the keys this writer owns), saves
    atomically, and returns the saved state. Concurrent writers each merge
    into the latest state instead of clobbering whole-dict — the fix for the
    compile-holds-its-copy-for-the-whole-run race that dropped query/lint
    counter writes (and, in the rare inverse direction, a freshly-ingested
    hash, i.e. a recompile's worth of tokens).

    A corrupt ``state.json`` raises (ValueError from json) rather than being
    silently replaced with defaults — this is the one state file whose loss
    costs real money, so fail loudly and let the operator look.
    """
    with locked(_lock_path_for(STATE_FILE)):
        state = load_json_state(STATE_FILE, _DEFAULT_STATE)
        mutator(state)
        save_json_state(STATE_FILE, state)
    return state


def _ledger_hash(value: object) -> str:
    """Normalize one ledger value to its hash string. Current schema stores
    the plain 16-hex ``file_hash`` string; pre-2026-05 state files used a
    ``{"hash": ..., "compiled_at": ...}`` dict — both shapes collapse here so
    no consumer ever re-implements the tolerance (the drift that killed
    flush's skip branch)."""
    if isinstance(value, dict):
        return str(value.get("hash", ""))
    return str(value)


def ingested_ledger() -> dict[str, str]:
    """The normalized ingested ledger: ROOT_DIR-relative path → content hash.

    Fresh disk read (short-lived callers expect current state). Raises on a
    corrupt state.json — same posture as ``update_state``."""
    state = load_json_state(STATE_FILE, _DEFAULT_STATE)
    ingested = state.get("ingested", {})
    if not isinstance(ingested, dict):
        return {}
    return {str(k): _ledger_hash(v) for k, v in ingested.items()}


def is_ingested(path: Path, *, ledger: dict[str, str] | None = None) -> bool:
    """True iff ``path``'s CURRENT content hash matches its ledger entry —
    i.e. compile has already processed exactly this content and would skip it.

    Pass a pre-loaded ``ledger`` when checking many paths. A path outside the
    vault, an unreadable file, or a missing entry are all "not ingested"."""
    led = ledger if ledger is not None else ingested_ledger()
    try:
        rel = str(path.relative_to(ROOT_DIR))
    except ValueError:
        return False
    stored = led.get(rel)
    if not stored:
        return False
    try:
        return stored == file_hash(path)
    except OSError:
        return False


def pending_paths() -> list[Path]:
    """All raw/ + daily/ files whose content hash differs from the ledger —
    compile's candidate set, in ``list_raw_files`` order (mtime DESC, newest
    first, so rate-limit aborts starve old backlog rather than fresh
    activity). Unreadable files are skipped."""
    led = ingested_ledger()
    pending: list[Path] = []
    for f in list_raw_files():
        try:
            rel = str(f.relative_to(ROOT_DIR))
        except ValueError:
            continue
        try:
            current = file_hash(f)
        except (OSError, ValueError):
            continue
        if led.get(rel) != current:
            pending.append(f)
    return pending


# ── StateStore facade for hot side-state files ───────────────────────


class StateStore:
    """One JSON state file behind a load-once read cache + locked atomic writes.

    For "hot" stores that per-item loops consult repeatedly (dream-activation,
    insufficient-corpus): ``load()`` parses the file ONCE per process and hands
    back the cached dict — treat it as read-only; every mutation goes through
    ``update()``, which re-reads FRESH under the exclusive lock, applies the
    mutator, saves atomically (tmp + os.replace via ``save_json_state``), and
    refreshes the cache. Fresh-read-under-lock means concurrent writers merge
    key-wise instead of clobbering each other's entries.

    ``tolerant=True`` (default) loads a corrupt/unreadable file as ``default``
    — right for rebuildable side-state. Format knobs (``sort_keys`` /
    ``trailing_newline``) keep pre-existing on-disk serializations
    byte-stable across the migration onto this facade.
    """

    def __init__(
        self,
        path: Path,
        *,
        default: dict | None = None,
        tolerant: bool = True,
        sort_keys: bool = False,
        trailing_newline: bool = False,
        lock_path: Path | None = None,
    ) -> None:
        self.path = path
        self.lock_path = lock_path or _lock_path_for(path)
        self._default = dict(default) if default else {}
        self._tolerant = tolerant
        self._sort_keys = sort_keys
        self._trailing_newline = trailing_newline
        self._cache: dict | None = None

    def _read(self) -> dict:
        try:
            data = load_json_state(self.path, self._default)
        except (ValueError, OSError):
            if self._tolerant:
                return dict(self._default)
            raise
        if not isinstance(data, dict):
            if self._tolerant:
                return dict(self._default)
            raise ValueError(f"{self.path}: expected a JSON object at top level")
        return data

    def load(self) -> dict:
        """Cached snapshot (first call reads disk). READ-ONLY by contract —
        mutations that bypass ``update()`` are neither locked nor persisted."""
        if self._cache is None:
            self._cache = self._read()
        return self._cache

    def reload(self) -> dict:
        """Force a fresh disk read and refresh the cache."""
        self._cache = self._read()
        return self._cache

    def update(self, mutator: Callable[[dict], None]) -> dict:
        """Locked RMW: fresh disk read under the lock → ``mutator(data)`` →
        atomic save → cache refresh. Always writes (call sites gate no-op
        updates on ``load()`` when churn matters). Returns the saved state."""
        with locked(self.lock_path):
            data = self._read()
            mutator(data)
            save_json_state(
                self.path,
                data,
                sort_keys=self._sort_keys,
                trailing_newline=self._trailing_newline,
            )
        self._cache = data
        return data


_STORES: dict[Path, StateStore] = {}


def store_for(path: Path, **kwargs) -> StateStore:
    """Process-wide singleton ``StateStore`` per path — the load-once cache
    lives on the instance, so every consumer of the same file shares it.
    Constructor kwargs apply on first call only (same file, same format)."""
    store = _STORES.get(path)
    if store is None:
        store = StateStore(path, **kwargs)
        _STORES[path] = store
    return store
