"""Patch a name wherever `core.health` binds it (M033-S04-T07).

`core.health` is a package: its checks live in `environment` / `engine` / `pipeline`,
each importing the vault paths it reads from `core.paths`. A test that patched
`health.ROOT_DIR` on the package would patch an object no check reads — the package
binds none of those names (`tests/test_health_package.py`), so such a patch raises. This
helper patches every submodule that binds the name and fails if none does.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType
from typing import Any

import pytest

from core import health


def health_modules() -> list[ModuleType]:
    """The package plus every submodule of it."""
    modules: list[ModuleType] = [health]
    for info in pkgutil.iter_modules(health.__path__):
        modules.append(importlib.import_module(f"core.health.{info.name}"))
    return modules


def patch_health_path(monkeypatch: pytest.MonkeyPatch, name: str, value: Any) -> None:
    """Patch `name` on every `core.health` module that binds it (at least one must)."""
    owners = [m for m in health_modules() if name in vars(m)]
    assert owners, f"no core.health module binds {name!r}"
    for module in owners:
        monkeypatch.setattr(module, name, value)
