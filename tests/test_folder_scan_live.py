"""LIVE e2e for the folder-deep-scan path (M027-S04-T04).

Gated on LLM_WIKI_LIVE_E2E=1 — the normal suite skips this file ($0,
deterministic). When enabled it runs the FULL real chain once: a planted
real trove file → pending folder-deep-scan request → `cli._dispatch`
real-run → REAL ClaudeSdkProvider (real bundled-CLI SDK call, real
exact-file path-scope hook) → answer artifact.

Cost: one CONFIG.models.compile_model call on a ~10-line file (cents).
This is the REGEL-#1 boundary for the T01–T03 chain, which is otherwise
verified with a mocked SDK.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.config import CONFIG

pytestmark = pytest.mark.skipif(
    not os.environ.get("LLM_WIKI_LIVE_E2E"),
    reason="live SDK e2e — set LLM_WIKI_LIVE_E2E=1 to run (costs cents)",
)

TARGET_FACT = "KX-4711-2024"
RAW_BODY_MARKER = (
    "LOREMRAW-0xCAFE-this-exact-sentence-must-never-be-copied-into-the-vault-"
    "because-answers-are-distillations-not-documents"
)


def test_live_folder_deep_scan_end_to_end(tmp_path: Path, monkeypatch):
    import curiosity.cli as cli
    from curiosity.backends import folder as fb

    # ── real trove file with a planted fact + a raw-body marker ──────
    trove = tmp_path / "trove" / "40 Versicherungen"
    trove.mkdir(parents=True)
    doc = trove / "mobilfunk-vertrag-notizen.md"
    doc.write_text(
        "# Mobilfunkvertrag — Notizen\n\n"
        f"Die Vertragsnummer lautet {TARGET_FACT}.\n"
        "Monatliche Grundgebühr: 14,99 EUR. Kündigungsfrist: 1 Monat.\n\n"
        f"Anhang (irrelevant): {RAW_BODY_MARKER}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        CONFIG.personal,
        "watched_folders",
        [{"id": "docs", "kind": "local", "path": str(tmp_path / "trove")}],
    )
    monkeypatch.setattr(fb, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(fb, "ANSWER_DIR", tmp_path / "raw" / "notes" / "folder")

    request_path = tmp_path / "request-vertragsnummer-mobilfunk-2026-06-10.json"
    request_path.write_text(
        json.dumps(
            {
                "type": "folder-deep-scan",
                "status": "pending",
                "root_id": "docs",
                "file_path": "40 Versicherungen/mobilfunk-vertrag-notizen.md",
                "file_confidence": 5,
                "topic": "Vertragsnummer des Mobilfunkvertrags",
                "rationale": "Dateiname nennt den Mobilfunkvertrag direkt.",
                "source": "raw/notes/note.md",
                "created": "2026-06-10T20:00:00+00:00",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # ── the real thing: dispatch → SDK → persist ─────────────────────
    assert cli._dispatch(request_path, dry_run=False) is True

    answer_path = (
        tmp_path / "raw" / "notes" / "folder"
        / "answer-vertragsnummer-mobilfunk-2026-06-10.md"
    )
    assert answer_path.exists()
    answer_text = answer_path.read_text(encoding="utf-8")
    print("\n--- live answer artifact ---\n" + answer_text + "\n---")

    # contract values (LLM wording is free)
    assert "kind: folder-deep-scan" in answer_text
    assert f"as_of_mtime: {doc.stat().st_mtime}" in answer_text
    assert TARGET_FACT in answer_text  # the fact was captured

    # P2 live: the raw body marker persisted nowhere under the vault root
    offenders = [
        f for f in tmp_path.rglob("*")
        if f.is_file()
        and "trove" not in f.parts
        and RAW_BODY_MARKER in f.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == []

    req = json.loads(request_path.read_text(encoding="utf-8"))
    assert req["status"] == "done"
    assert req["output"].endswith(answer_path.name)
