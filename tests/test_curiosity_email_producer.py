"""M033-S04-T06 — characterisation of `curiosity.producer.maybe_generate_curiosity_requests`,
the email-deep-scan pass, with a fake Ollama: the gates, the folder-allowlist resolution,
the numbered listing + schema bounds, the per-gap drop ladder, the request shape, the
drop-summary log line and the failure ladder. Written before the split; the folder pass is
covered by test_curiosity_folder_producer.py."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest

from core.config import CONFIG
from core.utils import slugify
from curiosity import producer

SOURCE = (
    "Meeting mit Hetzner über die Rechnung vom Mai. Offene Frage: wird die Admin-Pauschale "
    "weiter berechnet? Bob schickt die Unterlagen per Mail nach."
)
FOLDERS = [
    {"path": "INBOX", "desc": "everything"},
    {"path": "INBOX/Hetzner", "desc": "hosting invoices"},
    {"path": "INBOX/Misc"},
]


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated vault root with one source note, three email folders, two accounts."""
    monkeypatch.setattr(producer, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(producer, "RAW_REQUESTS_DIR", tmp_path / "raw" / "requests")
    monkeypatch.setattr(producer, "RAW_INDEX_DIR", tmp_path / "raw" / "index")
    monkeypatch.setattr(CONFIG.features, "curiosity_loop", True)
    monkeypatch.setattr(CONFIG.limits, "curiosity_min_source_chars", 10)
    monkeypatch.setattr(CONFIG.limits, "curiosity_source_globs", [])
    monkeypatch.setattr(CONFIG.limits, "curiosity_exclude_globs", [])
    monkeypatch.setattr(CONFIG.limits, "curiosity_folder_confidence_min", 4)
    monkeypatch.setattr(CONFIG.limits, "curiosity_quote_min_anchor_tokens", 3)
    monkeypatch.setattr(CONFIG.limits, "curiosity_max_gaps", 5)
    monkeypatch.setattr(CONFIG.personal, "primary_account", "work")
    monkeypatch.setattr(CONFIG.personal, "accounts", {"work": {}, "private": {}})
    monkeypatch.setattr(CONFIG.personal, "curiosity_folders", [])
    monkeypatch.setattr(CONFIG.personal, "email_folders", list(FOLDERS))
    monkeypatch.setattr(producer.ollama_client, "is_reachable", lambda: True)

    rendered: dict = {}

    def _fake_render(name, **kw):
        rendered.update(kw, _template=name)
        return f"PROMPT[{name}]"

    monkeypatch.setattr(producer, "render", _fake_render)

    src = tmp_path / "raw" / "notes" / "hetzner.md"
    src.parent.mkdir(parents=True)
    src.write_text(SOURCE, encoding="utf-8")
    return tmp_path, src, rendered


def _gap(**kw):
    g = {
        "topic": "Hetzner Admin-Pauschale",
        "source_quote": "wird die Admin-Pauschale weiter berechnet",
        "folder_index": 2,
        "folder_confidence": 5,
        "account": "work",
        "rationale": "The note asks whether the fee continues.",
    }
    g.update(kw)
    return g


def _run(monkeypatch, src, gaps, *, seen: dict | None = None):
    """Run the pass with the fake model answering `gaps` (a list → JSON, a str verbatim,
    an exception → raised); `seen` receives the schema the producer sent."""

    def _fake_chat_schema(prompt, *, model, schema, timeout):
        if seen is not None:
            seen.update(prompt=prompt, model=model, schema=schema, timeout=timeout)
        if isinstance(gaps, BaseException):
            raise gaps
        if isinstance(gaps, str):
            return gaps
        return json.dumps({"gaps": gaps})

    monkeypatch.setattr(producer.ollama_client, "chat_schema", _fake_chat_schema)
    asyncio.run(producer.maybe_generate_curiosity_requests(src))


def _requests(root):
    d = root / "raw" / "requests"
    return sorted(d.glob("request-*.json")) if d.exists() else []


def _boom(*a, **kw):  # pragma: no cover - must never fire
    raise AssertionError("LLM called despite a gate")


SLUG = slugify("Hetzner Admin-Pauschale", max_len=40, ascii_only=True)


# ── the write path ───────────────────────────────────────────────────


def test_happy_gap_writes_an_email_deep_scan_request(env, monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="compile")
    root, src, rendered = env
    seen: dict = {}

    _run(monkeypatch, src, [_gap()], seen=seen)

    [req] = _requests(root)
    assert req.name == f"request-{SLUG}-{producer.today_iso()}.json"
    body = json.loads(req.read_text(encoding="utf-8"))
    created = body.pop("created")
    assert isinstance(created, str) and created.startswith("20")
    assert body == {
        "type": "email-deep-scan",
        "status": "pending",
        "folder": "INBOX/Hetzner",
        "folder_confidence": 5,
        "account": "work",
        "model": producer.CURIOSITY_MODEL,
        "topic": "Hetzner Admin-Pauschale",
        "source_quote": "wird die Admin-Pauschale weiter berechnet",
        "rationale": "The note asks whether the fee continues.",
        "source": "raw/notes/hetzner.md",
    }
    # The prompt saw the numbered listing of the post-allowlist folders + the excerpt.
    assert rendered["_template"] == "compile_curiosity"
    assert rendered["source_path"] == "raw/notes/hetzner.md"
    assert rendered["source_content"] == SOURCE
    assert rendered["primary_account"] == "work"
    assert rendered["email_folders_listing"] == (
        "1. INBOX — everything\n2. INBOX/Hetzner — hosting invoices\n3. INBOX/Misc"
    )
    # The schema bounds the pick to the listed folders and the configured accounts.
    props = seen["schema"]["properties"]["gaps"]["items"]["properties"]
    assert props["folder_index"] == {"type": "integer", "minimum": 1, "maximum": 3}
    assert props["account"] == {"type": "string", "enum": ["work", "private"]}
    assert seen["model"] == producer.CURIOSITY_MODEL
    assert seen["timeout"] == CONFIG.limits.curiosity_timeout_s
    assert "  Curiosity request: Hetzner Admin-Pauschale → INBOX/Hetzner" in caplog.text
    assert "gap(s) gen" not in caplog.text  # nothing dropped → no drop summary


def test_legacy_folder_field_maps_when_the_index_is_absent(env, monkeypatch) -> None:
    root, src, _ = env
    gap = _gap(folder="INBOX/Misc")
    del gap["folder_index"]

    _run(monkeypatch, src, [gap])

    [req] = _requests(root)
    assert json.loads(req.read_text(encoding="utf-8"))["folder"] == "INBOX/Misc"


def test_unknown_account_and_model_fall_back_in_the_request(env, monkeypatch) -> None:
    root, src, _ = env
    gap = _gap()
    del gap["account"]

    _run(monkeypatch, src, [gap])

    body = json.loads(_requests(root)[0].read_text(encoding="utf-8"))
    assert body["account"] == "work" and body["model"] == producer.CURIOSITY_MODEL


# ── the drop ladder ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"folder_index": 9, "folder": "INBOX/Nowhere"}, "folder_unmapped"),
        ({"folder_confidence": 3}, "folder_low_confidence"),
        ({"folder_confidence": "5"}, "folder_low_confidence"),
        ({"topic": "  "}, "empty_topic"),
        ({"rationale": ""}, "empty_rationale"),
        ({"source_quote": "kurz"}, "quote_missing"),
        ({"source_quote": None}, "quote_missing"),
        ({"source_quote": "nothing of this is in the source text"}, "quote_unsourced"),
    ],
)
def test_each_drop_reason_is_counted(env, monkeypatch, caplog, overrides, reason) -> None:
    caplog.set_level(logging.INFO, logger="compile")
    root, src, _ = env

    _run(monkeypatch, src, [_gap(**overrides)])

    assert _requests(root) == []
    assert f"  Curiosity: 1 gap(s) gen, 0 kept (dropped: {reason}=1)" in caplog.text


