"""M033-S04-T07 — `core.health` is a package; its checks live in submodules.

A test that patches a name on the package patches an object no check reads. So the
package binds none of the names the tests patch (the surface measured 2026-10-15): a stale
`monkeypatch.setattr(health, "WIKI_DIR", …)` raises AttributeError instead of silently
isolating nothing. Every such name has an owning submodule, which
`tests/_health_paths.py` patches.
"""

from __future__ import annotations

import pytest

from core import health

PATCHED = (
    "ROOT_DIR",
    "KNOWLEDGE_DIR",
    "LOGS_DIR",
    "STATE_DIR",
    "STATE_FILE",
    "WIKI_DIR",
    "_piggyback_tasks",
    "_failed_imports",
    "_declared_import_names",
    "_effective_env_dir",
    "_is_dataless",
    "_FLUSH_LOG_TAIL_BYTES",
)


def test_the_package_binds_no_patched_name() -> None:
    bound = sorted(n for n in PATCHED if n in vars(health))
    assert bound == [], (
        f"core.health binds {bound}: a test patching them on the package would isolate "
        "nothing — import them only in the submodule that reads them"
    )


def test_every_patched_name_has_an_owning_submodule() -> None:
    from ._health_paths import health_modules

    owners = {n: [m.__name__ for m in health_modules() if n in vars(m)] for n in PATCHED}
    assert [n for n, mods in owners.items() if not mods] == []


def test_a_stale_package_patch_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(AttributeError):
        monkeypatch.setattr(health, "WIKI_DIR", "/nowhere")
