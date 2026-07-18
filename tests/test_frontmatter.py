"""core/frontmatter — the single frontmatter grammar (C03).

Table-tests the ONE tolerance policy over the edge inputs that used to get
different answers from the router vs the classifier vs lint vs reports:
fence-at-EOF, ``--- `` trailing space, CRLF, quoted values, valueless keys,
malformed/non-dict YAML. Plus the write side: serialize round-trip and the
DECISIONS-2026-05-15 surgical `update_fields`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import frontmatter as fm_mod
from core.frontmatter import (
    FrontmatterError,
    backup,
    field,
    parse,
    parse_strict,
    serialize,
    split_fence,
    update_fields,
    write,
)


# ── split_fence ──────────────────────────────────────────────────────


class TestSplitFence:
    def test_no_fence(self):
        assert split_fence("just a note body") == (None, "just a note body")

    def test_standard(self):
        block, body = split_fence("---\ntype: note\n---\n\n# Hi\n")
        assert block == "type: note"
        assert body == "\n# Hi\n"

    def test_fence_at_eof_without_newline(self):
        block, body = split_fence("---\ntype: note\n---")
        assert block == "type: note"
        assert body == ""

    def test_unterminated_is_no_frontmatter(self):
        text = "---\ntype: note\nbody without closing fence"
        assert split_fence(text) == (None, text)

    def test_trailing_space_on_both_fences(self):
        block, body = split_fence("--- \ntype: note\n--- \nbody")
        assert block == "type: note"
        assert body == "body"

    def test_crlf(self):
        block, body = split_fence("---\r\ntype: note\r\n---\r\nbody")
        assert block == "type: note"
        assert body == "body"

    def test_four_dashes_is_not_a_fence(self):
        text = "---\ntype: note\n----\nbody"
        assert split_fence(text) == (None, text)

    def test_dashes_with_text_do_not_close(self):
        text = "---\ntype: note\n--- comment\nbody"
        assert split_fence(text) == (None, text)

    def test_empty_block(self):
        assert split_fence("---\n---\nbody") == ("", "body")


# ── parse / parse_strict ─────────────────────────────────────────────


class TestParse:
    def test_dict_and_body(self):
        fm, body = parse("---\ntype: note\ntags: [a, b]\n---\n\nbody\n")
        assert fm == {"type": "note", "tags": ["a", "b"]}
        assert body == "\nbody\n"

    def test_no_fence_returns_whole_text_as_body(self):
        assert parse("plain body") == ({}, "plain body")

    def test_malformed_yaml_tolerant(self):
        fm, body = parse("---\n{unclosed\n---\nbody")
        assert fm == {}
        assert body == "body"

    def test_non_dict_document_tolerant(self):
        fm, body = parse("---\n- just\n- a list\n---\nbody")
        assert fm == {}
        assert body == "body"

    def test_json_escaped_scalar_decodes(self):
        # The intents→triage live bug: json.dumps-written values are valid
        # YAML double-quoted scalars and MUST decode (umlauts + quotes).
        fm, _ = parse('---\nsummary: "M\\u00fcller sagt \\"hi\\""\n---\n')
        assert fm["summary"] == 'Müller sagt "hi"'


class TestParseStrict:
    def test_ok(self):
        assert parse_strict("---\na: 1\n---\nb")[0] == {"a": 1}

    @pytest.mark.parametrize(
        "text",
        [
            "no fence at all",
            "---\nunterminated: yes",
            "---\n{malformed\n---\nbody",
            "---\n- a\n- list\n---\nbody",
            "---\n---\nbody",  # empty block → None document → non-dict
        ],
    )
    def test_raises(self, text):
        with pytest.raises(FrontmatterError):
            parse_strict(text)


# ── field — the hot-path accessor (router ≡ classifier grammar) ──────


class TestField:
    def test_plain(self):
        assert field("---\ntype: calendar-rollup\n---\nx", "type") == "calendar-rollup"

    def test_double_and_single_quotes(self):
        assert field('---\ntype: "note"\n---\n', "type") == "note"
        assert field("---\ntype: 'note'\n---\n", "type") == "note"

    def test_value_with_spaces_and_punctuation(self):
        content = "---\ntitle: with spaces, commas! and punc.\n---\n"
        assert field(content, "title") == "with spaces, commas! and punc."

    def test_missing_key(self):
        assert field("---\ntype: note\n---\n", "title") is None

    def test_valueless_key(self):
        assert field("---\ntype:\n---\nbody", "type") is None
        assert field("---\ntype:   \n---\nbody", "type") is None

    def test_no_frontmatter(self):
        assert field("type: note in body", "type") is None

    def test_unterminated_fence(self):
        assert field("---\ntype: note\nno closing", "type") is None

    def test_fence_at_eof(self):
        assert field("---\ntype: note\n---", "type") == "note"

    def test_opening_fence_trailing_space(self):
        # Pre-C03 divergence: the router saw this type, the classifier did not.
        assert field("--- \ntype: memory-sync\n---\nx", "type") == "memory-sync"

    def test_crlf(self):
        assert field("---\r\ntype: transcript\r\n---\r\nx", "type") == "transcript"

    def test_only_first_fence_block_is_searched(self):
        content = "---\ntitle: real\n---\nbody\ntitle: fake\n"
        assert field(content, "title") == "real"

    def test_trailing_comment_stripped_on_unquoted(self):
        assert field("---\ntype: note  # classified\n---\n", "type") == "note"

    def test_hash_without_space_kept(self):
        assert field("---\nsource: https://x.de/a#frag\n---\n", "source") == "https://x.de/a#frag"

    def test_hash_inside_quotes_kept(self):
        assert field('---\ntitle: "a # b"\n---\n', "title") == "a # b"

    def test_key_is_regex_escaped(self):
        assert field("---\na.b: v\naxb: w\n---\n", "a.b") == "v"


# ── serialize / write ────────────────────────────────────────────────


class TestSerializeWrite:
    def test_round_trip(self):
        fm = {"title": "Takes — Jane", "type": "takes", "n": 3, "flag": False}
        text = serialize(fm, "# Body\n\n- line\n")
        fm2, body2 = parse(text)
        assert fm2 == fm
        assert body2 == "\n# Body\n\n- line\n"

    def test_unicode_kept_raw(self):
        text = serialize({"summary": "Müller prüft"}, "b")
        assert "Müller prüft" in text

    def test_long_scalar_not_folded(self):
        long = "word " * 60  # >80 chars would fold at yaml's default width
        text = serialize({"summary": long.strip()}, "b")
        assert f"summary: {long.strip()}\n" in text

    def test_body_normalized_single_blank_separator(self):
        # Leading blank lines in the body collapse — the take.py round-trip
        # used to GROW one blank line per append.
        text = serialize({"a": 1}, "\n\n# H\n")
        assert text == "---\na: 1\n---\n\n# H\n"
        assert parse(text)[1] == "\n# H\n"

    def test_empty_body(self):
        assert serialize({"a": 1}, "") == "---\na: 1\n---\n"

    def test_write_creates_parents(self, tmp_path: Path):
        target = tmp_path / "sub" / "f.md"
        write(target, {"type": "note"}, "body")
        assert target.read_text(encoding="utf-8") == "---\ntype: note\n---\n\nbody\n"


# ── update_fields — surgical writeback (DECISIONS 2026-05-15) ────────


class TestUpdateFields:
    def test_replaces_only_target_line(self, tmp_path: Path):
        f = tmp_path / "fact.md"
        f.write_text(
            '---\ntitle: "Operator picked quoting"\nstatus: negation\n'
            "applied: false\n---\n\nBody stays.\n",
            encoding="utf-8",
        )
        update_fields(f, applied="2026-07-18T10:00:00+02:00")
        text = f.read_text(encoding="utf-8")
        assert 'title: "Operator picked quoting"' in text  # untouched bytes
        assert "applied: false" not in text
        assert "Body stays.\n" in text
        fm, _ = parse(text)
        assert fm["applied"] == "2026-07-18T10:00:00+02:00"
        assert isinstance(fm["applied"], str)  # quoted → stays a string

    def test_appends_missing_key_before_close(self, tmp_path: Path):
        f = tmp_path / "fact.md"
        f.write_text("---\ntype: fact\n---\n\nB\n", encoding="utf-8")
        update_fields(f, last_reconciled="2026-07-18T10:00:00+02:00", updated="2026-07-18")
        fm, body = parse(f.read_text(encoding="utf-8"))
        assert fm["type"] == "fact"
        assert fm["last_reconciled"] == "2026-07-18T10:00:00+02:00"
        assert fm["updated"] == "2026-07-18"
        assert body == "\nB\n"

    def test_body_key_lines_untouched(self, tmp_path: Path):
        f = tmp_path / "r.md"
        f.write_text("---\nstatus: pending\n---\nstatus: decoy in body\n", encoding="utf-8")
        update_fields(f, status="accepted")
        text = f.read_text(encoding="utf-8")
        assert "status: accepted" in text
        assert "status: decoy in body" in text

    def test_no_fence_raises(self, tmp_path: Path):
        f = tmp_path / "x.md"
        f.write_text("no frontmatter", encoding="utf-8")
        with pytest.raises(FrontmatterError):
            update_fields(f, a="b")

    def test_multiline_value_rejected(self, tmp_path: Path):
        f = tmp_path / "x.md"
        f.write_text("---\na: 1\n---\n", encoding="utf-8")
        with pytest.raises(ValueError):
            update_fields(f, a="two\nlines")


class TestBackup:
    def test_backup_copies(self, tmp_path: Path):
        f = tmp_path / "f.md"
        f.write_text("content", encoding="utf-8")
        bak = backup(f)
        assert bak is not None and bak.exists()
        assert bak.name.startswith("f.md.bak.")
        assert bak.read_text(encoding="utf-8") == "content"

    def test_backup_missing_returns_none(self, tmp_path: Path):
        assert backup(tmp_path / "nope.md") is None


# ── router ≡ classifier identity on the same bytes ───────────────────


class TestRouterClassifierIdentity:
    """The C03 core claim: route and classify read type: through ONE grammar."""

    EDGE_INPUTS = (
        "---\ntype: memory-sync\n---\nbody",
        "--- \ntype: memory-sync\n---\nbody",     # trailing space on open fence
        "---\r\ntype: memory-sync\r\n---\r\nbody",  # CRLF
        "---\ntype: memory-sync\n---",              # fence at EOF
        '---\ntype: "memory-sync"\n---\nbody',      # quoted
        "---\ntype:\n---\nbody",                    # valueless
        "---\ntype: memory-sync\nno closing fence",
    )

    def test_route_and_classify_read_the_same_helper(self):
        from compile_stages import route

        for content in self.EDGE_INPUTS:
            assert route._frontmatter_type(content) == field(content, "type")

    def test_skip_list_gate_applies_on_crlf_and_trailing_space(self, monkeypatch):
        from core.config import CONFIG
        from compile_stages.route import Skip, decide_route

        monkeypatch.setattr(
            CONFIG.limits, "compile_skip_substrate_types", ("calendar-rollup",)
        )
        for content in (
            "---\r\ntype: calendar-rollup\r\n---\r\nstuff",
            "--- \ntype: calendar-rollup\n--- \nstuff",
        ):
            r = decide_route(Path("raw/notes/x.md"), content)
            assert isinstance(r, Skip)
            assert r.reason == "substrate_type_excluded_calendar-rollup"

    def test_classifier_sees_type_behind_tolerant_fence(self):
        from compile_stages.classify import classify

        sections = "".join(f"## M{i}\n\ntext\n\n" for i in range(4))
        content = f"--- \ntype: memory-sync\n---\n{sections}"
        result = classify(content, Path("raw/memories/m.md"))
        assert result.kind == "aggregated-memory"
        assert len(result.chunks) == 4


def test_module_all_exports_exist():
    for name in fm_mod.__all__:
        assert hasattr(fm_mod, name)
