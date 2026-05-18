"""Tests for `scripts/reports/_engine/study.py` — manifest schema +
state + is_due + fork + RunDirectory + flock."""

from __future__ import annotations

import multiprocessing
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from scripts.reports._engine.study import (
    InstrumentRef,
    RunDirectory,
    Study,
    StudyManifest,
    StudyState,
    acquire_study_lock,
    fork_study,
    list_studies,
)


VALID_MANIFEST = {
    "study_id": "test-study",
    "title": "Test study",
    "created": "2026-05-17T00:00:00+00:00",
    "schedule": "weekly",
    "instruments": [
        {"slug": "phq-9", "version": "1.0.0", "source": "inferred"},
        {"slug": "gad-7", "version": "1.0.0", "source": "inferred"},
    ],
    "notes": "ok",
}


class TestInstrumentRef:
    def test_minimal_load(self) -> None:
        ref = InstrumentRef.from_dict({"slug": "phq-9", "version": "1.0.0"})
        assert ref.slug == "phq-9"
        assert ref.version == "1.0.0"
        assert ref.source == "inferred"
        assert ref.alias is None

    def test_with_alias(self) -> None:
        ref = InstrumentRef.from_dict(
            {"slug": "phq-9", "version": "1.0.0", "source": "form", "alias": "phq-9-self"}
        )
        assert ref.alias == "phq-9-self"
        assert ref.source == "form"

    def test_missing_slug_rejected(self) -> None:
        with pytest.raises(ValueError):
            InstrumentRef.from_dict({"version": "1.0.0"})

    def test_invalid_source_rejected(self) -> None:
        with pytest.raises(ValueError):
            InstrumentRef.from_dict({"slug": "x", "version": "1.0.0", "source": "magic"})

    def test_report_filename_uses_alias_if_set(self) -> None:
        ref = InstrumentRef.from_dict(
            {"slug": "phq-9", "version": "1.0.0", "alias": "phq-9-self"}
        )
        assert ref.report_filename == "phq-9-self.md"

    def test_report_filename_falls_back_to_slug(self) -> None:
        ref = InstrumentRef.from_dict({"slug": "phq-9", "version": "1.0.0"})
        assert ref.report_filename == "phq-9.md"


class TestStudyManifest:
    def test_good_manifest_loads(self) -> None:
        m = StudyManifest.from_dict(VALID_MANIFEST)
        assert m.study_id == "test-study"
        assert m.schedule == "weekly"
        assert len(m.instruments) == 2

    def test_invalid_schedule_rejected(self) -> None:
        bad = dict(VALID_MANIFEST, schedule="annual")
        with pytest.raises(ValueError):
            StudyManifest.from_dict(bad)

    def test_missing_required_field_rejected(self) -> None:
        bad = {k: v for k, v in VALID_MANIFEST.items() if k != "schedule"}
        with pytest.raises(ValueError, match="schedule"):
            StudyManifest.from_dict(bad)

    def test_bad_slug_rejected(self) -> None:
        for bad in ("X", "ab", "-leading", "trailing-", "with space", "with_underscore"):
            with pytest.raises(ValueError):
                StudyManifest.from_dict(dict(VALID_MANIFEST, study_id=bad))

    def test_empty_instruments_rejected(self) -> None:
        with pytest.raises(ValueError):
            StudyManifest.from_dict(dict(VALID_MANIFEST, instruments=[]))

    def test_duplicate_alias_rejected(self) -> None:
        bad = dict(
            VALID_MANIFEST,
            instruments=[
                {"slug": "phq-9", "version": "1.0.0"},
                {"slug": "phq-9", "version": "1.0.0"},
            ],
        )
        with pytest.raises(ValueError, match="duplicate aliases"):
            StudyManifest.from_dict(bad)

    def test_distinct_aliases_for_same_slug_allowed(self) -> None:
        """source=both pattern: two refs to same instrument with distinct aliases."""
        ok = dict(
            VALID_MANIFEST,
            instruments=[
                {"slug": "phq-9", "version": "1.0.0", "source": "inferred",
                 "alias": "phq-9-inf"},
                {"slug": "phq-9", "version": "1.0.0", "source": "form",
                 "alias": "phq-9-self"},
            ],
        )
        m = StudyManifest.from_dict(ok)
        assert len(m.instruments) == 2

    def test_round_trip_yaml(self) -> None:
        m1 = StudyManifest.from_dict(VALID_MANIFEST)
        as_yaml = yaml.safe_dump(m1.to_dict(), sort_keys=False)
        m2 = StudyManifest.from_dict(yaml.safe_load(as_yaml))
        assert m1 == m2