def test_edge_paraphrased_quote_is_anchored_by_a_token_window(env, monkeypatch) -> None:
    root, src, _ = env
    quote = "Ob die Admin-Pauschale weiter berechnet wird, bleibt offen"  # core 3-gram matches

    _run(monkeypatch, src, [_gap(source_quote=quote)])

    assert len(_requests(root)) == 1


def test_duplicate_and_previously_rejected_slugs_are_dropped(env, monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="compile")
    root, src, _ = env
    reqs = root / "raw" / "requests"
    reqs.mkdir(parents=True)
    (reqs / f"request-{SLUG}-{producer.today_iso()}.json").write_text("{}", encoding="utf-8")
    other_slug = slugify("Bob Unterlagen", max_len=40, ascii_only=True)
    (reqs / f"request-{other_slug}-2026-01-01.json").write_text(
        json.dumps({"status": "rejected"}), encoding="utf-8"
    )

    _run(
        monkeypatch,
        src,
        [_gap(), _gap(topic="Bob Unterlagen", source_quote="Bob schickt die Unterlagen per Mail")],
    )

    assert [p.name for p in _requests(root)] == [
        f"request-{other_slug}-2026-01-01.json",
        f"request-{SLUG}-{producer.today_iso()}.json",
    ]
    assert (
        "  Curiosity: 2 gap(s) gen, 0 kept (dropped: duplicate=1, rejected_persistent=1)"
        in caplog.text
    )


