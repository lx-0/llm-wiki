"""Tests for the folder-curiosity producer (curiosity/producer.py).

M027-S03-T01: `maybe_generate_folder_requests` is the sibling of the email
pass — it injects the body-blind folder-index digests in-context (with a
consumer-side budget trim, DECISIONS 2026-06-10), asks the local LLM for
knowledge gaps a watched-folder file could answer, and writes
`folder-deep-scan` request JSONs. The anti-hallucination gate is a
FILE-EXISTS anchor (the named path must be present in the current index)
instead of email's `source_quote` — the index IS what the model saw.

All LLM traffic is mocked (`ollama_client.chat_schema`); the prompt template
ships in T02, so `render` is stubbed too.
"""

from __future__ import annotations

import asyncio
import json

import pytest

import curiosity.producer as producer
from core.config import CONFIG

DIGEST = """---
type: folder-index
root_id: docs
root_path: "/troves/docs"
generated_at: "2026-06-10T12:00:00+00:00"
files: 2
dirs: 1
skipped_excluded: 0
skipped_depth: 0
errors: 0
---

# Folder index — docs

**Root:** `/troves/docs` · 2 files · 1 dirs · 0 errors

## Recent changes

- `11 Steuern/Steuerbescheid-2024.pdf` — 2026-06-01 · 1.2 KB

## Tree

- `11 Steuern`/
  - `11 Steuern/Steuerbescheid-2024.pdf` · 1.2 KB
- `vertrag-handy.pdf` · 3.4 KB
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated vault root with one source note + one digest."""
    monkeypatch.setattr(producer, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(producer, "RAW_REQUESTS_DIR", tmp_path / "raw" / "requests")
    monkeypatch.setattr(producer, "RAW_INDEX_DIR", tmp_path / "raw" / "index")
    monkeypatch.setattr(CONFIG.features, "curiosity_loop", True)
    monkeypatch.setattr(
        CONFIG.personal,
        "watched_folders",
        [{"id": "docs", "kind": "local", "path": "/troves/docs"}],
    )
    monkeypatch.setattr(CONFIG.limits, "curiosity_min_source_chars", 10)
    monkeypatch.setattr(CONFIG.limits, "curiosity_source_globs", [])
    monkeypatch.setattr(CONFIG.limits, "curiosity_folder_confidence_min", 4)
    monkeypatch.setattr(producer.ollama_client, "is_reachable", lambda: True)

    rendered = {}

    def _fake_render(name, **kw):
        rendered.update(kw, _template=name)
        return f"PROMPT[{name}]"

    monkeypatch.setattr(producer, "render", _fake_render)

    (tmp_path / "raw" / "index").mkdir(parents=True)
    (tmp_path / "raw" / "index" / "docs.md").write_text(DIGEST, encoding="utf-8")
    src = tmp_path / "raw" / "notes" / "note.md"
    src.parent.mkdir(parents=True)
    src.write_text(
        "Operator erwähnt den Steuerbescheid 2024 und offene Rückfragen dazu.",
        encoding="utf-8",
    )
    return tmp_path, src, rendered


def _gap(**kw):
    g = {
        "topic": "Steuerbescheid 2024",
        "root_id": "docs",
        "file_path": "11 Steuern/Steuerbescheid-2024.pdf",
        "file_confidence": 5,
        "rationale": "The note asks questions the assessment PDF answers.",
    }
    g.update(kw)
    return g


def _run(monkeypatch, src, gaps):
    def _fake_chat_schema(prompt, *, model, schema, timeout):
        return json.dumps({"gaps": gaps})

    monkeypatch.setattr(producer.ollama_client, "chat_schema", _fake_chat_schema)
    asyncio.run(producer.maybe_generate_folder_requests(src))


def _requests(root):
    return sorted((root / "raw" / "requests").glob("request-*.json")) if (
        root / "raw" / "requests"
    ).exists() else []


def test_indexed_file_gap_writes_folder_deep_scan_request(env, monkeypatch):
    root, src, _ = env
    _run(monkeypatch, src, [_gap()])
    reqs = _requests(root)
    assert len(reqs) == 1
    body = json.loads(reqs[0].read_text(encoding="utf-8"))
    assert body["type"] == "folder-deep-scan"
    assert body["status"] == "pending"
    assert body["root_id"] == "docs"
    assert body["file_path"] == "11 Steuern/Steuerbescheid-2024.pdf"
    assert body["file_confidence"] == 5
    assert body["source"] == "raw/notes/note.md"


def test_invented_path_is_dropped_by_file_exists_anchor(env, monkeypatch):
    root, src, _ = env
    _run(monkeypatch, src, [_gap(file_path="11 Steuern/erfundene-datei.pdf")])
    assert _requests(root) == []


def test_low_confidence_gap_is_dropped(env, monkeypatch):
    root, src, _ = env
    _run(monkeypatch, src, [_gap(file_confidence=3)])  # min is 4
    assert _requests(root) == []


def test_no_watched_folders_skips_before_llm(env, monkeypatch):
    root, src, _ = env
    monkeypatch.setattr(CONFIG.personal, "watched_folders", [])

    def _boom(*a, **kw):  # pragma: no cover - must never fire
        raise AssertionError("LLM called despite no watched_folders")

    monkeypatch.setattr(producer.ollama_client, "chat_schema", _boom)
    asyncio.run(producer.maybe_generate_folder_requests(src))
    assert _requests(root) == []


def test_no_digests_skips_before_llm(env, monkeypatch):
    root, src, _ = env
    (root / "raw" / "index" / "docs.md").unlink()

    def _boom(*a, **kw):  # pragma: no cover - must never fire
        raise AssertionError("LLM called despite no digests")

    monkeypatch.setattr(producer.ollama_client, "chat_schema", _boom)
    asyncio.run(producer.maybe_generate_folder_requests(src))
    assert _requests(root) == []


# --- T03: dispatch branch + registration + backend skeleton ---------------


def _request_file(dir_path, name="request-steuerbescheid-2024-2026-06-10.json", **kw):
    body = {
        "type": "folder-deep-scan",
        "status": "pending",
        "root_id": "docs",
        "file_path": "11 Steuern/Steuerbescheid-2024.pdf",
        "file_confidence": 5,
        "topic": "Steuerbescheid 2024",
        "rationale": "The note asks questions the assessment PDF answers.",
        "source": "raw/notes/note.md",
        "created": "2026-06-10T12:00:00+00:00",
    }
    body.update(kw)
    p = dir_path / name
    p.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return p


def test_folder_curiosity_producer_is_registered():
    from producers import all_producers

    names = [p.SPEC.name for p in all_producers()]
    assert "folder_curiosity" in names


def test_dispatch_routes_folder_deep_scan_to_folder_backend(tmp_path, monkeypatch):
    import curiosity.cli as cli
    from curiosity.backends import folder as folder_backend

    called = {}

    def _fake(request_path, *, dry_run):
        called["path"] = request_path
        called["dry_run"] = dry_run
        return folder_backend.RunResult(success=True)

    monkeypatch.setattr(cli.folder_backend, "process_request", _fake)
    p = _request_file(tmp_path)
    assert cli._dispatch(p, dry_run=True) is True
    assert called == {"path": p, "dry_run": True}
    # a genuinely unknown type still hits the unsupported error path
    bogus = _request_file(tmp_path, name="request-bogus-2026-06-10.json",
                          type="weird-scan")
    assert cli._dispatch(bogus, dry_run=True) is False


def test_skeleton_real_run_leaves_request_pending(tmp_path, monkeypatch):
    from curiosity.backends import folder as folder_backend

    monkeypatch.setattr(
        CONFIG.personal,
        "watched_folders",
        [{"id": "docs", "kind": "local", "path": str(tmp_path / "trove")}],
    )
    p = _request_file(tmp_path)
    before = p.read_text(encoding="utf-8")
    res = folder_backend.process_request(p, dry_run=False)
    assert res.success is False
    assert "S04" in (res.error or "")
    assert p.read_text(encoding="utf-8") == before  # untouched -> stays pending


def test_skeleton_dry_run_resolves_path_and_reports_exists(tmp_path, monkeypatch):
    from curiosity.backends import folder as folder_backend

    target_dir = tmp_path / "trove" / "11 Steuern"
    target_dir.mkdir(parents=True)
    (target_dir / "Steuerbescheid-2024.pdf").write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        CONFIG.personal,
        "watched_folders",
        [{"id": "docs", "kind": "local", "path": str(tmp_path / "trove")}],
    )
    p = _request_file(tmp_path)
    res = folder_backend.process_request(p, dry_run=True)
    assert res.success is True
    # unknown root_id is a shape error even in dry-run
    bad = _request_file(tmp_path, name="request-bad-root-2026-06-10.json",
                        root_id="nope")
    assert folder_backend.process_request(bad, dry_run=True).success is False


