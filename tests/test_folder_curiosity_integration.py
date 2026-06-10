"""True-chain integration tests for the M027 folder-curiosity pass (S03-T04).

Everything is REAL except the LLM call: a fixture tree on disk is walked by
the S02 collector (`walk_root` → `write_index`), the producer loads that
digest and renders the REAL `prompts/compile_curiosity_folder.md` via the
real `render()`, the emitted request JSON is dispatched through the real
`curiosity/cli._dispatch` into the real backend skeleton. Only
`ollama_client.chat_schema` is mocked (its prompt argument is captured so
the tests can prove the real digest/template flowed in).

Rationale: the T01 unit tests use a hand-written digest + stubbed render —
per the "mocks mask wiring bugs" rule, at least one test per path must run
the critical chain unmocked.
"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest

import collectors.folder_index as folder_index
import curiosity.cli as cli
import curiosity.producer as producer
from core.config import CONFIG

GAP = {
    "topic": "Steuerbescheid 2024",
    "root_id": "docs",
    "file_path": "11 Steuern/Steuerbescheid-2024.pdf",
    "file_confidence": 5,
    "rationale": "Filename names the tax assessment exactly.",
}


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """Fixture tree + REAL walked/written digest + source note."""
    trove = tmp_path / "trove"
    (trove / "11 Steuern").mkdir(parents=True)
    (trove / "11 Steuern" / "Steuerbescheid-2024.pdf").write_text(
        "x", encoding="utf-8"
    )
    (trove / "ümlaut notizen.md").write_text("u", encoding="utf-8")
    (trove / "decoy.txt").write_text("d", encoding="utf-8")

    monkeypatch.setattr(folder_index, "INDEX_DIR", tmp_path / "raw" / "index")
    monkeypatch.setattr(
        folder_index, "STATE_FILE", tmp_path / "state" / "folder-index.json"
    )
    monkeypatch.setattr(producer, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(producer, "RAW_REQUESTS_DIR", tmp_path / "raw" / "requests")
    monkeypatch.setattr(producer, "RAW_INDEX_DIR", tmp_path / "raw" / "index")

    entry = {"id": "docs", "kind": "local", "path": str(trove)}
    monkeypatch.setattr(CONFIG.personal, "watched_folders", [entry])
    monkeypatch.setattr(CONFIG.features, "curiosity_loop", True)
    monkeypatch.setattr(CONFIG.limits, "curiosity_min_source_chars", 10)
    monkeypatch.setattr(CONFIG.limits, "curiosity_source_globs", [])
    monkeypatch.setattr(CONFIG.limits, "curiosity_folder_confidence_min", 4)
    monkeypatch.setattr(producer.ollama_client, "is_reachable", lambda: True)

    # REAL S02 chain — walk the fixture tree and write the digest.
    idx = folder_index.walk_root(entry, max_depth=0, recent_n=5)
    folder_index.write_index(idx)

    src = tmp_path / "raw" / "notes" / "note.md"
    src.parent.mkdir(parents=True)
    src.write_text(
        "Operator hat offene Rückfragen zum Steuerbescheid 2024 notiert.",
        encoding="utf-8",
    )
    return tmp_path, trove, src


def _run_with_gaps(monkeypatch, src, gaps):
    captured = {}

    def _fake_chat_schema(prompt, *, model, schema, timeout):
        captured["prompt"] = prompt
        return json.dumps({"gaps": gaps})

    monkeypatch.setattr(producer.ollama_client, "chat_schema", _fake_chat_schema)
    asyncio.run(producer.maybe_generate_folder_requests(src))
    return captured


def _requests(root):
    d = root / "raw" / "requests"
    return sorted(d.glob("request-*.json")) if d.exists() else []


def test_happy_chain_walk_index_produce_request(vault, monkeypatch):
    root, _, src = vault
    captured = _run_with_gaps(monkeypatch, src, [GAP])

    # the REAL digest flowed into the REAL template
    assert "11 Steuern/Steuerbescheid-2024.pdf" in captured["prompt"]
    assert "You see metadata only" in captured["prompt"]  # template marker

    reqs = _requests(root)
    assert len(reqs) == 1
    body = json.loads(reqs[0].read_text(encoding="utf-8"))
    assert body["type"] == "folder-deep-scan"
    assert body["root_id"] == "docs"
    assert body["file_path"] == "11 Steuern/Steuerbescheid-2024.pdf"
    assert body["status"] == "pending"


def test_anchor_rejects_unwalked_path_over_real_digest(vault, monkeypatch):
    root, _, src = vault
    captured = _run_with_gaps(
        monkeypatch, src,
        [dict(GAP, file_path="11 Steuern/plausibel-aber-erfunden.pdf")],
    )
    assert "prompt" in captured  # producer really ran — gate, not no-op
    assert _requests(root) == []


def test_confidence_gate_over_real_chain(vault, monkeypatch):
    root, _, src = vault
    captured = _run_with_gaps(monkeypatch, src, [dict(GAP, file_confidence=3)])
    assert "prompt" in captured  # producer really ran (threshold is 4)
    assert _requests(root) == []


def test_answer_artifact_is_compile_candidate_and_routes_like_email(
    tmp_path, monkeypatch
):
    """S05-T01 pins: a persisted folder answer (a) appears in compile's
    candidate list (`list_raw_files` walks raw/) and (b) routes through
    the SAME dispatch lane as the proven email deep-scans — parity-
    asserted, so a future dedicated `note` dispatch forces a conscious
    folder decision."""
    from curiosity.backends import folder as fb
    from curiosity.backends.folder_providers import ScanAnswer

    # persist a real answer via the real backend (provider stubbed)
    trove = tmp_path / "trove" / "11 Steuern"
    trove.mkdir(parents=True)
    (trove / "Steuerbescheid-2024.pdf").write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        CONFIG.personal,
        "watched_folders",
        [{"id": "docs", "kind": "local", "path": str(tmp_path / "trove")}],
    )
    monkeypatch.setattr(fb, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(fb, "ANSWER_DIR", tmp_path / "raw" / "notes" / "folder")

    class _Stub:
        async def answer(self, *, topic, rationale, file_abs, file_rel):
            return ScanAnswer(
                answer_md="## Answer\n\ndistilled",
                file_path=file_rel,
                as_of_mtime=file_abs.stat().st_mtime,
            )

    monkeypatch.setattr(fb, "get_provider", lambda: _Stub())
    request_path = tmp_path / "request-steuer-2026-06-10.json"
    request_path.write_text(
        json.dumps({
            "type": "folder-deep-scan", "status": "pending",
            "root_id": "docs",
            "file_path": "11 Steuern/Steuerbescheid-2024.pdf",
            "file_confidence": 5, "topic": "Steuerbescheid 2024",
            "rationale": "r", "source": "raw/notes/note.md",
            "created": "2026-06-10T20:00:00+00:00",
        }, indent=2),
        encoding="utf-8",
    )
    assert fb.process_request(request_path, dry_run=False).success is True
    answer_path = tmp_path / "raw" / "notes" / "folder" / "answer-steuer-2026-06-10.md"
    assert answer_path.exists()

    # (a) selection pin — compile's walker lists the artifact
    import core.utils as cu

    monkeypatch.setattr(cu, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(cu, "DAILY_DIR", tmp_path / "daily")
    assert answer_path in cu.list_raw_files()

    # (b) routing-parity pin — same lane as email deep-scans
    from pathlib import Path as P

    from compile_stages.route import Compile, decide_route

    answer_route = decide_route(
        P("raw/notes/folder") / answer_path.name,
        answer_path.read_text(encoding="utf-8"),
    )
    email_route = decide_route(
        P("raw/notes/email/deep-projectx-2026-06-10.md"),
        "---\ntype: note\nkind: email-deep-scan\ntopic: \"x\"\n---\n\nbody",
    )
    assert isinstance(answer_route, Compile)
    assert isinstance(email_route, Compile)
    assert (
        answer_route.metadata.substrate_prompt
        == email_route.metadata.substrate_prompt
    )
    assert answer_route.metadata.model_id == email_route.metadata.model_id


def test_e2e_dispatch_dry_run_and_stale_file_branch(vault, monkeypatch, caplog):
    root, trove, src = vault
    _run_with_gaps(monkeypatch, src, [GAP])
    request_path = _requests(root)[0]

    with caplog.at_level(logging.INFO, logger="curiosity"):
        assert cli._dispatch(request_path, dry_run=True) is True
    assert "exists" in caplog.text

    # stale index: the file vanished after indexing — dry-run still works
    # but surfaces the staleness signal
    (trove / "11 Steuern" / "Steuerbescheid-2024.pdf").unlink()
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="curiosity"):
        assert cli._dispatch(request_path, dry_run=True) is True
    assert "MISSING" in caplog.text
