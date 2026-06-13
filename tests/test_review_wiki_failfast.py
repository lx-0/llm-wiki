"""review-wiki classifies failures so the sweep can fail-fast on a down kcma
(error_kind=ollama) without aborting on mere unparseable model output
(error_kind=parse). This classification is what the consecutive-failure abort
counts on."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def _load_review_module():
    path = Path(__file__).resolve().parent.parent / "scripts" / "review-wiki.py"
    spec = importlib.util.spec_from_file_location("review_wiki_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _article(tmp_path):
    art = tmp_path / "a.md"
    art.write_text("# A\nsome body words here", encoding="utf-8")
    return art


def test_transport_failure_is_ollama_kind(tmp_path, monkeypatch):
    import httpx
    mod = _load_review_module()
    monkeypatch.setattr(mod, "KNOWLEDGE_DIR", tmp_path)
    monkeypatch.setattr(mod, "render", lambda *a, **k: "PROMPT")
    monkeypatch.setattr(mod.ollama_client, "chat",
                        lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    r = mod.review_article(_article(tmp_path), "m")
    assert r["error_kind"] == "ollama"   # counts toward fail-fast abort


def test_unparseable_output_is_parse_kind(tmp_path, monkeypatch):
    mod = _load_review_module()
    monkeypatch.setattr(mod, "KNOWLEDGE_DIR", tmp_path)
    monkeypatch.setattr(mod, "render", lambda *a, **k: "PROMPT")
    monkeypatch.setattr(mod.ollama_client, "chat", lambda *a, **k: "not json at all")
    r = mod.review_article(_article(tmp_path), "m")
    assert r["error_kind"] == "parse"   # kcma is UP — must NOT trip fail-fast


def test_success_has_no_error(tmp_path, monkeypatch):
    mod = _load_review_module()
    monkeypatch.setattr(mod, "KNOWLEDGE_DIR", tmp_path)
    monkeypatch.setattr(mod, "render", lambda *a, **k: "PROMPT")
    monkeypatch.setattr(mod.ollama_client, "chat",
                        lambda *a, **k: '{"overall": 4, "verdict": "keep"}')
    r = mod.review_article(_article(tmp_path), "m")
    assert "error" not in r and r["overall"] == 4 and r["article"] == "a.md"


def test_sweep_deadline_capped_below_hard_kill():
    """The soft sweep deadline always fires before the piggyback hard wall-clock
    cap, so a slow-but-alive sweep writes its partial and exits clean instead of
    being killed (false `timeout`). Uses the soft knob, but never more than
    0.9× the hard cap."""
    mod = _load_review_module()
    # soft knob below the hard cap → use the knob as-is
    assert mod._sweep_deadline_s(review_max=12600, piggyback_max=14400) == 12600
    # hard cap lowered below the knob → deadline drops to 0.9× the hard cap
    assert mod._sweep_deadline_s(review_max=12600, piggyback_max=10000) == 9000