def test_max_gaps_caps_the_loop(env, monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="compile")
    root, src, _ = env
    monkeypatch.setattr(CONFIG.limits, "curiosity_max_gaps", 1)

    _run(
        monkeypatch,
        src,
        [_gap(), _gap(topic="Bob Unterlagen", source_quote="Bob schickt die Unterlagen per Mail")],
    )

    assert len(_requests(root)) == 1
    assert "  Curiosity: 2 gap(s) gen, 1 kept (dropped: none)" in caplog.text


# ── folders + allowlist ──────────────────────────────────────────────


def test_allowlist_restricts_the_listing_and_the_index(env, monkeypatch) -> None:
    root, src, rendered = env
    monkeypatch.setattr(CONFIG.personal, "curiosity_folders", ["INBOX/Hetzner"])
    seen: dict = {}

    _run(monkeypatch, src, [_gap(folder_index=1)], seen=seen)

    assert rendered["email_folders_listing"] == "1. INBOX/Hetzner — hosting invoices"
    props = seen["schema"]["properties"]["gaps"]["items"]["properties"]
    assert props["folder_index"]["maximum"] == 1
    assert json.loads(_requests(root)[0].read_text(encoding="utf-8"))["folder"] == "INBOX/Hetzner"


def test_allowlist_matching_nothing_falls_back_with_a_warning(env, monkeypatch, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="compile")
    _root, src, rendered = env
    monkeypatch.setattr(CONFIG.personal, "curiosity_folders", ["INBOX/Nope"])

    _run(monkeypatch, src, [_gap()])

    assert rendered["email_folders_listing"].startswith("1. INBOX — everything\n")
    assert (
        "  Curiosity: personal.curiosity_folders=['INBOX/Nope'] matched zero "
        "email_folders — falling back to full list" in caplog.text
    )


def test_no_email_folders_skips_before_the_model(env, monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="compile")
    root, src, _ = env
    monkeypatch.setattr(CONFIG.personal, "email_folders", [{"desc": "no path"}])
    monkeypatch.setattr(producer.ollama_client, "chat_schema", _boom)

    asyncio.run(producer.maybe_generate_curiosity_requests(src))

    assert _requests(root) == []
    assert "  Curiosity: no personal.email_folders configured, skipping" in caplog.text


# ── the gates ────────────────────────────────────────────────────────


