"""Keep test writes inside the checkout.

`core.paths` derives every engine path from `__file__` under the assumption
that the engine is installed as `<vault>/.wiki/`::

    CORE_DIR = <engine>/scripts/core
    WIKI_DIR = <engine>
    ROOT_DIR = WIKI_DIR.parent      # the vault — in a real install

In a development checkout that last line resolves to the directory *next to*
the repo, so every constant derived from `ROOT_DIR` (`DAILY_DIR`, `RAW_DIR`,
`KNOWLEDGE_DIR`, `_dashboard-*.md`, …) points at the operator's filesystem
instead of at a vault. A test that exercises a real write path therefore
litters the parent directory — silently, because nothing there is under git.

Two layers keep that contained:

1. `isolated_vault_paths` (autouse in `conftest.py`) repoints the vault-content
   constants that tests actually reach at a per-test sink under pytest's tmp
   base. Tests that patch the same constant themselves still win — their
   `monkeypatch` runs after this fixture.
2. `install_write_guard` intercepts the write entry points and raises on the
   first write landing under `ROOT_DIR` but outside the checkout, so a new
   collector that forgets layer 1 fails loudly instead of leaking.

Incident 2026-07-25: 22 tests across five collector suites had been appending
real daily rollups to `<checkout>/../daily/<date>/{captures,voice,pictures}.md`
ever since those collectors were written — plus `2025-05-15/voice.md` from a
fixed-date fixture. Layer 2 is what makes the next one a red test.
"""

from __future__ import annotations

import builtins
import io
import os
from pathlib import Path

from core.paths import ROOT_DIR, WIKI_DIR

# Everything under ROOT_DIR but outside WIKI_DIR is "the vault" — off-limits
# during tests. Compared as string prefixes: this runs on every write in the
# suite, so it must not cost a syscall.
_ROOT_PREFIX = f"{ROOT_DIR}{os.sep}"
_WIKI_PREFIX = f"{WIKI_DIR}{os.sep}"

_WRITE_MODE_CHARS = frozenset("wxa+")


class VaultWriteEscape(RuntimeError):
    """A test wrote outside the checkout, into the inferred vault root."""


def _escapee(path: object) -> str | None:
    """Return the offending absolute path, or None if the write is allowed."""
    try:
        raw = os.fspath(path)  # type: ignore[arg-type]
    except TypeError:
        return None  # file descriptor or other non-path — not our business
    text = raw if isinstance(raw, str) else os.fsdecode(raw)
    if not text.startswith(os.sep):
        text = os.path.abspath(text)
    if text.startswith(_ROOT_PREFIX) and not text.startswith(_WIKI_PREFIX):
        return text
    return None


def _reject(path: object, operation: str) -> None:
    offender = _escapee(path)
    if offender is None:
        return
    raise VaultWriteEscape(
        f"{operation} escaped the checkout: {offender}\n"
        f"  checkout:   {WIKI_DIR}\n"
        f"  ROOT_DIR:   {ROOT_DIR}  (core.paths assumes <vault>/.wiki/ — in a dev\n"
        f"              checkout this is the directory NEXT TO the repo)\n"
        "Repoint the path constant this code reads (monkeypatch it at the module\n"
        "that owns it, e.g. `core.daily_capture.DAILY_DIR`) so the write lands in\n"
        "tmp_path. See tests/_vault_isolation.py."
    )


def _is_write_mode(mode: object) -> bool:
    return any(char in str(mode) for char in _WRITE_MODE_CHARS)


_ORIGINALS: dict[str, object] = {}


def install_write_guard() -> None:
    """Patch the write entry points. Idempotent; undone by `remove_write_guard`."""
    if _ORIGINALS:
        return

    _ORIGINALS.update(
        builtins_open=builtins.open,
        io_open=io.open,
        path_open=Path.open,
        path_mkdir=Path.mkdir,
        os_makedirs=os.makedirs,
        os_mkdir=os.mkdir,
        os_rename=os.rename,
        os_replace=os.replace,
        os_remove=os.remove,
        os_unlink=os.unlink,
        os_rmdir=os.rmdir,
    )

    def guarded_open(file, mode="r", *args, **kwargs):
        if _is_write_mode(mode):
            _reject(file, "open()")
        return _ORIGINALS["builtins_open"](file, mode, *args, **kwargs)  # type: ignore[operator]

    def guarded_path_open(self, mode="r", *args, **kwargs):
        if _is_write_mode(mode):
            _reject(self, "Path.open()")
        return _ORIGINALS["path_open"](self, mode, *args, **kwargs)  # type: ignore[operator]

    def guarded_path_mkdir(self, *args, **kwargs):
        _reject(self, "Path.mkdir()")
        return _ORIGINALS["path_mkdir"](self, *args, **kwargs)  # type: ignore[operator]

    def _guard_os(name: str, label: str, arg_index: int = 0):
        original = _ORIGINALS[name]

        def guarded(*args, **kwargs):
            if len(args) > arg_index:
                _reject(args[arg_index], label)
            return original(*args, **kwargs)  # type: ignore[operator]

        return guarded

    builtins.open = guarded_open
    io.open = guarded_open
    Path.open = guarded_path_open  # type: ignore[method-assign]
    Path.mkdir = guarded_path_mkdir  # type: ignore[method-assign]
    os.makedirs = _guard_os("os_makedirs", "os.makedirs()")
    os.mkdir = _guard_os("os_mkdir", "os.mkdir()")
    # rename/replace guard the destination — moving something INTO the vault leaks too.
    os.rename = _guard_os("os_rename", "os.rename()", arg_index=1)
    os.replace = _guard_os("os_replace", "os.replace()", arg_index=1)
    os.remove = _guard_os("os_remove", "os.remove()")
    os.unlink = _guard_os("os_unlink", "os.unlink()")
    os.rmdir = _guard_os("os_rmdir", "os.rmdir()")


def remove_write_guard() -> None:
    """Restore the unpatched write entry points."""
    if not _ORIGINALS:
        return
    builtins.open = _ORIGINALS["builtins_open"]  # type: ignore[assignment]
    io.open = _ORIGINALS["io_open"]  # type: ignore[assignment]
    Path.open = _ORIGINALS["path_open"]  # type: ignore[method-assign]
    Path.mkdir = _ORIGINALS["path_mkdir"]  # type: ignore[method-assign]
    os.makedirs = _ORIGINALS["os_makedirs"]  # type: ignore[assignment]
    os.mkdir = _ORIGINALS["os_mkdir"]  # type: ignore[assignment]
    os.rename = _ORIGINALS["os_rename"]  # type: ignore[assignment]
    os.replace = _ORIGINALS["os_replace"]  # type: ignore[assignment]
    os.remove = _ORIGINALS["os_remove"]  # type: ignore[assignment]
    os.unlink = _ORIGINALS["os_unlink"]  # type: ignore[assignment]
    os.rmdir = _ORIGINALS["os_rmdir"]  # type: ignore[assignment]
    _ORIGINALS.clear()
