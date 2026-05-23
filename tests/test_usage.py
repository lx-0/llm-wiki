"""Token-usage ledger (core/usage.py). Pure, deterministic, no LLM/provider calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def test_provider_for_model():
    from core import usage
    assert usage.provider_for_model("claude-opus-4-7") == "claude"
    assert usage.provider_for_model("claude-opus-4-7[1m]") == "claude"
    assert usage.provider_for_model("anthropic/claude-x") == "claude"
    assert usage.provider_for_model("gemma4:e4b") == "ollama"
    assert usage.provider_for_model("llama3.1:8b") == "ollama"
    assert usage.provider_for_model("") == "ollama"  # unknown -> local default


def test_record_groups_by_provider_model_and_counts_calls():
    from core import usage
    L = usage.UsageLedger()
    L.record(model="claude-opus-4-7", input_tokens=100, output_tokens=20)
    L.record(model="claude-opus-4-7", input_tokens=50, output_tokens=10)
    L.record(model="gemma4:e4b", input_tokens=5, output_tokens=5)
    t = L.totals()
    assert t[("claude", "claude-opus-4-7")].input_tokens == 150
    assert t[("claude", "claude-opus-4-7")].output_tokens == 30
    assert t[("claude", "claude-opus-4-7")].calls == 2
    assert t[("claude", "claude-opus-4-7")].total_tokens == 180
    assert t[("ollama", "gemma4:e4b")].total_tokens == 10


def test_record_ollama_and_openai_usage_shapes():
    from core import usage
    L = usage.UsageLedger()
    L.record_ollama("gemma4:e4b", {"prompt_eval_count": 12, "eval_count": 7})
    L.record_openai_usage("llama3.1:8b", {"prompt_tokens": 3, "completion_tokens": 4})
    L.record_ollama("gemma4:e4b", {})  # missing fields -> 0, no crash
    t = L.totals()
    assert t[("ollama", "gemma4:e4b")].input_tokens == 12
    assert t[("ollama", "gemma4:e4b")].output_tokens == 7
    assert t[("ollama", "gemma4:e4b")].calls == 2
    assert t[("ollama", "llama3.1:8b")].input_tokens == 3
    assert t[("ollama", "llama3.1:8b")].output_tokens == 4


def test_persist_merges_under_date_bucket(tmp_path):
    from core import usage
    p = tmp_path / "usage.json"
    L = usage.UsageLedger()
    L.record(model="claude-opus-4-7", input_tokens=100, output_tokens=20)
    L.persist(p, day="2026-05-23")
    L2 = usage.UsageLedger()
    L2.record(model="claude-opus-4-7", input_tokens=5, output_tokens=1)
    L2.record(model="gemma4:e4b", input_tokens=9, output_tokens=2)
    L2.persist(p, day="2026-05-23")
    data = json.loads(p.read_text(encoding="utf-8"))
    bucket = data["2026-05-23"]
    assert bucket["claude:claude-opus-4-7"]["input_tokens"] == 105
    assert bucket["claude:claude-opus-4-7"]["output_tokens"] == 21
    assert bucket["claude:claude-opus-4-7"]["calls"] == 2
    assert bucket["ollama:gemma4:e4b"]["output_tokens"] == 2


def test_persist_separate_days_dont_merge(tmp_path):
    from core import usage
    p = tmp_path / "usage.json"
    a = usage.UsageLedger(); a.record(model="claude-opus-4-7", input_tokens=1); a.persist(p, day="2026-05-22")
    b = usage.UsageLedger(); b.record(model="claude-opus-4-7", input_tokens=2); b.persist(p, day="2026-05-23")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert set(data.keys()) == {"2026-05-22", "2026-05-23"}


def test_persist_empty_is_noop(tmp_path):
    from core import usage
    p = tmp_path / "usage.json"
    usage.UsageLedger().persist(p, day="2026-05-23")
    assert not p.exists()


def test_summary_line():
    from core import usage
    L = usage.UsageLedger()
    assert L.summary_line() == "usage: (none)"
    L.record(model="claude-opus-4-7", input_tokens=1500, output_tokens=300)
    s = L.summary_line()
    assert "claude/claude-opus-4-7" in s and "1.5K in" in s and "300 out" in s
