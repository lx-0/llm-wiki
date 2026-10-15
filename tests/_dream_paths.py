"""Patch a dream-subsystem name in every module that binds it (M033-S04-T07).

`dream.py` is split into `dream_model` (entities + cooldown), `dream_corpus` (corpus
assembly, activation + backoff side-state) and `dream_priority` (M017 sweep
priority). A constant such as `ROOT_DIR` is bound — and read — in several of them;
patching it on one module leaves the others reading the real vault. Tests patch
through `patch_dream_path`, and `tests/test_dream_layout.py` refuses a direct patch
of a name more than one dream module binds.
"""

from __future__ import annotations

import importlib
from types import ModuleType

import pytest

DREAM_MODULES = ("dream", "dream_model", "dream_corpus", "dream_priority")


def dream_modules() -> list[ModuleType]:
    return [importlib.import_module(name) for name in DREAM_MODULES]


def patch_dream_path(monkeypatch: pytest.MonkeyPatch, name: str, value: object) -> None:
    """Patch `name` on every dream module that binds it; fail when none does (a patch
    of a name nothing binds would isolate nothing)."""
    binders = [mod for mod in dream_modules() if name in vars(mod)]
    assert binders, f"no dream module binds {name!r} — the patch would isolate nothing"
    for mod in binders:
        monkeypatch.setattr(mod, name, value)