def test_real_prompt_template_renders_with_t01_kwargs():
    """T02: the actual prompts/compile_curiosity_folder.md must render with
    exactly the kwargs the producer passes — no missing/unresolved vars."""
    from core.prompts import render as real_render

    out = real_render(
        "compile_curiosity_folder",
        source_path="raw/notes/note.md",
        source_content="Operator erwähnt den Steuerbescheid 2024.",
        folder_digests=DIGEST,
        timestamp="2026-06-10T12:00:00+00:00",
    )
    assert "raw/notes/note.md" in out
    assert "Steuerbescheid-2024.pdf" in out  # digest block embedded
    for field in ("root_id", "file_path", "file_confidence", "rationale"):
        assert f'"{field}"' in out  # JSON contract spelled out
    assert "${" not in out  # nothing unsubstituted


def test_over_budget_digest_is_trimmed_not_dropped(env, monkeypatch):
    root, src, rendered = env
    # inflate the digest with many file lines; keep one dir + Recent intact
    filler = "\n".join(
        f"- `bulk/file-{i:04d}.txt` · 1.0 KB" for i in range(400)
    )
    (root / "raw" / "index" / "docs.md").write_text(
        DIGEST + filler + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(CONFIG.limits, "curiosity_max_prompt_chars", 4000)
    _run(monkeypatch, src, [])
    digests_block = rendered["folder_digests"]
    assert len(digests_block) < 4000
    assert "Steuerbescheid-2024.pdf" in digests_block  # Recent line survives
    assert "`11 Steuern`/" in digests_block  # dir skeleton survives
    assert "file-0399" not in digests_block  # bulk file lines trimmed