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
import os

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


def test_real_run_on_missing_file_marks_stale(tmp_path, monkeypatch):
    """Stale index (file gone since indexing): fail soft, request marked
    `stale` (T03) so batches stop re-dispatching until it reappears."""
    from curiosity.backends import folder as folder_backend

    monkeypatch.setattr(
        CONFIG.personal,
        "watched_folders",
        [{"id": "docs", "kind": "local", "path": str(tmp_path / "trove")}],
    )
    p = _request_file(tmp_path)
    res = folder_backend.process_request(p, dry_run=False)
    assert res.success is False
    assert "missing" in (res.error or "")
    req = json.loads(p.read_text(encoding="utf-8"))
    assert req["status"] == "stale"
    assert req["last_error"]


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


# --- S04-T02: answer-only persistence --------------------------------------

RAW_BODY_MARKER = "RAWBODY-7f3a-must-never-persist"


def _persist_env(tmp_path, monkeypatch):
    """Vault + trove + pending request; provider mocked at the seam."""
    from curiosity.backends import folder as folder_backend

    trove = tmp_path / "trove" / "11 Steuern"
    trove.mkdir(parents=True)
    (trove / "Steuerbescheid-2024.pdf").write_text(
        f"intro {RAW_BODY_MARKER} outro", encoding="utf-8"
    )
    monkeypatch.setattr(
        CONFIG.personal,
        "watched_folders",
        [{"id": "docs", "kind": "local", "path": str(tmp_path / "trove")}],
    )
    monkeypatch.setattr(folder_backend, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(
        folder_backend, "ANSWER_DIR", tmp_path / "raw" / "notes" / "folder"
    )
    p = _request_file(tmp_path)
    return folder_backend, tmp_path, p


def _fake_provider(monkeypatch, folder_backend, answer_md, error=None):
    from curiosity.backends.folder_providers import ScanAnswer

    class _Fake:
        async def answer(self, *, topic, rationale, file_abs, file_rel):
            return ScanAnswer(
                answer_md=answer_md,
                file_path=file_rel,
                as_of_mtime=1234.5,
                error=error,
            )

    monkeypatch.setattr(folder_backend, "get_provider", lambda: _Fake())


def test_persist_answer_only_and_flip_request(tmp_path, monkeypatch):
    fb, root, request_path = _persist_env(tmp_path, monkeypatch)
    _fake_provider(
        monkeypatch, fb, "## Answer\n\nFinal amount: 1234 EUR (page 2)."
    )
    res = fb.process_request(request_path, dry_run=False)
    assert res.success is True

    answer = root / "raw" / "notes" / "folder" / (
        "answer-" + request_path.stem.removeprefix("request-") + ".md"
    )
    assert answer.exists()
    text = answer.read_text(encoding="utf-8")
    assert "kind: folder-deep-scan" in text
    assert "as_of_mtime: 1234.5" in text
    # human-readable date next to the float (S05-T01): the compile agent
    # and the operator read a date, the staleness machinery keeps the float
    assert "as_of: 1970-01-01" in text  # 1234.5 epoch -> 1970-01-01 UTC
    assert "Final amount: 1234 EUR" in text

    req = json.loads(request_path.read_text(encoding="utf-8"))
    assert req["status"] == "done"
    assert req["output"].endswith(answer.name)


def test_sensitivity_stamped_into_answer_when_root_carries_it(
    tmp_path, monkeypatch
):
    """Q3 full build: the root's sensitivity value travels into the answer
    frontmatter; compile propagates it from there (prompt rule)."""
    fb, root, request_path = _persist_env(tmp_path, monkeypatch)
    monkeypatch.setattr(
        CONFIG.personal,
        "watched_folders",
        [{
            "id": "docs", "kind": "local",
            "path": str(tmp_path / "trove"),
            "sensitivity": "private",
        }],
    )
    _fake_provider(monkeypatch, fb, "## Answer\n\ndistilled")
    assert fb.process_request(request_path, dry_run=False).success is True
    answer = next((root / "raw" / "notes" / "folder").glob("answer-*.md"))
    assert "sensitivity: private" in answer.read_text(encoding="utf-8")


def test_no_sensitivity_line_when_root_has_none(tmp_path, monkeypatch):
    fb, root, request_path = _persist_env(tmp_path, monkeypatch)
    _fake_provider(monkeypatch, fb, "## Answer\n\ndistilled")
    assert fb.process_request(request_path, dry_run=False).success is True
    answer = next((root / "raw" / "notes" / "folder").glob("answer-*.md"))
    assert "sensitivity" not in answer.read_text(encoding="utf-8")


def test_compile_main_prompt_carries_sensitivity_propagation_rule():
    """The substrate-agnostic carry rule lives in the main compile prompt."""
    prompt = (
        __import__("pathlib").Path("prompts/compile_main.md")
        .read_text(encoding="utf-8")
    )
    assert "sensitivity" in prompt


def test_compile_main_prompt_records_folder_answer_facts():
    """S05-T03 live finding: rule 1's 'not trivial facts' bar made the agent
    dismiss an operator-approved invoice extract (run 2026-06-10 23:15 —
    done, 0 writes). folder-deep-scan answers are explicitly requested
    facts: the prompt must instruct recording them despite the bar."""
    prompt = (
        __import__("pathlib").Path("prompts/compile_main.md")
        .read_text(encoding="utf-8")
    )
    assert "folder-deep-scan" in prompt
    assert "raw/notes/folder/" in prompt


def test_p2_no_raw_body_anywhere_under_the_vault(tmp_path, monkeypatch):
    fb, root, request_path = _persist_env(tmp_path, monkeypatch)
    _fake_provider(monkeypatch, fb, "## Answer\n\ndistilled only")
    assert fb.process_request(request_path, dry_run=False).success is True
    # P2: walk EVERY file under the vault root (except the trove itself,
    # which is outside the vault in production but inside tmp here) and
    # assert the raw body marker persisted nowhere.
    offenders = [
        f for f in root.rglob("*")
        if f.is_file()
        and "trove" not in f.parts
        and RAW_BODY_MARKER in f.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == []


def test_sentinel_marks_request_not_answered(tmp_path, monkeypatch):
    """T03: a non-answer quarantines the request (status not-answered +
    staleness anchor) so batches stop re-dispatching; nothing persisted."""
    fb, root, request_path = _persist_env(tmp_path, monkeypatch)
    _fake_provider(
        monkeypatch, fb,
        "NOT ANSWERED IN THIS FILE\nIt is a phone contract, not a tax doc.",
    )
    res = fb.process_request(request_path, dry_run=False)
    assert res.success is False
    assert "not_answered" in (res.error or "")
    assert not (root / "raw" / "notes" / "folder").exists()
    req = json.loads(request_path.read_text(encoding="utf-8"))
    assert req["status"] == "not-answered"
    assert req["failed_as_of_mtime"] == 1234.5  # anchor = answer's as-of
    assert req["last_error"]


def test_provider_error_marks_request_error(tmp_path, monkeypatch):
    fb, root, request_path = _persist_env(tmp_path, monkeypatch)
    _fake_provider(monkeypatch, fb, "", error="empty_result")
    res = fb.process_request(request_path, dry_run=False)
    assert res.success is False
    assert res.error == "empty_result"
    assert not (root / "raw" / "notes" / "folder").exists()
    req = json.loads(request_path.read_text(encoding="utf-8"))
    assert req["status"] == "error"
    assert req["last_error"] == "empty_result"
    assert req["failed_as_of_mtime"] == 1234.5


def test_error_request_retries_only_after_file_change(tmp_path, monkeypatch):
    """The staleness gate: unchanged file -> skip without constructing a
    provider; touched file -> retry proceeds and can succeed."""
    fb, root, request_path = _persist_env(tmp_path, monkeypatch)
    trove_file = tmp_path / "trove" / "11 Steuern" / "Steuerbescheid-2024.pdf"
    os.utime(trove_file, (1234.5, 1234.5))  # current mtime == failure anchor
    _fake_provider(monkeypatch, fb, "", error="empty_result")
    assert fb.process_request(request_path, dry_run=False).success is False

    def _boom():  # pragma: no cover - must never fire
        raise AssertionError("provider constructed despite unchanged file")

    monkeypatch.setattr(fb, "get_provider", _boom)
    res = fb.process_request(request_path, dry_run=False)
    assert res.success is False
    assert res.error == "unchanged_since_failure"

    os.utime(trove_file, (9999.0, 9999.0))  # the source changed
    _fake_provider(monkeypatch, fb, "## Answer\n\nnow it works")
    res2 = fb.process_request(request_path, dry_run=False)
    assert res2.success is True
    assert json.loads(request_path.read_text(encoding="utf-8"))["status"] == "done"


def test_missing_file_marks_stale_and_retries_on_reappearance(
    tmp_path, monkeypatch
):
    fb, root, request_path = _persist_env(tmp_path, monkeypatch)
    trove_file = tmp_path / "trove" / "11 Steuern" / "Steuerbescheid-2024.pdf"
    trove_file.unlink()
    res = fb.process_request(request_path, dry_run=False)
    assert res.success is False
    assert json.loads(request_path.read_text(encoding="utf-8"))["status"] == "stale"

    # still missing -> skip without provider
    def _boom():  # pragma: no cover
        raise AssertionError("provider constructed despite missing file")

    monkeypatch.setattr(fb, "get_provider", _boom)
    res2 = fb.process_request(request_path, dry_run=False)
    assert res2.error == "still_missing"

    # file reappears -> retry proceeds
    trove_file.write_text("back again", encoding="utf-8")
    _fake_provider(monkeypatch, fb, "## Answer\n\nrecovered")
    assert fb.process_request(request_path, dry_run=False).success is True


def test_done_request_is_never_redispatched(tmp_path, monkeypatch):
    fb, root, request_path = _persist_env(tmp_path, monkeypatch)
    req = json.loads(request_path.read_text(encoding="utf-8"))
    req["status"] = "done"
    request_path.write_text(json.dumps(req, indent=2), encoding="utf-8")
    before = request_path.read_text(encoding="utf-8")

    def _boom():  # pragma: no cover
        raise AssertionError("provider constructed for a done request")

    monkeypatch.setattr(fb, "get_provider", _boom)
    res = fb.process_request(request_path, dry_run=False)
    assert res.success is False
    assert res.error == "already_done"
    assert request_path.read_text(encoding="utf-8") == before


# --- S04-T05: informed-consent walk card -----------------------------------


def _card_env(tmp_path, monkeypatch, create_file=True):
    trove = tmp_path / "trove" / "11 Steuern"
    trove.mkdir(parents=True)
    if create_file:
        (trove / "Steuerbescheid-2024.pdf").write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        CONFIG.personal,
        "watched_folders",
        [{"id": "docs", "kind": "local", "path": str(tmp_path / "trove")}],
    )


def test_walk_card_folder_request_shows_informed_consent(
    tmp_path, monkeypatch, capsys
):
    import curiosity.cli as cli

    _card_env(tmp_path, monkeypatch)
    r = json.loads(_request_file(tmp_path).read_text(encoding="utf-8"))
    cli._print_request_card(1, 1, tmp_path / "request-x.json", r)
    out = capsys.readouterr().out
    # file + confidence
    assert "docs/11 Steuern/Steuerbescheid-2024.pdf" in out
    assert "confidence 5/5" in out
    # resolved absolute path + staleness marker
    assert str(tmp_path / "trove" / "11 Steuern" / "Steuerbescheid-2024.pdf") in out
    assert "exists" in out
    # the consent line: what gets loaded, sent WHERE, to answer WHAT
    assert "LOAD this file" in out
    assert "claude-sdk" in out
    assert "Steuerbescheid 2024" in out  # the topic
    assert "Why this file:" in out
    # no email-card leftovers
    assert "Account" not in out


def test_walk_card_folder_request_marks_missing_file(
    tmp_path, monkeypatch, capsys
):
    import curiosity.cli as cli

    _card_env(tmp_path, monkeypatch, create_file=False)
    r = json.loads(_request_file(tmp_path).read_text(encoding="utf-8"))
    cli._print_request_card(1, 1, tmp_path / "request-x.json", r)
    out = capsys.readouterr().out
    assert "MISSING" in out  # informed staleness BEFORE approving


def test_walk_card_email_request_unchanged(tmp_path, capsys):
    import curiosity.cli as cli

    r = {
        "type": "email-deep-scan",
        "status": "pending",
        "topic": "ProjectX delivery timeline",
        "folder": "INBOX/Work",
        "folder_confidence": 4,
        "account": "kasserver",
        "source": "raw/notes/note.md",
        "created": "2026-06-10T20:00:00+00:00",
        "model": "llama3.1:8b",
        "source_quote": "the delivery slipped",
        "rationale": "Work folder holds the thread.",
    }
    cli._print_request_card(1, 1, tmp_path / "request-email.json", r)
    out = capsys.readouterr().out
    assert "Folder      : INBOX/Work" in out
    assert "Account     : kasserver" in out
    assert "LOAD this file" not in out  # consent line is folder-only


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