"""Tests for the gmeet collector's pairing logic (Notes ↔ Transcript merge).

The collector itself is heavy (OAuth + Drive HTTP), so these tests cover the
pure pieces that decide *whether* and *how* to merge:

- `_meeting_key`: same meeting → same key; different meeting → different key;
  whitespace + quote-glyph variation between Notes-Doc and Transcript-Doc
  names normalises away.
- `_scan_siblings`: legacy singular `doc_kind` / `drive_doc_id` frontmatter is
  parsed AND new list-shape frontmatter is parsed; both feed the sibling-map.
- `_render_markdown`: a list of Docs renders one file with ordered sections.
- `_merge_into_sibling`: legacy frontmatter is upgraded to the list shape and
  the new section is appended; idempotency assertion is part of the
  collector's run-loop logic (sibling.doc_kinds check) — covered separately.

Order of section helpers: `_KIND_ORDER` (declared inside `_run_one_account`)
ensures Notes → Transcript → unknown — exercised indirectly via the render
test by passing Docs in mixed order.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from collectors import gmeet


# ── _meeting_key ─────────────────────────────────────────────────────


def test_meeting_key_pairs_notes_and_transcript_for_same_meeting() -> None:
    notes = 'Sprint Sync – 2026/05/15 10:00 CEST – Notizen von Gemini'
    tx = 'Sprint Sync – 2026/05/15 10:00 CEST – Transcript'
    assert gmeet._meeting_key(notes) == gmeet._meeting_key(tx)


def test_meeting_key_distinguishes_different_meetings() -> None:
    a = 'Sprint Sync – 2026/05/15 10:00 CEST – Transcript'
    b = 'Sprint Sync – 2026/05/16 10:00 CEST – Transcript'  # next-day session
    assert gmeet._meeting_key(a) != gmeet._meeting_key(b)


def test_meeting_key_normalises_quote_glyph_variation() -> None:
    # Gemini sometimes uses straight quotes in one Doc, curly in the other.
    straight = 'Arbeitsgruppe "Agentic OS" – 2026/05/15 – Notizen von Gemini'
    curly = 'Arbeitsgruppe “Agentic OS” – 2026/05/15 – Transcript'
    assert gmeet._meeting_key(straight) == gmeet._meeting_key(curly)


def test_meeting_key_normalises_whitespace_variation() -> None:
    a = 'My  Meeting\t – 2026/05/15 – Transcript'
    b = 'My Meeting – 2026/05/15 – Notes by Gemini'
    assert gmeet._meeting_key(a) == gmeet._meeting_key(b)


# ── _scan_siblings ──────────────────────────────────────────────────


def _write_legacy_file(root: Path, *, drive_doc_id: str, doc_kind: str,
                      drive_doc_name: str, body: str = "Legacy body.") -> Path:
    """Write a pre-pairing-shape file (singular `doc_kind` / `drive_doc_id`)."""
    p = root / f"2026-05-13--meeting--{drive_doc_id[:12]}.md"
    p.write_text(
        "---\n"
        "type: transcript\n"
        "source: gmeet\n"
        f"meeting_id: {drive_doc_id[:12]}\n"
        f"title: '{gmeet._meeting_title(drive_doc_name)}'\n"
        f"doc_kind: {doc_kind}\n"
        f"drive_doc_id: {drive_doc_id}\n"
        f"drive_doc_name: '{drive_doc_name}'\n"
        "---\n\n"
        "## Summary\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return p


def test_scan_siblings_returns_empty_for_missing_dir(tmp_path: Path) -> None:
    smap, sids = gmeet._scan_siblings(tmp_path / "does-not-exist")
    assert smap == {}
    assert sids == set()


def test_scan_siblings_parses_legacy_singular_frontmatter(tmp_path: Path) -> None:
    name = 'Sprint Sync – 2026/05/15 10:00 CEST – Notizen von Gemini'
    p = _write_legacy_file(tmp_path, drive_doc_id="doc_id_notes_legacy",
                           doc_kind="notes", drive_doc_name=name)
    smap, sids = gmeet._scan_siblings(tmp_path)
    assert list(smap.keys()) == [gmeet._meeting_key(name)]
    sib = smap[gmeet._meeting_key(name)]
    assert sib.path == p
    assert sib.doc_kinds == {"notes"}
    assert sib.drive_doc_ids == {"doc_id_notes_legacy"}
    # `already_present` set covers both filename short-id AND frontmatter ids.
    assert "doc_id_notes_legacy"[:12] in sids


def test_scan_siblings_parses_new_list_frontmatter(tmp_path: Path) -> None:
    name = 'Sprint Sync – 2026/05/15 10:00 CEST'
    p = tmp_path / f"2026-05-15--sprint--{gmeet._meeting_key(name)}.md"
    p.write_text(
        "---\n"
        "type: transcript\n"
        "source: gmeet\n"
        f"title: '{name}'\n"
        "doc_kinds:\n  - notes\n  - transcript\n"
        "drive_docs:\n"
        "  - id: doc_notes_xyz\n    kind: notes\n    name: 'Sprint Sync – Notizen von Gemini'\n"
        "  - id: doc_tx_xyz\n    kind: transcript\n    name: 'Sprint Sync – Transcript'\n"
        f"drive_doc_name: '{name} – Notizen von Gemini'\n"
        "---\n\n## Summary\n\nx\n\n## Transcript\n\ny\n",
        encoding="utf-8",
    )
    smap, sids = gmeet._scan_siblings(tmp_path)
    sib = smap[gmeet._meeting_key(name + ' – Notizen von Gemini')]
    assert sib.doc_kinds == {"notes", "transcript"}
    assert sib.drive_doc_ids == {"doc_notes_xyz", "doc_tx_xyz"}


def test_scan_siblings_tolerates_malformed_frontmatter(tmp_path: Path) -> None:
    """Broken YAML → file is skipped, the rest of the dir still indexes."""
    good = _write_legacy_file(tmp_path, drive_doc_id="good_id",
                              doc_kind="notes",
                              drive_doc_name="Good Meeting – Notizen von Gemini")
    bad = tmp_path / "2026-05-13--bad--xxxxxxxxxxxx.md"
    bad.write_text("---\nnot: [valid: yaml\n---\n\nbody\n", encoding="utf-8")
    no_fm = tmp_path / "2026-05-13--nofm--yyyyyyyyyyyy.md"
    no_fm.write_text("just a body, no frontmatter\n", encoding="utf-8")

    smap, _sids = gmeet._scan_siblings(tmp_path)
    assert len(smap) == 1
    assert list(smap.values())[0].path == good


# ── _render_markdown ────────────────────────────────────────────────


def test_render_markdown_single_doc_uses_list_schema() -> None:
    doc = {"id": "abc123def456", "name": "Solo Meeting – 2026/05/15 – Transcript",
           "createdTime": "2026-05-15T10:00:00Z", "webViewLink": "https://drive.example/abc"}
    md = gmeet._render_markdown([(doc, "**Alice** [00:01] — Hi")],
                                 account_id="acct", input_source="cli")
    assert "doc_kinds:\n- transcript" in md
    assert "drive_docs:" in md
    assert "## Transcript" in md
    # Singular legacy keys must NOT appear in fresh writes — only the list shape.
    assert "doc_kind:" not in md.split("---\n", 2)[1]  # not in the frontmatter
    assert "drive_doc_id:" not in md.split("---\n", 2)[1]


def test_render_markdown_pairs_notes_before_transcript() -> None:
    notes = {"id": "n1", "name": "Pair – 2026/05/15 – Notizen von Gemini",
             "createdTime": "2026-05-15T10:01:00Z"}
    tx = {"id": "t1", "name": "Pair – 2026/05/15 – Transcript",
          "createdTime": "2026-05-15T10:05:00Z"}
    md = gmeet._render_markdown([(notes, "Summary body."), (tx, "Transcript body.")],
                                 account_id="acct", input_source="cli")
    # `## Summary` appears before `## Transcript` in the body.
    assert md.index("## Summary") < md.index("## Transcript")
    # `doc_kinds` list order mirrors the input order (Notes first).
    assert "doc_kinds:\n- notes\n- transcript" in md


def test_render_markdown_meeting_id_is_meeting_key_not_doc_short_id() -> None:
    """Across a Notes-Doc + Transcript-Doc pair, `meeting_id` is the stable
    meeting_key — not the first Doc's short_id — so the field genuinely
    identifies the meeting, not the file's first source."""
    notes = {"id": "abc_notes", "name": "Meeting X – Notizen von Gemini",
             "createdTime": "2026-05-15T10:00:00Z"}
    tx = {"id": "abc_tx", "name": "Meeting X – Transcript",
          "createdTime": "2026-05-15T10:05:00Z"}
    md_pair = gmeet._render_markdown([(notes, "n"), (tx, "t")],
                                      account_id="a", input_source="cli")
    md_solo = gmeet._render_markdown([(notes, "n")], account_id="a", input_source="cli")
    expected = gmeet._meeting_key(notes["name"])
    assert f"meeting_id: {expected}" in md_pair
    assert f"meeting_id: {expected}" in md_solo  # same meeting → same id either way


