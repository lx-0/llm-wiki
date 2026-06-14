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