def test_feature_off_short_source_glob_and_exclude_gates(env, monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="compile")
    root, src, rendered = env
    monkeypatch.setattr(producer.ollama_client, "chat_schema", _boom)

    monkeypatch.setattr(CONFIG.features, "curiosity_loop", False)
    asyncio.run(producer.maybe_generate_curiosity_requests(src))
    monkeypatch.setattr(CONFIG.features, "curiosity_loop", True)

    monkeypatch.setattr(CONFIG.limits, "curiosity_min_source_chars", 10_000)
    asyncio.run(producer.maybe_generate_curiosity_requests(src))
    monkeypatch.setattr(CONFIG.limits, "curiosity_min_source_chars", 10)

    monkeypatch.setattr(CONFIG.limits, "curiosity_source_globs", ["daily/*"])
    asyncio.run(producer.maybe_generate_curiosity_requests(src))
    assert "  Curiosity: skipping raw/notes/hetzner.md (no source-glob match)" in caplog.text
    monkeypatch.setattr(CONFIG.limits, "curiosity_source_globs", [])

    monkeypatch.setattr(CONFIG.limits, "curiosity_exclude_globs", ["raw/notes/*"])
    asyncio.run(producer.maybe_generate_curiosity_requests(src))
    assert "  Curiosity: skipping raw/notes/hetzner.md (exclude-glob)" in caplog.text

    assert _requests(root) == [] and rendered == {}


def test_unreachable_ollama_skips_after_rendering(env, monkeypatch) -> None:
    root, src, rendered = env
    monkeypatch.setattr(producer.ollama_client, "is_reachable", lambda: False)
    monkeypatch.setattr(producer.ollama_client, "chat_schema", _boom)

    asyncio.run(producer.maybe_generate_curiosity_requests(src))

    assert _requests(root) == [] and rendered["_template"] == "compile_curiosity"


# ── the model's answer ───────────────────────────────────────────────


def test_empty_non_dict_and_invalid_answers(env, monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="compile")
    root, src, _ = env

    _run(monkeypatch, src, [])
    assert "  Curiosity: no gaps found" in caplog.text

    _run(monkeypatch, src, ["not a gap", _gap()])
    assert "  Curiosity: dropping 1 non-dict gap(s); sample='not a gap'" in caplog.text
    assert len(_requests(root)) == 1

    _run(monkeypatch, src, "{not json")
    assert "  Curiosity: invalid JSON: {not json" in caplog.text

    _run(monkeypatch, src, "42")
    assert "  Curiosity: unexpected response type" in caplog.text


def test_failure_ladder_logs_and_never_raises(env, monkeypatch, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="compile")
    _root, src, _ = env
    model = producer.CURIOSITY_MODEL

    _run(monkeypatch, src, httpx.TimeoutException("slow"))
    assert (
        f"  Curiosity: Ollama timeout (model={model}, {CONFIG.limits.curiosity_timeout_s}s)"
        in caplog.text
    )

    req = httpx.Request("POST", "http://ollama/api/chat")
    _run(
        monkeypatch,
        src,
        httpx.HTTPStatusError("404", request=req, response=httpx.Response(404, text="no model")),
    )
    assert (
        f"  Curiosity: Ollama model '{model}' not available — pull it on the host "
        f"(`ollama pull {model}`) or change CONFIG.models.curiosity_model" in caplog.text
    )

    _run(
        monkeypatch,
        src,
        httpx.HTTPStatusError("500", request=req, response=httpx.Response(500, text="boom")),
    )
    assert "  Curiosity: Ollama HTTP 500 — boom" in caplog.text

    _run(monkeypatch, src, httpx.ConnectError("refused"))
    assert "  Curiosity: Ollama connection error: refused" in caplog.text

    _run(monkeypatch, src, KeyError("gaps"))
    assert "  Curiosity: parse error: 'gaps'" in caplog.text

    _run(monkeypatch, src, RuntimeError("unexpected"))
    assert "  Curiosity pass failed" in caplog.text
