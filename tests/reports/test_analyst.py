"""Tests for the M019-S05 analyst layer — prompt-building +
persistence (not the live SDK call).

The actual `run_analyst()` invocation is exercised in S05-T06's live
test against lxw substrate — unit-testing the SDK call would require
elaborate mocking that adds little signal. Here we lock the
deterministic pieces: how prompts get composed, how outputs land on
disk with correct frontmatter.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.analyze import (
    _build_pass1_user_prompt,
    _build_pass2_user_prompt,
    _latest_run_dir,
    _persist_pass1,
    _persist_pass2,
    _previous_run_dir,
)
from scripts.reports._engine.lib.analyst import AnalystResult
from scripts.reports._engine.study import Study, StudyManifest, StudyState


MANIFEST = {
    "study_id": "test-baseline",
    "title": "Test baseline",
    "created": "2026-05-17T00:00:00+00:00",
    "schedule": "weekly",
    "instruments": [
        {"slug": "phq-9", "version": "1.0.0", "source": "inferred"},
        {"slug": "gad-7", "version": "1.0.0", "source": "inferred"},
    ],
}


def _build_study_dir(tmp_path: Path, runs: list[dict]) -> Study:
    study_dir = tmp_path / "test-baseline"
    study_dir.mkdir(parents=True)
    (study_dir / "manifest.yaml").write_text(
        yaml.safe_dump(MANIFEST, sort_keys=False), encoding="utf-8"
    )
    runs_dir = study_dir / "runs"
    runs_dir.mkdir()
    for run in runs:
        ts_dir = runs_dir / run["timestamp"]
        ts_dir.mkdir()
        (ts_dir / "_summary.md").write_text(
            run.get("summary", "# summary\n"),
            encoding="utf-8",
        )
        inst_dir = ts_dir / "instruments"
        inst_dir.mkdir()
        for slug, body in run.get("instruments", {}).items():
            (inst_dir / f"{slug}.md").write_text(body, encoding="utf-8")
    return Study.load(study_dir)


class TestRunDirHelpers:
    def test_latest_run_dir_picks_lexically_max(self, tmp_path: Path) -> None:
        study = _build_study_dir(
            tmp_path,
            [
                {"timestamp": "2026-05-10T10-00-00"},
                {"timestamp": "2026-05-17T10-00-00"},
                {"timestamp": "2026-05-15T10-00-00"},
            ],
        )
        latest = _latest_run_dir(study)
        assert latest is not None
        assert latest.name == "2026-05-17T10-00-00"

    def test_latest_skips_tmp_dirs(self, tmp_path: Path) -> None:
        study = _build_study_dir(
            tmp_path, [{"timestamp": "2026-05-17T10-00-00"}]
        )
        # Plant a stale tmp dir
        (study.runs_dir / ".2026-05-18T10-00-00.tmp").mkdir()
        latest = _latest_run_dir(study)
        assert latest is not None
        assert latest.name == "2026-05-17T10-00-00"

    def test_latest_returns_none_when_no_runs(self, tmp_path: Path) -> None:
        study = _build_study_dir(tmp_path, [])
        assert _latest_run_dir(study) is None

    def test_previous_run_dir(self, tmp_path: Path) -> None:
        study = _build_study_dir(
            tmp_path,
            [
                {"timestamp": "2026-05-10T10-00-00"},
                {"timestamp": "2026-05-15T10-00-00"},
                {"timestamp": "2026-05-17T10-00-00"},
            ],
        )
        latest = _latest_run_dir(study)
        assert latest is not None
        prev = _previous_run_dir(study, latest)
        assert prev is not None
        assert prev.name == "2026-05-15T10-00-00"

    def test_previous_none_on_single_run(self, tmp_path: Path) -> None:
        study = _build_study_dir(
            tmp_path, [{"timestamp": "2026-05-17T10-00-00"}]
        )
        latest = _latest_run_dir(study)
        assert latest is not None
        assert _previous_run_dir(study, latest) is None


class TestPass1Prompt:
    def test_inlines_manifest_summary_and_instruments(self, tmp_path: Path) -> None:
        study = _build_study_dir(
            tmp_path,
            [{
                "timestamp": "2026-05-17T10-00-00",
                "summary": "# summary content\nfoo bar baz\n",
                "instruments": {
                    "phq-9": "# phq-9 report\nQ3 sleep evidence ...\n",
                    "gad-7": "# gad-7 report\nQ1 nervous ...\n",
                },
            }],
        )
        run_dir = _latest_run_dir(study)
        prompt = _build_pass1_user_prompt(study, run_dir)  # type: ignore[arg-type]
        assert "test-baseline" in prompt
        assert "## Manifest" in prompt
        assert "study_id: test-baseline" in prompt
        assert "## Deterministic summary" in prompt
        assert "summary content" in prompt
        assert "## Per-instrument report: `instruments/phq-9.md`" in prompt
        assert "Q3 sleep evidence" in prompt
        assert "## Per-instrument report: `instruments/gad-7.md`" in prompt
        # Heading instruction at end
        assert "Heading: `# Analysis — test-baseline" in prompt

    def test_includes_previous_summary_when_present(self, tmp_path: Path) -> None:
        study = _build_study_dir(
            tmp_path,
            [
                {
                    "timestamp": "2026-05-10T10-00-00",
                    "summary": "# OLD summary\nprev-data\n",
                },
                {
                    "timestamp": "2026-05-17T10-00-00",
                    "summary": "# NEW summary\ncurrent-data\n",
                    "instruments": {"phq-9": "# phq-9 ...\n"},
                },
            ],
        )
        run_dir = _latest_run_dir(study)
        prompt = _build_pass1_user_prompt(study, run_dir)  # type: ignore[arg-type]
        assert "Previous run's summary" in prompt
        assert "prev-data" in prompt

    def test_no_previous_section_on_single_run(self, tmp_path: Path) -> None:
        study = _build_study_dir(
            tmp_path,
            [{
                "timestamp": "2026-05-17T10-00-00",
                "summary": "# summary\n",
                "instruments": {"phq-9": "# phq-9\n"},
            }],
        )
        run_dir = _latest_run_dir(study)
        prompt = _build_pass1_user_prompt(study, run_dir)  # type: ignore[arg-type]
        assert "Previous run's summary" not in prompt


class TestPass2Prompt:
    def test_n1_acknowledges_single_study(self, tmp_path: Path) -> None:
        study = _build_study_dir(
            tmp_path,
            [{
                "timestamp": "2026-05-17T10-00-00",
                "summary": "# sum\n",
                "instruments": {"phq-9": "# phq-9\n"},
            }],
        )
        latest = _latest_run_dir(study)
        summary = latest / "_summary.md"  # type: ignore[union-attr]
        analysis = latest / "_analysis.md"  # type: ignore[union-attr]
        analysis.write_text("# pass-1 body\n", encoding="utf-8")

        prompt = _build_pass2_user_prompt([(study, summary, analysis)])
        assert "1 study" in prompt
        assert "test-baseline" in prompt
        assert "Latest `_analysis.md`" in prompt
        # Bullet instruction at end mentions N=1 framing
        assert "N=1" in prompt

    def test_n2_inlines_both_studies(self, tmp_path: Path) -> None:
        # Build two synthetic studies
        s1 = _build_study_dir(
            tmp_path / "s1-dir",
            [{
                "timestamp": "2026-05-17T10-00-00",
                "summary": "# clinical sum\n",
                "instruments": {"phq-9": "# phq-9\n"},
            }],
        )
        s2 = _build_study_dir(
            tmp_path / "s2-dir",
            [{
                "timestamp": "2026-05-17T10-00-00",
                "summary": "# personality sum\n",
                "instruments": {"ipip-neo": "# ipip-neo\n"},
            }],
        )
        # rename manifests for distinctness
        m2 = yaml.safe_load(
            (s2.study_dir / "manifest.yaml").read_text(encoding="utf-8")
        )
        m2["study_id"] = "personality-deep-dive"
        (s2.study_dir / "manifest.yaml").write_text(
            yaml.safe_dump(m2, sort_keys=False), encoding="utf-8"
        )

        def latest_paths(study: Study) -> tuple[Path, Path]:
            latest = _latest_run_dir(study)
            assert latest is not None
            (latest / "_analysis.md").write_text("# pass-1\n", encoding="utf-8")
            return latest / "_summary.md", latest / "_analysis.md"

        s1_summary, s1_analysis = latest_paths(s1)
        s2_summary, s2_analysis = latest_paths(s2)
        s2_reloaded = Study.load(s2.study_dir)

        prompt = _build_pass2_user_prompt(
            [(s1, s1_summary, s1_analysis), (s2_reloaded, s2_summary, s2_analysis)]
        )
        assert "2 study/studies" in prompt
        assert "test-baseline" in prompt
        assert "personality-deep-dive" in prompt
        assert "clinical sum" in prompt
        assert "personality sum" in prompt


class TestPersistence:
    def test_pass1_persist_writes_frontmatter_and_body(self, tmp_path: Path) -> None:
        study = _build_study_dir(
            tmp_path, [{"timestamp": "2026-05-17T10-00-00"}]
        )
        run_dir = _latest_run_dir(study)
        result = AnalystResult(
            markdown_body="# Analysis — test-baseline @ 2026-05-17T10-00-00\n\n"
                          "Body line 1\nBody line 2\n",
            elapsed_ms=42_000,
            model_id="claude-haiku-4-5",
            persona_version="abc123",
            prompt_version="def456",
            cost_usd=0.08,
            pass_label="per-study",
        )
        path = _persist_pass1(study, run_dir, result)  # type: ignore[arg-type]
        assert path.name == "_analysis.md"
        assert path.parent == run_dir
        content = path.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        fm_end = content.index("\n---\n")
        fm = yaml.safe_load(content[4:fm_end])
        assert fm["kind"] == "analysis"
        assert fm["pass"] == 1
        assert fm["study_id"] == "test-baseline"
        assert fm["persona_version"] == "abc123"
        assert fm["prompt_version"] == "def456"
        assert fm["model_id"] == "claude-haiku-4-5"
        assert fm["informant_report"] is True
        # Body present
        assert "# Analysis — test-baseline" in content
        assert "Body line 1" in content

    def test_pass2_persist_writes_to_analyses_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Redirect analyses_root to tmp
        monkeypatch.setattr(
            "scripts.analyze._analyses_root",
            lambda: tmp_path / "reports" / "analyses",
        )
        result = AnalystResult(
            markdown_body="# Cross-study analysis — 2026-05-17T11-00-00\n\n"
                          "N=1; body.\n",
            elapsed_ms=15_000,
            model_id="claude-haiku-4-5",
            persona_version="xx",
            prompt_version="yy",
            cost_usd=0.04,
            pass_label="cross-study",
        )
        path = _persist_pass2(result, study_count=1)
        assert path.parent.name == "analyses"
        content = path.read_text(encoding="utf-8")
        fm_end = content.index("\n---\n", 4)
        fm = yaml.safe_load(content[4:fm_end])
        assert fm["kind"] == "cross-study-analysis"
        assert fm["pass"] == 2
        assert fm["study_count"] == 1
        assert "N=1; body" in content
