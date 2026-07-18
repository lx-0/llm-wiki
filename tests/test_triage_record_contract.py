"""Contract guard: the inbox-record frontmatter ⇄ the static triage UI.

`templates/triage.html` is a separate (JavaScript) consumer of the same
`workspace/inbox/<stem>.md` records that `scripts/intents/_record.py` writes and
`scripts/triage.py` mutates. Three independent readers of one markdown shape —
no shared schema object can bind them across Python + the browser. So this test
pins the contract: the frontmatter keys the writer emits AND the keys the HTML
depends on. Rename a key in `_record.py` and forget the HTML → this test fails,
naming exactly what drifted. (Write-Read-Symmetry rule.)
"""
from __future__ import annotations

import re
from pathlib import Path

# Keys the triage UI reads/writes (detected_at is written but the UI ignores it).
CONTRACT_KEYS = {"type", "status", "kind", "confidence", "summary", "source"}

_TRIAGE_HTML = Path(__file__).resolve().parent.parent / "templates" / "triage.html"


def _record_frontmatter_keys(tmp_path, monkeypatch) -> set[str]:
    import intents._record as rec
    monkeypatch.setattr(rec, "WORKSPACE_INBOX_DIR", tmp_path)
    from intents.base import Intent

    rec.write_inbox_record(
        Intent(kind="note", summary="x", source="raw/voice/v.md", confidence="high"),
        type_="note", triage_hint="hint.",
    )
    text = (tmp_path / "v.md").read_text(encoding="utf-8")
    m = re.match(r"\A---\n(.*?)\n---", text, re.DOTALL)
    assert m, "record has no frontmatter block"
    return {line.split(":", 1)[0].strip() for line in m.group(1).splitlines() if ":" in line}


def test_writer_emits_every_contract_key(tmp_path, monkeypatch):
    keys = _record_frontmatter_keys(tmp_path, monkeypatch)
    missing = CONTRACT_KEYS - keys
    assert not missing, (
        f"_record.py no longer writes {missing} — the triage UI reads these. "
        f"Update CONTRACT_KEYS + templates/triage.html together."
    )


def test_triage_html_references_every_contract_key():
    html = _TRIAGE_HTML.read_text(encoding="utf-8")
    missing = {k for k in CONTRACT_KEYS if k not in html}
    assert not missing, (
        f"templates/triage.html no longer references {missing} — if the record "
        f"schema changed, the UI must follow."
    )


def test_summary_umlaut_and_quote_round_trip(tmp_path, monkeypatch):
    """C03 live bug (RED first): _record.py wrote `summary:` via json.dumps
    (ensure_ascii → `M\\u00fcller`, quotes → `\\"`), while triage._fields read
    it back with a bare `.strip('\"')` — umlauts and quotes surfaced garbled in
    the triage list AND were copied garbled into workspace/todo.md on accept.
    The write and the read now both go through core.frontmatter, so the record
    round-trips exactly."""
    import intents._record as rec
    import triage
    from intents.base import Intent

    monkeypatch.setattr(rec, "WORKSPACE_INBOX_DIR", tmp_path)
    summary = 'Müller sagt "Grüß dich" und geht.'
    rec.write_inbox_record(
        Intent(kind="task", summary=summary, source="raw/voice/v.md", confidence="high"),
        type_="task", triage_hint="hint.",
    )
    text = (tmp_path / "v.md").read_text(encoding="utf-8")
    fields = triage._fields(text)
    assert fields["summary"] == summary
    # The other reader of the same bytes (capture date fallback path) still
    # gets a sliceable string for detected_at.
    assert len(fields.get("detected_at", "")[:10]) == 10


def test_legacy_json_escaped_summary_now_decodes():
    """Records already on disk (written pre-C03 with ensure_ascii json.dumps)
    are valid YAML double-quoted scalars — the new reader decodes them instead
    of displaying `M\\u00fcller`."""
    import triage

    legacy = (
        "---\n"
        "type: task\n"
        "status: pending\n"
        'summary: "M\\u00fcller sagt \\"hi\\""\n'
        "source: raw/voice/v.md\n"
        "---\n# x\n"
    )
    assert triage._fields(legacy)["summary"] == 'Müller sagt "hi"'
