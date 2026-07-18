"""Type-safe config load/set — `core.config` merge + coerce + YAML fallback.

Covers the three silent-misconfig classes the C05 config-layer pass closed:

  1. `_merge_dataclass` used to assign YAML overrides unvalidated — a wrong
     type (string for an int knob, null for a non-optional) propagated into
     CONFIG and surfaced later as an unrelated crash, or as a knob the
     operator "tuned" that did nothing. Now: WARNING + keep engine default.
  2. `_coerce` used to fall through to the raw string for list/dict targets —
     `wiki config set limits.intent_source_globs foo` overwrote a glob list
     with the string "foo". Now: refused with a clear message.
  3. A YAML parse error used to revert the whole install to factory defaults
     silently. Now: ERROR-logged loudly (last-resort handler → stderr).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from core import config
from core.config_schema import Limits, Personal, PiggybackTask


# ── _merge_dataclass type gate ──────────────────────────────────────────


def test_merge_keeps_default_on_type_mismatch(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger="core.config"):
        merged = config._merge_dataclass(
            Limits(), {"compile_max_turns": "twenty"}, path="limits"
        )
    assert merged.compile_max_turns == Limits().compile_max_turns
    assert any("limits.compile_max_turns" in r.message for r in caplog.records)


def test_merge_keeps_default_on_null_for_non_optional(caplog: pytest.LogCaptureFixture):
    """`compile_max_turns:` with an empty YAML value parses to None — must not
    poison CONFIG with a None int."""
    with caplog.at_level(logging.WARNING, logger="core.config"):
        merged = config._merge_dataclass(Limits(), {"compile_max_turns": None})
    assert merged.compile_max_turns == Limits().compile_max_turns


def test_merge_rejects_bool_for_int_field():
    """YAML `compile_max_turns: true` must not sneak through the bool-is-int trap."""
    merged = config._merge_dataclass(Limits(), {"compile_max_turns": True})
    assert merged.compile_max_turns == Limits().compile_max_turns


def test_merge_accepts_valid_override():
    merged = config._merge_dataclass(Limits(), {"compile_max_turns": 8})
    assert merged.compile_max_turns == 8


def test_merge_accepts_int_for_float_field():
    merged = config._merge_dataclass(Limits(), {"dedup_fuzzy_threshold": 1})
    assert merged.dedup_fuzzy_threshold == 1


def test_merge_accepts_list_for_tuple_field():
    """YAML has no tuple form — a list override satisfies a tuple-typed field."""
    merged = config._merge_dataclass(
        Limits(), {"compile_skip_substrate_types": ["email-delta"]}
    )
    assert list(merged.compile_skip_substrate_types) == ["email-delta"]


def test_merge_accepts_union_forms_for_picture_inbox():
    """`picture_inbox: str | list[str]` — both spellings are legal (2026-05-28
    list-form intake)."""
    as_str = config._merge_dataclass(Personal(), {"picture_inbox": "/inbox"})
    assert as_str.picture_inbox == "/inbox"
    as_list = config._merge_dataclass(Personal(), {"picture_inbox": ["/a", "/b"]})
    assert as_list.picture_inbox == ["/a", "/b"]


def test_merge_accepts_none_for_optional_field():
    merged = config._merge_dataclass(Personal(), {"implicit_operator_author": None})
    assert merged.implicit_operator_author is None
    merged = config._merge_dataclass(Personal(), {"implicit_operator_author": "alex"})
    assert merged.implicit_operator_author == "alex"


def test_merge_piggyback_type_mismatch_keeps_default(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger="core.config"):
        merged = config._merge_piggybacks(
            {"lint_structural": PiggybackTask(cooldown_hours=24)},
            {"lint_structural": {"cooldown_hours": "daily"}},
        )
    assert merged["lint_structural"].cooldown_hours == 24
    assert any(
        "piggybacks.lint_structural.cooldown_hours" in r.message for r in caplog.records
    )


# ── _coerce structured-target refusal ───────────────────────────────────


def test_coerce_refuses_list_target():
    with pytest.raises(ValueError, match="list-valued"):
        config._coerce("foo", ["raw/voice/*"])


def test_coerce_refuses_dict_target():
    with pytest.raises(ValueError, match="dict-valued"):
        config._coerce("foo", {"a": 1})


def test_coerce_refuses_tuple_target():
    with pytest.raises(ValueError, match="tuple-valued"):
        config._coerce("foo", ("email-delta",))


def test_coerce_scalars_still_work():
    assert config._coerce("true", False) is True
    assert config._coerce("7", 1) == 7
    assert config._coerce("0.5", 1.0) == 0.5
    assert config._coerce("text", "hint") == "text"


# ── load() loud fallback ────────────────────────────────────────────────


def test_load_yaml_error_logs_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    broken = tmp_path / "config.yaml"
    broken.write_text("scheduling: [unclosed\n", encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_FILE", broken)
    with caplog.at_level(logging.ERROR, logger="core.config"):
        cfg = config.load()
    assert cfg.scheduling.compile_after_hour == 18  # factory defaults
    assert any("factory defaults" in r.message for r in caplog.records)


def test_load_non_mapping_logs_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    weird = tmp_path / "config.yaml"
    weird.write_text("just a string\n", encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_FILE", weird)
    with caplog.at_level(logging.ERROR, logger="core.config"):
        cfg = config.load()
    assert cfg.limits.compile_max_files == 30
    assert any("factory defaults" in r.message for r in caplog.records)


def test_load_applies_wrong_typed_override_as_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """End-to-end through load(): valid overrides apply, mistyped ones don't."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "limits:\n  compile_max_files: 5\n  compile_max_turns: banana\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_FILE", cfg_file)
    cfg = config.load()
    assert cfg.limits.compile_max_files == 5
    assert cfg.limits.compile_max_turns == Limits().compile_max_turns
