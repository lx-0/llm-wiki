"""Air-gap regression tests for the compile substrate-scope policy.

M019-S01-T03 implements the air-gap as:
  (a) Constant `COMPILE_SUBSTRATE_EXCLUDED_PREFIXES` in `scripts/core/config.py`
  (b) Helper `is_compile_excluded_path(rel_path)` in `scripts/core/utils.py`
  (c) Filter in `list_raw_files()` applying (b)
  (d) Prompt SCOPE block in `prompts/compile_main_system.md` listing `reports/**`

This file pins all four.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.core.config import COMPILE_SUBSTRATE_EXCLUDED_PREFIXES
from scripts.core.utils import is_compile_excluded_path


# ── (a) Constant invariants ──────────────────────────────────────────


def test_reports_is_excluded_prefix() -> None:
    """Reports/ MUST be in the excluded set — air-gap depends on it."""
    assert "reports/" in COMPILE_SUBSTRATE_EXCLUDED_PREFIXES


def test_engine_subtrees_excluded() -> None:
    for expected in (".wiki/", ".ytstack/", ".obsidian/", ".git/"):
        assert expected in COMPILE_SUBSTRATE_EXCLUDED_PREFIXES


def test_excluded_prefixes_have_trailing_slash() -> None:
    """Form invariant — match is segment-anchored via startswith()."""
    for pre in COMPILE_SUBSTRATE_EXCLUDED_PREFIXES:
        assert pre.endswith("/"), f"{pre!r} must end with '/'"
        assert not pre.startswith("/"), f"{pre!r} must not start with '/'"


# ── (b) is_compile_excluded_path semantics ───────────────────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        "reports/studies/longitudinal-baseline/runs/2026-05-17/phq-9.md",
        "reports/analyses/2026-05-17.md",
        "reports/",
        ".wiki/scripts/compile.py",
        ".ytstack/STATE.md",
        ".obsidian/workspace.json",
    ],
)
def test_excluded_paths_blocked(rel_path: str) -> None:
    assert is_compile_excluded_path(rel_path), (
        f"{rel_path!r} should be blocked by the air-gap"
    )


@pytest.mark.parametrize(
    "rel_path",
    [
        "daily/2026-05-17.md",
        "raw/notes/voice/2026-05-17-001.md",
        "raw/transcripts/jamie/2026-05-15--review.md",
        "knowledge/concepts/foo.md",
        # Segment-anchored: 'raw/reports/x.md' starts with 'raw/', not 'reports/'.
        "raw/reports/false-positive.md",
        # Same: 'archived-reports/' is not 'reports/'.
        "archived-reports/old.md",
    ],
)
def test_allowed_paths_pass(rel_path: str) -> None:
    assert not is_compile_excluded_path(rel_path), (
        f"{rel_path!r} should pass the air-gap filter"
    )


def test_handles_pathlib_input() -> None:
    """Helper accepts Path objects too, not just strings."""
    assert is_compile_excluded_path(Path("reports") / "studies" / "x.md")
    assert not is_compile_excluded_path(Path("daily") / "2026-05-17.md")


def test_handles_leading_slash() -> None:
    """Rel-paths with accidental leading slash still match correctly."""
    assert is_compile_excluded_path("/reports/x.md")


# ── (c) list_raw_files() applies the filter ──────────────────────────


def test_list_raw_files_excludes_reports_at_vault_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the walker were ever to surface a vault-root reports/ file,
    the filter must drop it. Today's walker doesn't enter reports/ —
    we simulate the future-walker-expansion case by symlinking a
    reports/ file under raw/ (rglob follows file symlinks)."""
    vault = tmp_path / "vault"
    (vault / "daily").mkdir(parents=True)
    (vault / "raw" / "notes").mkdir(parents=True)
    (vault / "reports").mkdir(parents=True)

    (vault / "daily" / "2026-05-17.md").write_text("# Daily\n", encoding="utf-8")
    (vault / "raw" / "notes" / "voice.md").write_text("# Voice\n", encoding="utf-8")
    real_report = vault / "reports" / "study.md"
    real_report.write_text("# Report (must NEVER reach compile)\n", encoding="utf-8")

    # Symlink from raw/ → reports/study.md. rglob follows file
    # symlinks, so the walker sees the target. The filter must drop it
    # by resolving the symlink and checking the resolved rel-path.
    leak = vault / "raw" / "notes" / "leak-via-symlink.md"
    try:
        leak.symlink_to(real_report)
    except OSError:
        pytest.skip("symlinks not supported on this filesystem")

    monkeypatch.setattr("scripts.core.utils.DAILY_DIR", vault / "daily")
    monkeypatch.setattr("scripts.core.utils.RAW_DIR", vault / "raw")

    from scripts.core.utils import list_raw_files
    listed = list_raw_files()

    resolved_listed = [p.resolve() for p in listed]
    real_report_resolved = real_report.resolve()
    assert real_report_resolved not in resolved_listed, (
        "reports/study.md leaked into list_raw_files() output via symlink — "
        "filter did not catch the resolved path"
    )

    rel_paths = [str(p.resolve().relative_to(vault.resolve())) for p in listed]
    assert "daily/2026-05-17.md" in rel_paths
    assert "raw/notes/voice.md" in rel_paths


# ── (d) Compile prompt mentions reports/ in its SCOPE block ──────────


def test_compile_prompt_lists_reports_as_excluded() -> None:
    """`compile_main_system.md` SCOPE block lists `reports/**` explicitly.

    Belt-and-braces: even if the constant flips, the prompt itself
    tells the agent not to touch reports/. This is the second line
    of defense (the first is `make_path_scope_gate` restricting Write
    to `knowledge/`).
    """
    repo_root = Path(__file__).resolve().parents[2]
    prompt = (repo_root / "prompts" / "compile_main_system.md").read_text(
        encoding="utf-8"
    )
    assert "reports/**" in prompt, (
        "compile_main_system.md must list reports/** in its SCOPE block"
    )
