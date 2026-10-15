"""M033-S04-T06 — characterisation of `reports._engine.runner.run_inference` with a fake
`infer_batch` and a fixed substrate scope over the real phq-9 instrument: the report
placement, the per-batch prompt + its hashed version, operator answers excluded from the
prompt and winning at scoring, the all-answered no-SDK path. Written before the split;
`_persist_report` is covered by test_runner_report.py."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
import yaml

from core import frontmatter
from reports._engine import runner
from reports._engine.instrument import load_instrument
from reports._engine.lib.inference import BatchResult, ItemInference

INSTRUMENTS_ROOT = (
    Path(__file__).resolve().parents[2] / "scripts" / "reports" / "_engine" / "instruments"
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    day = vault / "daily" / "2026-10-14.md"
    day.parent.mkdir(parents=True)
    day.write_text("# day\n\nslept badly, low energy\n", encoding="utf-8")
    monkeypatch.setattr(runner, "resolve_substrate_files", lambda root, globs, days: [day])
    calls: list[dict] = []

    def _fake_infer_batch(rendered_prompt, batch, *, vault_cwd, prompt_version, **kw):
        calls.append(
            {
                "prompt": rendered_prompt,
                "batch": batch,
                "vault_cwd": vault_cwd,
                "prompt_version": prompt_version,
                **kw,
            }
        )
        items = {
            it.id: ItemInference(
                item_id=it.id, answer=1, confidence=0.9, evidence=[], reasoning="seen"
            )
            for it in batch.items
        }
        return BatchResult(
            items=items,
            elapsed_ms=5,
            model_id=kw.get("model", "fake-model"),
            prompt_version=prompt_version,
            cost_usd=0.01,
            batch_label=batch.label,
        )

    monkeypatch.setattr(runner, "infer_batch", _fake_infer_batch)
    return vault, calls


def _fm(report: Path) -> dict:
    return frontmatter.parse_strict(report.read_text(encoding="utf-8"))[0]


def _write_answers(study_dir: Path, answers: dict[str, int]) -> None:
    study_dir.mkdir(parents=True, exist_ok=True)
    (study_dir / "operator_answers.yaml").write_text(
        yaml.safe_dump(
            {
                "phq-9": {
                    item: {"value": value, "answered_at": "2026-10-15T09:00:00+00:00"}
                    for item, value in answers.items()
                }
            }
        ),
        encoding="utf-8",
    )


def test_single_batch_report_lands_in_the_output_dir(env, capsys) -> None:
    vault, calls = env

    report = runner.run_inference("phq-9", "1.0.0", vault, output_dir=vault / "out")

    assert report == vault / "out" / "phq-9.md"
    [call] = calls
    assert call["batch"].label == "all" and len(call["batch"].items) == 9
    assert call["vault_cwd"] == vault
    expected_model = load_instrument(INSTRUMENTS_ROOT / "phq-9" / "v1.0.0").meta.inference.model
    assert call.get("model") == (expected_model or None)
    fm = _fm(report)
    assert fm["instrument"] == "phq-9" and fm["run_kind"] == "ad-hoc"
    assert fm["total_score"] == 9 and fm["coverage"]["coverage_pct"] == 100.0
    assert fm["prompt_version"] == hashlib.sha256(call["prompt"].encode("utf-8")).hexdigest()[:16]
    assert fm["prompt_version"] == call["prompt_version"]
    assert fm["model_id"] == (expected_model or "fake-model") and fm["cost_usd"] == 0.01
    assert fm["scope"]["file_count"] == 1 and fm["scope"]["lookback_days"] == 14
    text = report.read_text(encoding="utf-8")
    assert "Batch `all`" in text and call["prompt"] in text
    assert "- `daily/2026-10-14.md`" in text
    out = capsys.readouterr().out
    for needle in (
        "Loading instrument:",
        "slug=phq-9 v1.0.0  items=9",
        "1 files matched.",
        "batches: 1 (all)",
        "batch=all  prompt_chars=",
        "→ answered=9/9  cost=$0.0100",
        "Score: total=9  band=mild  coverage=100.0%  bandable=True",
        f"Report persisted: {report}",
    ):
        assert needle in out, needle


def test_operator_answers_leave_the_prompt_and_win_at_scoring(env, capsys) -> None:
    vault, calls = env
    study_dir = vault / "reports" / "studies" / "baseline"
    _write_answers(study_dir, {"9": 3, "1": 0})

    report = runner.run_inference(
        "phq-9", "1.0.0", vault, output_dir=vault / "out", study_dir=study_dir
    )

    [call] = calls
    assert [it.id for it in call["batch"].items] == ["2", "3", "4", "5", "6", "7", "8"]
    assert "**9**" not in call["prompt"] and "**1**" not in call["prompt"]
    assert "**2**" in call["prompt"]
    assert _fm(report)["total_score"] == 7 + 3 + 0
    out = capsys.readouterr().out
    assert "operator-supplied answers: 2 item(s) — ['1', '9'] (excluded from inference)" in out


def test_all_items_operator_answered_skips_the_sdk(env, capsys) -> None:
    vault, calls = env
    study_dir = vault / "reports" / "studies" / "baseline"
    _write_answers(study_dir, {str(i): 2 for i in range(1, 10)})

    report = runner.run_inference(
        "phq-9", "1.0.0", vault, output_dir=vault / "out", study_dir=study_dir
    )

    assert calls == []
    fm = _fm(report)
    assert fm["total_score"] == 18 and fm["prompt_version"] == "" and fm["model_id"] == ""
    assert "no SDK call this run" in report.read_text(encoding="utf-8")
    assert "all items operator-answered — skipping SDK call entirely." in capsys.readouterr().out


def test_default_output_dir_is_the_adhoc_timestamp_dir(env) -> None:
    vault, _calls = env

    report = runner.run_inference("phq-9", "1.0.0", vault)

    assert report.name == "phq-9.md" and report.parent.parent == vault / "reports" / "_adhoc"
    assert len(report.parent.name) == len("2026-10-15T12-00-00")


def test_instrument_model_override_reaches_the_sdk(env) -> None:
    vault, calls = env

    report = runner.run_inference("isi", "1.0.0", vault, output_dir=vault / "out")

    assert [c.get("model") for c in calls] == ["claude-sonnet-4-6"] * len(calls)
    assert _fm(report)["model_id"] == "claude-sonnet-4-6"


def test_missing_instrument_raises_before_any_work(env) -> None:
    vault, calls = env

    with pytest.raises(FileNotFoundError, match="Instrument not found"):
        runner.run_inference("nope", "1.0.0", vault)
    assert calls == []


def test_main_wraps_run_inference(env, monkeypatch, capsys) -> None:
    vault, _calls = env
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner",
            "--vault",
            str(vault),
            "--instrument",
            "phq-9",
            "--output-dir",
            str(vault / "o"),
        ],
    )

    assert runner.main() == 0
    assert (vault / "o" / "phq-9.md").is_file()

    monkeypatch.setattr(sys, "argv", ["runner", "--vault", str(vault), "--instrument", "nope"])
    assert runner.main() == 1
    assert "ERROR: Instrument not found" in capsys.readouterr().err
