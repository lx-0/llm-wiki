"""The source-root layout, pinned (DECISIONS 2026-10-14, M033-S02).

`scripts/` is the engine's source root, not a package: modules import `core.*`,
`collectors.*`, `reports.*` with `scripts/` on `sys.path` — put there by Python itself for
a script run by path, by `core.entry` for a child spawned as `python -m <module>`, by
pytest's `pythonpath` for tests, and by `hooks/_bootstrap.py` for the hooks Claude Code
runs from any directory. Nothing else inserts into `sys.path`, nothing spells the second
identity `scripts.core.*`, and `scripts/__init__.py` must never exist (a regular package
there would make `scripts.core` importable again from `.wiki/` and reopen the split).
"""

from __future__ import annotations

import re
from pathlib import Path

from core import entry

REPO = Path(__file__).resolve().parent.parent
SCANNED = ("scripts", "hooks", "tests")
BOOTSTRAP_ALLOWLIST = {"hooks/_bootstrap.py"}

# import statements AND quoted dotted targets: a monkeypatch.setattr on the quoted
# second-identity path patched the other module object and silently missed (M033-S02-T04)
_SECOND_IDENTITY = re.compile(
    r"^\s*(from\s+scripts\.|import\s+scripts\.)|[\"']scripts\.[a-z_]", re.MULTILINE
)
_SYS_PATH_INSERT = re.compile(r"^\s*sys\.path\.insert\(", re.MULTILINE)


def _py_files() -> list[Path]:
    """Every Python file under the scanned roots — except this guard, whose own
    patterns and comments would match themselves."""
    me = Path(__file__).resolve()
    return sorted(p for d in SCANNED for p in (REPO / d).rglob("*.py") if p.resolve() != me)


def test_no_module_spells_the_second_identity() -> None:
    offenders = [
        f"{p.relative_to(REPO)}:{text[: m.start()].count(chr(10)) + 1}"
        for p in _py_files()
        for text in [p.read_text(encoding="utf-8")]
        for m in _SECOND_IDENTITY.finditer(text)
    ]
    assert offenders == [], "import core.x / reports.x, never scripts.core.x:\n" + "\n".join(
        offenders
    )


def test_sys_path_is_only_touched_by_the_hooks_bootstrap() -> None:
    offenders = [
        str(p.relative_to(REPO))
        for p in _py_files()
        if _SYS_PATH_INSERT.search(p.read_text(encoding="utf-8"))
        and str(p.relative_to(REPO)) not in BOOTSTRAP_ALLOWLIST
    ]
    assert offenders == [], "sys.path.insert outside hooks/_bootstrap.py:\n" + "\n".join(offenders)
    assert (REPO / "hooks" / "_bootstrap.py").is_file()


def test_scripts_is_not_a_package() -> None:
    assert not (REPO / "scripts" / "__init__.py").exists()


def test_scripts_dir_is_the_source_root_pytest_put_on_the_path() -> None:
    import core.config as cfg

    assert Path(cfg.__file__).resolve().parent.parent == entry.SCRIPTS_DIR


# ── documented invocations ────────────────────────────────────────────────────
# A sub-package module cannot run by file path any more (no per-module bootstrap since
# T04): a docstring or doc that still says `uv run python scripts/<pkg>/<x>.py` sends the
# operator into `ModuleNotFoundError: core`. Spell `wiki <cmd>`, a top-level entry script,
# or `python -m <pkg>.<module>` with scripts/ on PYTHONPATH (M033-S02-T06).
_DOC_ROOTS = ("docs", "templates", "AGENTS.md", "README.md")
_BY_PATH_INVOCATION = re.compile(
    r"uv run (?:--project \S+ )?python (?:\S*/)?scripts/[a-z_]+/[a-z_-]+\.py"
)


def _documented_files() -> list[Path]:
    files = _py_files()
    for root in _DOC_ROOTS:
        path = REPO / root
        files.extend([path] if path.is_file() else sorted(path.rglob("*.md")))
    return files


def test_no_documented_invocation_runs_a_sub_package_module_by_path() -> None:
    offenders = [
        f"{path.relative_to(REPO)}:{n}: {line.strip()[:100]}"
        for path in _documented_files()
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
        if _BY_PATH_INVOCATION.search(line)
    ]
    assert offenders == [], (
        "by-path invocations of sub-package modules (spell `wiki <cmd>`, a top-level entry "
        "script, or `python -m <pkg>.<module>`):\n" + "\n".join(offenders)
    )
