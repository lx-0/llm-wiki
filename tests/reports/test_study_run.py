"""M033-S04-T06 — characterisation of `study.cmd_run` over a tmp studies root with a fake
`_run_one_instrument` (the inference) and the real meta-report: the finalised run dir, the
state bump, the instrument filter, the form-source skip, the deferred retry, the terminal
failure, the lock. Written before the split; manifest / state / lock / RunDirectory are
covered by test_study.py."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pytest
import yaml

import study as study_cli
from reports._engine import study as study_mod

MANIFEST = {
    "study_id": "baseline",
    "title": "Baseline",
    "created": "2026-05-17T00:00:00+00:00",
    "schedule": "weekly",
    "instruments": [
        {"slug": "phq-9", "version": "1.0.0", "source": "inferred"},
        {"slug": "gad-7", "version": "1.0.0", "source": "inferred", "alias": "gad"},
        {"slug": "who-5", "version": "1.0.0", "source": "form"},
    ],
    "notes": "ok",
}
SCORES = {"phq-9": (6, "mild", 9), "gad-7": (4, "minimal", 7)}


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "reports" / "studies"
    sdir = root / "baseline"
    sdir.mkdir(parents=True)
    (sdir / "manifest.yaml").write_text(yaml.safe_dump(MANIFEST, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(study_cli, "_studies_root", lambda: root)
    monkeypatch.setattr(study_mod, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(time, "sleep", lambda s: None)
    return root, sdir


def _install_inference(monkeypatch, *, fail: dict[str, int] | None = None):
    """A fake `_run_one_instrument` writing a timeline-parseable report; `fail` maps an
    alias/slug to how many calls raise before one succeeds (-1 = always)."""
    budget = dict(fail or {})
    calls: list[str] = []

    def _fake(ref, run_dir, study):
        name = ref.alias or ref.slug
        calls.append(name)
        left = budget.get(name, 0)
        if left:
            budget[name] = left - 1 if left > 0 else left
            raise RuntimeError("flaky" if left > 0 else "dead")
        total, band, items = SCORES[ref.slug]
        fm = {
            "instrument": ref.slug,
            "version": ref.version,
            "run_timestamp": run_dir.timestamp,
            "total_score": total,
            "band": band,
            "bandable": True,
            "coverage": {
                "answered_at_high_confidence": items,
                "total_items": items,
                "coverage_pct": 100.0,
                "bandable_threshold": 80.0,
            },
        }
        path = run_dir.instruments_dir / ref.report_filename
        path.write_text(
            "---\n" + yaml.safe_dump(fm, sort_keys=False).strip() + "\n---\n\n# Report body\n",
            encoding="utf-8",
        )
        return path

    monkeypatch.setattr(study_cli, "_run_one_instrument", _fake)
    return calls


def _args(**over) -> argparse.Namespace:
    base = {"study_id": "baseline", "instrument": None, "no_analyze": True}
    base.update(over)
    return argparse.Namespace(**base)


def _final_run(sdir: Path) -> Path:
    runs = [p for p in (sdir / "runs").iterdir() if not p.name.startswith(".")]
    assert len(runs) == 1, runs
    return runs[0]


def test_run_finalises_the_dir_renders_the_meta_report_and_bumps_state(
    env, monkeypatch, capsys
) -> None:
    _root, sdir = env
    calls = _install_inference(monkeypatch)

    rc = study_cli.cmd_run(_args())

    assert rc == 0 and calls == ["phq-9", "gad"]
    run = _final_run(sdir)
    assert sorted(p.name for p in (run / "instruments").iterdir()) == ["gad.md", "phq-9.md"]
    assert (run / "_summary.md").is_file() and (run / "charts" / "radar.svg").is_file()
    assert not (sdir / "runs" / f".{run.name}.tmp").exists()
    state = yaml.safe_load((sdir / "state.yaml").read_text(encoding="utf-8"))
    assert state["run_count"] == 1 and state["last_run_at"]
    out = capsys.readouterr().out
    for needle in (
        f"=== wiki study run baseline @ {run.name} (3 instrument(s)) ===",
        "  - phq-9 v1.0.0: source=inferred; running …",
        "      → instruments/phq-9.md",
        "  - gad v1.0.0: source=inferred; running …",
        "  - who-5 v1.0.0: source=form — skipped (form-source path lands post-wedge)",
        "      → meta-report: _summary.md",
        "✓ Study run complete in ",
        f"2 instrument report(s) in {run}",
        f"state updated: last_run_at={state['last_run_at']} run_count=1",
    ):
        assert needle in out, needle


def test_instrument_filter_narrows_the_run_and_rejects_unknown_aliases(
    env, monkeypatch, capsys
) -> None:
    _root, sdir = env
    calls = _install_inference(monkeypatch)

    assert study_cli.cmd_run(_args(instrument="gad")) == 0
    assert calls == ["gad"]
    assert [p.name for p in (_final_run(sdir) / "instruments").iterdir()] == ["gad.md"]

    assert study_cli.cmd_run(_args(instrument="nope")) == 2
    assert "ERROR: --instrument 'nope' not present in study 'baseline'" in capsys.readouterr().err


def test_missing_or_malformed_study_is_an_error(env, capsys) -> None:
    root, sdir = env

    assert study_cli.cmd_run(_args(study_id="ghost")) == 2
    err = capsys.readouterr().err
    assert f"ERROR: study not found: {root / 'ghost'}" in err
    assert "Available studies: baseline" in err

    (sdir / "manifest.yaml").write_text("schedule: weekly\n", encoding="utf-8")
    assert study_cli.cmd_run(_args()) == 2
    assert "ERROR: failed to load study 'baseline':" in capsys.readouterr().err


def test_deferred_instrument_recovers_on_the_end_of_run_retry(env, monkeypatch, capsys) -> None:
    _root, sdir = env
    calls = _install_inference(monkeypatch, fail={"phq-9": 1})

    rc = study_cli.cmd_run(_args())

    assert rc == 0 and calls == ["phq-9", "gad", "phq-9"]
    run = _final_run(sdir)
    assert sorted(p.name for p in (run / "instruments").iterdir()) == ["gad.md", "phq-9.md"]
    out = capsys.readouterr().out
    for needle in (
        "      ✗ phq-9 failed after retries: RuntimeError: flaky",
        "        queued for end-of-run retry attempt.",
        "→ 1 deferred instrument(s); 60s pause then end-of-run retry pass …",
        "  - phq-9 v1.0.0: deferred retry …",
        "      ✓ recovered → instruments/phq-9.md",
        "2 instrument report(s)",
    ):
        assert needle in out, needle


def test_terminally_failed_instrument_is_reported_and_the_run_still_lands(
    env, monkeypatch, capsys
) -> None:
    _root, sdir = env
    calls = _install_inference(monkeypatch, fail={"gad": -1})

    rc = study_cli.cmd_run(_args())

    assert rc == 0 and calls == ["phq-9", "gad", "gad"]
    run = _final_run(sdir)
    assert [p.name for p in (run / "instruments").iterdir()] == ["phq-9.md"]
    out = capsys.readouterr().out
    assert "      ✗ still failing: RuntimeError: dead" in out
    assert "  1/1 instrument(s) terminally failed: ['gad']" in out
    assert "1 instrument report(s)" in out


def test_a_held_lock_skips_the_run(env, monkeypatch, capsys) -> None:
    _root, sdir = env
    calls = _install_inference(monkeypatch)
    handle = study_mod.acquire_study_lock("baseline")
    assert handle is not None
    try:
        rc = study_cli.cmd_run(_args())
    finally:
        handle.close()

    assert rc == 0 and calls == []
    assert not (sdir / "runs").exists()
    assert (
        "another `wiki study run baseline` is already in progress — skipping. "
        "(Cross-study runs are not blocked.)"
    ) in capsys.readouterr().err
