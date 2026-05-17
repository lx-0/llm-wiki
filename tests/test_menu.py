"""Tests for scripts/menu.py — catalog structural integrity + helpers.

The interactive prompt_toolkit flow is not unit-tested (it would require
a fake terminal); these tests focus on the dispatch catalog and the
pure helpers, which are where regressions silently break things.
"""

from __future__ import annotations

import pytest


def test_quick_actions_single_char_keys():
    import menu

    for key, *_ in menu.QUICK_ACTIONS:
        assert len(key) == 1, f"quick action key {key!r} must be single char"


def test_quick_actions_have_valid_dispatch():
    import menu

    for _key, _label, _desc, dispatch in menu.QUICK_ACTIONS:
        _assert_valid_dispatch(dispatch)


def test_categories_single_char_keys():
    import menu

    for letter in menu.CATEGORIES:
        assert len(letter) == 1, f"category key {letter!r} must be single char"


def test_categories_have_label_and_entries():
    import menu

    for letter, (label, entries) in menu.CATEGORIES.items():
        assert isinstance(label, str) and label, f"category {letter} missing label"
        assert isinstance(entries, list) and entries, f"category {letter} has no entries"


def test_all_dispatch_specs_valid():
    import menu

    for letter, (_label, entries) in menu.CATEGORIES.items():
        for eid, _l, _d, dispatch in entries:
            _assert_valid_dispatch(dispatch), f"{letter}/{eid}"


def test_prompt_dispatches_have_arg_placeholder():
    """Every (prompt, label, args) spec must have at least one {arg}."""
    import menu

    for source in (
        ("QUICK", menu.QUICK_ACTIONS),
        *(("CAT-" + letter, entries) for letter, (_l, entries) in menu.CATEGORIES.items()),
    ):
        for entry in source[1]:
            dispatch = entry[-1]
            if isinstance(dispatch, tuple) and dispatch[0] == "prompt":
                _, _label, args = dispatch
                assert any("{arg}" in a for a in args), (
                    f"{source[0]} prompt spec without {{arg}}: {entry!r}"
                )


def test_special_handlers_resolved():
    """Every (special, name) reference must have a handler registered."""
    import menu

    referenced: set[str] = set()
    sources = [menu.QUICK_ACTIONS]
    for _letter, (_label, entries) in menu.CATEGORIES.items():
        sources.append(entries)
    for src in sources:
        for entry in src:
            dispatch = entry[-1]
            if isinstance(dispatch, tuple) and dispatch[0] == "special":
                referenced.add(dispatch[1])

    missing = referenced - menu._SPECIAL_HANDLERS.keys()
    assert not missing, f"special handlers referenced but not registered: {missing}"


def test_render_status_line_with_full_status():
    import menu

    s = menu.render_status_line({
        "articles": 384,
        "last_compile_ago": "4h",
        "ollama_reachable": True,
    })
    assert "384 articles" in s
    assert "last compile 4h ago" in s
    assert "ollama ✓" in s


def test_render_status_line_singular():
    import menu

    s = menu.render_status_line({"articles": 1})
    assert "1 article" in s and "articles" not in s


def test_render_status_line_empty_status():
    import menu

    assert menu.render_status_line({}) == ""


def test_render_status_line_ollama_down():
    import menu

    s = menu.render_status_line({"ollama_reachable": False})
    assert "ollama ✗" in s


def test_flatten_for_fuzzy_covers_all_entries():
    import menu

    flat = menu._flatten_for_fuzzy()
    cat_entries = sum(len(entries) for _l, entries in menu.CATEGORIES.values())
    expected = cat_entries + len(menu.QUICK_ACTIONS)
    assert len(flat) == expected
    # all ids are unique
    ids = [row[0] for row in flat]
    assert len(set(ids)) == len(ids), "duplicate catalog ids in fuzzy flatten"


def test_home_state_n_suggestions_tracks_list():
    import menu

    state = menu.HomeState()
    assert state.n_suggestions() == 0
    state.suggestions = [{"key": "1"}, {"key": "2"}, {"key": "3"}]
    assert state.n_suggestions() == 3


# ── helpers ────────────────────────────────────────────────────────


def _assert_valid_dispatch(dispatch):
    if isinstance(dispatch, list):
        assert all(isinstance(a, str) for a in dispatch), f"list args must all be str: {dispatch}"
        assert dispatch, "list dispatch must be non-empty"
        return
    if isinstance(dispatch, tuple):
        kind = dispatch[0]
        if kind == "prompt":
            assert len(dispatch) == 3, f"prompt spec must be (prompt, label, args): {dispatch}"
            _, label, args = dispatch
            assert isinstance(label, str) and label
            assert isinstance(args, list) and args
            return
        if kind == "special":
            assert len(dispatch) == 2, f"special spec must be (special, name): {dispatch}"
            assert isinstance(dispatch[1], str) and dispatch[1]
            return
        pytest.fail(f"unknown dispatch tuple kind: {kind!r}")
    pytest.fail(f"dispatch must be list or tuple, got {type(dispatch).__name__}: {dispatch!r}")