class TestStudyState:
    def test_load_missing_file_returns_blank(self, tmp_path: Path) -> None:
        state = StudyState.load(tmp_path / "state.yaml")
        assert state.last_run_at is None
        assert state.run_count == 0

    def test_write_and_reload(self, tmp_path: Path) -> None:
        s = StudyState(last_run_at="2026-05-17T10:00:00+00:00", run_count=3)
        path = tmp_path / "state.yaml"
        s.write(path)
        loaded = StudyState.load(path)
        assert loaded.last_run_at == "2026-05-17T10:00:00+00:00"
        assert loaded.run_count == 3

    def test_mark_run_bumps_count_and_sets_timestamp(self) -> None:
        s = StudyState()
        when = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
        s.mark_run(when)
        assert s.run_count == 1
        assert "2026-05-17T12:00:00" in s.last_run_at  # type: ignore[arg-type]


class TestIsDue:
    def _make(self, schedule: str, last: str | None) -> Study:
        manifest = StudyManifest.from_dict(dict(VALID_MANIFEST, schedule=schedule))
        state = StudyState(last_run_at=last)
        return Study(manifest=manifest, state=state, study_dir=Path("/tmp/unused"))

    def test_manual_never_due(self) -> None:
        s = self._make("manual", last=None)
        assert s.is_due() is False

    def test_weekly_never_run_is_due(self) -> None:
        s = self._make("weekly", last=None)
        assert s.is_due() is True

    def test_weekly_recent_run_not_due(self) -> None:
        recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        s = self._make("weekly", last=recent)
        assert s.is_due() is False

    def test_weekly_8_days_ago_is_due(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        s = self._make("weekly", last=old)
        assert s.is_due() is True

    def test_quarterly_60_days_not_due(self) -> None:
        recent = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        s = self._make("quarterly", last=recent)
        assert s.is_due() is False

    def test_quarterly_100_days_is_due(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        s = self._make("quarterly", last=old)
        assert s.is_due() is True

    def test_malformed_last_run_falls_back_to_due(self) -> None:
        s = self._make("weekly", last="not-an-iso-date")
        assert s.is_due() is True


class TestForkStudy:
    def _build_source(self, root: Path) -> Study:
        src_dir = root / "source-study"
        src_dir.mkdir()
        (src_dir / "manifest.yaml").write_text(
            yaml.safe_dump(VALID_MANIFEST, sort_keys=False), encoding="utf-8"
        )
        return Study.load(src_dir)

    def test_fork_creates_new_manifest(self, tmp_path: Path) -> None:
        src = self._build_source(tmp_path)
        new_dir = fork_study(src, "child-study", tmp_path)
        assert (new_dir / "manifest.yaml").is_file()
        forked = StudyManifest.from_path(new_dir / "manifest.yaml")
        assert forked.study_id == "child-study"
        assert len(forked.instruments) == len(src.manifest.instruments)
        assert forked.schedule == src.manifest.schedule
        assert "(fork)" in forked.title
        # Fresh state — no inherited runs.
        forked_study = Study.load(new_dir)
        assert forked_study.state.last_run_at is None
        assert forked_study.state.run_count == 0

    def test_fork_collides_on_existing_id(self, tmp_path: Path) -> None:
        src = self._build_source(tmp_path)
        fork_study(src, "child-study", tmp_path)
        with pytest.raises(FileExistsError):
            fork_study(src, "child-study", tmp_path)

    def test_fork_rejects_bad_slug(self, tmp_path: Path) -> None:
        src = self._build_source(tmp_path)
        with pytest.raises(ValueError):
            fork_study(src, "BAD UPPERCASE", tmp_path)


class TestRunDirectory:
    def test_happy_path_atomic_commit(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        with RunDirectory(runs, "2026-05-17T15-30-04") as rd:
            rd.write("instruments/phq-9.md", "# phq-9 content\n")
            rd.write("_summary.md", "# summary\n")
        # After exit (no exception), final dir exists, tmp dir gone.
        assert rd.final_dir.is_dir()
        assert not rd.tmp_dir.exists()
        assert (rd.final_dir / "instruments" / "phq-9.md").read_text() == "# phq-9 content\n"

    def test_exception_leaves_tmp_dir_no_final(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        rd = RunDirectory(runs, "2026-05-17T16-00-00")
        with pytest.raises(RuntimeError):
            with rd:
                rd.write("instruments/phq-9.md", "# partial\n")
                raise RuntimeError("simulated crash")
        # tmp_dir remains for forensics; final dir does NOT exist.
        assert rd.tmp_dir.is_dir()
        assert not rd.final_dir.exists()

    def test_collision_with_existing_final_raises(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        # Pre-create the final dir to provoke collision.
        runs.mkdir()
        (runs / "2026-05-17T17-00-00").mkdir()
        with pytest.raises(FileExistsError):
            with RunDirectory(runs, "2026-05-17T17-00-00") as rd:
                rd.write("_summary.md", "x")

    def test_stale_tmp_cleaned_on_enter(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        runs.mkdir()
        stale = runs / ".2026-05-17T18-00-00.tmp"
        stale.mkdir()
        (stale / "leftover.md").write_text("old", encoding="utf-8")
        with RunDirectory(runs, "2026-05-17T18-00-00") as rd:
            assert rd.tmp_dir.is_dir()
            # leftover removed during enter
            assert not (rd.tmp_dir / "leftover.md").exists()
            rd.write("_summary.md", "fresh")
        assert rd.final_dir.is_dir()


def _hold_lock_subprocess(
    study_id: str, hold_seconds: float, signal_path: str, state_dir_str: str
) -> None:
    """Helper: take a lock, signal we got it, hold for N seconds.

    Subprocess (`spawn` on macOS) doesn't inherit the parent's monkeypatched
    module attrs, so we redirect STATE_DIR here too before acquiring.
    """
    from scripts.reports._engine import study as study_mod

    study_mod.STATE_DIR = Path(state_dir_str)
    lock = acquire_study_lock(study_id)
    if lock is None:
        Path(signal_path).write_text("failed-to-acquire", encoding="utf-8")
        return
    Path(signal_path).write_text("locked", encoding="utf-8")
    time.sleep(hold_seconds)
    lock.close()


class TestStudyLock:
    @pytest.fixture(autouse=True)
    def _isolated_state_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Redirect STATE_DIR so lock files land in tmp_path, not engine state/."""
        from scripts.reports._engine import study as study_mod

        monkeypatch.setattr(study_mod, "STATE_DIR", tmp_path)
        return tmp_path

    def test_acquire_returns_handle(self) -> None:
        lock = acquire_study_lock("test-lock-basic")
        assert lock is not None
        lock.close()

    def test_concurrent_acquire_blocked(self, tmp_path: Path) -> None:
        signal = tmp_path / "signal.txt"
        # Spawn a subprocess that takes the lock and holds for 2s.
        proc = multiprocessing.Process(
            target=_hold_lock_subprocess,
            args=("test-lock-concurrent", 2.0, str(signal), str(tmp_path)),
        )
        proc.start()
        # Wait for the child to acquire.
        for _ in range(50):
            if signal.exists() and signal.read_text() == "locked":
                break
            time.sleep(0.05)
        assert signal.read_text() == "locked"
        # Now try to acquire ourselves — should fail.
        my_lock = acquire_study_lock("test-lock-concurrent")
        assert my_lock is None
        proc.join(timeout=5.0)
        # After the child released, we can take it.
        my_lock = acquire_study_lock("test-lock-concurrent")
        assert my_lock is not None
        my_lock.close()

    def test_lock_rejects_bad_slug(self) -> None:
        with pytest.raises(ValueError):
            acquire_study_lock("BAD UPPERCASE")


class TestListStudies:
    def test_empty_returns_empty(self, tmp_path: Path) -> None:
        assert list_studies(tmp_path / "studies") == []

    def test_skips_dirs_without_manifest(self, tmp_path: Path) -> None:
        (tmp_path / "no-manifest").mkdir()
        assert list_studies(tmp_path) == []

    def test_returns_loaded_studies(self, tmp_path: Path) -> None:
        for sid in ("alpha-study", "beta-study"):
            d = tmp_path / sid
            d.mkdir()
            (d / "manifest.yaml").write_text(
                yaml.safe_dump(
                    dict(VALID_MANIFEST, study_id=sid),
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
        loaded = list_studies(tmp_path)
        assert len(loaded) == 2
        assert [s.manifest.study_id for s in loaded] == ["alpha-study", "beta-study"]

    def test_skips_malformed_manifest(self, tmp_path: Path) -> None:
        bad = tmp_path / "broken"
        bad.mkdir()
        (bad / "manifest.yaml").write_text("not: a: valid: manifest", encoding="utf-8")
        # Should not raise; just silently skips.
        loaded = list_studies(tmp_path)
        assert loaded == []