def test_render_markdown_rejects_empty_doc_list() -> None:
    with pytest.raises(ValueError):
        gmeet._render_markdown([], account_id="a", input_source="cli")


# ── _merge_into_sibling ─────────────────────────────────────────────


def test_merge_into_sibling_upgrades_legacy_singular_to_list_shape(tmp_path: Path) -> None:
    name = 'Pair – 2026/05/15 – Notizen von Gemini'
    _write_legacy_file(tmp_path, drive_doc_id="doc_notes_id",
                       doc_kind="notes", drive_doc_name=name)
    smap, _ = gmeet._scan_siblings(tmp_path)
    sib = list(smap.values())[0]
    new_doc = {"id": "doc_tx_id", "name": "Pair – 2026/05/15 – Transcript",
               "createdTime": "2026-05-15T10:05:00Z", "webViewLink": None}
    merged = gmeet._merge_into_sibling(sib, new_doc, "transcript body",
                                        account_id="acct", input_source="cli")
    # Legacy singular keys removed
    assert "doc_kind:" not in merged.split("---\n", 2)[1]
    assert "drive_doc_id:" not in merged.split("---\n", 2)[1]
    # New list keys present, both kinds in order
    assert "doc_kinds:\n- notes\n- transcript" in merged
    # Both Doc ids carried forward in drive_docs
    assert "id: doc_notes_id" in merged
    assert "id: doc_tx_id" in merged
    # Existing body section preserved + new section appended
    assert "## Summary" in merged
    assert "## Transcript" in merged
    assert merged.index("## Summary") < merged.index("## Transcript")


def test_merge_into_sibling_preserves_body_of_existing_sections(tmp_path: Path) -> None:
    """The legacy section's body content must survive the merge — we are
    appending, not replacing."""
    legacy_body = "Action items:\n- Talk to Bob\n- Update roadmap"
    _write_legacy_file(tmp_path, drive_doc_id="notes_id", doc_kind="notes",
                       drive_doc_name="Pair – Notizen von Gemini", body=legacy_body)
    smap, _ = gmeet._scan_siblings(tmp_path)
    sib = list(smap.values())[0]
    new_doc = {"id": "tx_id", "name": "Pair – Transcript",
               "createdTime": "2026-05-15T10:05:00Z"}
    merged = gmeet._merge_into_sibling(sib, new_doc, "transcript body",
                                        account_id="acct", input_source="cli")
    for line in legacy_body.splitlines():
        assert line in merged
