"""Unit tests for core.markers — the sentinel-region splice primitive.

Covers exactly the three degenerate marker states the module promises defined
behaviour for (missing / duplicated / reversed) plus the happy paths of
find_region / replace_region / ensure_region / strip_region.
"""

from __future__ import annotations

import pytest

from core import markers

B = "<!-- x:begin -->"
E = "<!-- x:end -->"


# ── find_region ─────────────────────────────────────────────────────

def test_find_region_locates_full_span_markers_included():
    text = f"head\n{B}\ninner\n{E}\ntail"
    region = markers.find_region(text, B, E)
    assert region is not None
    assert text[region.start : region.end] == f"{B}\ninner\n{E}"


def test_find_region_missing_begin_returns_none():
    assert markers.find_region(f"only {E} here", B, E) is None


def test_find_region_missing_end_returns_none():
    assert markers.find_region(f"only {B} here", B, E) is None


def test_find_region_reversed_markers_returns_none():
    # end BEFORE begin — a bare .find(end) would point before begin and drive a
    # corrupting splice; find_region must reject it (searches end after begin).
    text = f"{E}\nstray\n{B}\n"
    assert markers.find_region(text, B, E) is None


def test_find_region_duplicated_uses_first_begin_and_first_end_after():
    text = f"{B}\none\n{E}\nmid\n{B}\ntwo\n{E}\n"
    region = markers.find_region(text, B, E)
    assert region is not None
    assert text[region.start : region.end] == f"{B}\none\n{E}"


def test_find_region_stray_end_before_valid_pair_still_found():
    # a leading stray end must not blind us to a genuine pair that follows.
    text = f"{E}\n{B}\nbody\n{E}\n"
    region = markers.find_region(text, B, E)
    assert region is not None
    assert text[region.start : region.end] == f"{B}\nbody\n{E}"


# ── replace_region ──────────────────────────────────────────────────

def test_replace_region_replaces_in_place():
    text = f"top\n\n{B}\nold\n{E}\n\nbottom"
    block = f"{B}\nnew\n{E}"
    out = markers.replace_region(text, B, E, block)
    assert out == f"top\n\n{B}\nnew\n{E}\n\nbottom"
    assert "old" not in out


def test_replace_region_reversed_treated_as_missing_appends():
    # reversed markers => not a region => append policy runs, no corruption.
    text = f"{E}\nx\n{B}\n"
    block = f"{B}\nfresh\n{E}"
    out = markers.replace_region(text, B, E, block, on_missing="append")
    assert out.endswith(block)
    assert out.count(B) == 2  # the stray begin survives; a real pair is appended


def test_replace_region_append_when_missing():
    out = markers.replace_region("body text\n", B, E, f"{B}\nq\n{E}")
    assert out == f"body text\n\n{B}\nq\n{E}"


def test_replace_region_append_on_empty_is_block_only():
    out = markers.replace_region("", B, E, f"{B}\nq\n{E}")
    assert out == f"{B}\nq\n{E}"


def test_replace_region_skip_when_missing():
    assert markers.replace_region("no markers", B, E, "blk", on_missing="skip") == "no markers"


def test_replace_region_raise_when_missing():
    with pytest.raises(ValueError, match="not found"):
        markers.replace_region("no markers", B, E, "blk", on_missing="raise")


def test_replace_region_is_idempotent_for_identical_block():
    block = f"{B}\nsame\n{E}"
    once = markers.replace_region(f"a\n\n{block}\n\nb", B, E, block)
    twice = markers.replace_region(once, B, E, block)
    assert once == twice


# ── ensure_region ───────────────────────────────────────────────────

def test_ensure_region_replaces_when_present():
    text = f"x\n{B}\nold\n{E}\ny"
    out = markers.ensure_region(
        text, B, E, f"{B}\nnew\n{E}", insert=lambda t, blk: t + "\n" + blk
    )
    assert "new" in out and "old" not in out
    assert out.count(B) == 1


def test_ensure_region_inserts_via_callback_when_absent():
    def insert(t: str, blk: str) -> str:
        return blk + "\n\n" + t  # prepend

    out = markers.ensure_region("body", B, E, f"{B}\nz\n{E}", insert=insert)
    assert out == f"{B}\nz\n{E}\n\nbody"


def test_ensure_region_reversed_markers_route_to_insert():
    calls: list[str] = []

    def insert(t: str, blk: str) -> str:
        calls.append("inserted")
        return t + blk

    text = f"{E}\n{B}\n"  # reversed → not a region
    markers.ensure_region(text, B, E, f"{B}\nz\n{E}", insert=insert)
    assert calls == ["inserted"]


# ── strip_region ────────────────────────────────────────────────────

def test_strip_region_removes_span_and_collapses_seam():
    text = f"before\n\n{B}\nbody\n{E}\n\nafter\n"
    out = markers.strip_region(text, B, E)
    assert B not in out and E not in out
    assert "before" in out and "after" in out


def test_strip_region_missing_is_noop():
    text = "no markers here\n"
    assert markers.strip_region(text, B, E) == text


def test_strip_region_reversed_is_noop():
    text = f"{E}\nx\n{B}\n"  # reversed → nothing stripped
    assert markers.strip_region(text, B, E) == text


def test_strip_region_at_end_of_file_leaves_trimmed_head():
    text = f"head content\n\n{B}\nbody\n{E}\n"
    out = markers.strip_region(text, B, E)
    assert out == "head content"
