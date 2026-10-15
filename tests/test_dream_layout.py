"""M033-S04-T07 — the dream split's patch surface.

`dream.py` is split into `dream_model` / `dream_corpus` / `dream_priority`. A name
bound in several of them (`ROOT_DIR`) is read in several of them, so a test that
patches it on one module silently leaves the others on the real vault — the patch
passes, the isolation does not happen. Every direct `monkeypatch.setattr` on a dream
module in `tests/` must therefore name something exactly that module binds; a name
bound in more than one goes through `tests/_dream_paths.py:patch_dream_path`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._dream_paths import DREAM_MODULES, dream_modules

TESTS = Path(__file__).resolve().parent


def _direct_patches() -> list[tuple[str, int, str, str]]:
    """(file, line, module, name) for every `<x>.setattr(<dream module>, "NAME", …)` and
    `<x>.setattr("<dream module>.NAME", …)` in tests/."""
    found: list[tuple[str, int, str, str]] = []
    for path in sorted(TESTS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = {
            (a.asname or a.name): a.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for a in node.names
            if a.name in DREAM_MODULES
        }
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setattr"
                and node.args
            ):
                continue
            first = node.args[0]
            if isinstance(first, ast.Name) and first.id in aliases and len(node.args) > 1:
                name_arg = node.args[1]
                if isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str):
                    found.append((path.name, node.lineno, aliases[first.id], name_arg.value))
            elif isinstance(first, ast.Constant) and isinstance(first.value, str):
                module, _, name = first.value.rpartition(".")
                if module in DREAM_MODULES:
                    found.append((path.name, node.lineno, module, name))
    return found


def test_direct_dream_patches_name_a_single_binder() -> None:
    bound = {mod.__name__: set(vars(mod)) for mod in dream_modules()}
    problems = []
    for file, line, module, name in _direct_patches():
        binders = sorted(m for m, names in bound.items() if name in names)
        if binders != [module]:
            hint = " — use patch_dream_path" if len(binders) > 1 else ""
            problems.append(
                f"{file}:{line} patches {module}.{name}, bound by {binders or 'no module'}{hint}"
            )
    assert problems == [], "\n".join(problems)


def test_the_scan_sees_the_patch_forms_the_tests_use() -> None:
    # The guard is only as good as its parser: it must see both forms in use today.
    forms = {(module, name) for _f, _l, module, name in _direct_patches()}
    assert ("dream", "query") in forms  # monkeypatch.setattr(dream, "query", …)
    assert any(f == "test_dream_cycle.py" for f, _l, _m, _n in _direct_patches())
