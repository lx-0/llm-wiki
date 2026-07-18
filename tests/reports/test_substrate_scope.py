"""Tests for the substrate-scope seam — the privacy boundary of reports.

Scope resolution now lives in its own owning module. Both the production
runner and the audit probe import it; the probe imports production, never
the reverse. These tests pin the resolution behaviour AND the import
direction so the privacy contract can't drift back into a one-shot script.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from scripts.reports._engine import audit_scope, runner, substrate_scope
from scripts.reports._engine.substrate_scope import (
    CLINICAL_DEFAULT_SUBSTRATE_GLOBS,
    resolve_substrate_files,
)


def _touch(path: Path, *, age_days: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    when = time.time() - age_days * 86400
    os.utime(path, (when, when))


class TestResolveSubstrateFiles:
    def test_only_files_inside_window(self, tmp_path: Path) -> None:
        _touch(tmp_path / "daily" / "recent.md", age_days=2)
        _touch(tmp_path / "daily" / "stale.md", age_days=40)
        out = resolve_substrate_files(tmp_path, ("daily/*.md",), lookback_days=14)
        names = {p.name for p in out}
        assert names == {"recent.md"}

    def test_dedupes_across_overlapping_globs(self, tmp_path: Path) -> None:
        _touch(tmp_path / "daily" / "a.md", age_days=1)
        out = resolve_substrate_files(
            tmp_path, ("daily/*.md", "daily/a.md"), lookback_days=14
        )
        assert out == [tmp_path / "daily" / "a.md"]

    def test_returns_sorted(self, tmp_path: Path) -> None:
        for name in ("c.md", "a.md", "b.md"):
            _touch(tmp_path / "daily" / name, age_days=1)
        out = resolve_substrate_files(tmp_path, ("daily/*.md",), lookback_days=14)
        assert [p.name for p in out] == ["a.md", "b.md", "c.md"]

    def test_directories_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "daily" / "sub.md").mkdir(parents=True)  # a directory, not a file
        out = resolve_substrate_files(tmp_path, ("daily/*",), lookback_days=14)
        assert out == []


class TestImportDirection:
    def test_probe_and_runner_use_the_production_primitive(self) -> None:
        # Both adapters resolve to the SAME function object from the seam.
        assert audit_scope.resolve_substrate_files is resolve_substrate_files
        assert runner.resolve_substrate_files is resolve_substrate_files

    def test_shared_glob_constant_is_the_seam_constant(self) -> None:
        assert audit_scope.CLINICAL_DEFAULT_SUBSTRATE_GLOBS is CLINICAL_DEFAULT_SUBSTRATE_GLOBS
        assert runner.CLINICAL_DEFAULT_SUBSTRATE_GLOBS is CLINICAL_DEFAULT_SUBSTRATE_GLOBS

    def test_seam_does_not_import_the_probe(self) -> None:
        # The production seam must not depend on the one-shot audit probe.
        # (Prose in the docstring may name it; an import statement may not.)
        src = Path(substrate_scope.__file__).read_text(encoding="utf-8")
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                assert "audit_scope" not in stripped
