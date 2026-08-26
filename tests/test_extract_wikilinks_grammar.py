"""`extract_wikilinks` must share the ONE wikilink grammar.

The 2026-08-26 bash-bracket guard was added to `core.links.WIKILINK_RE` and
its commit claimed "every consumer inherits via the regex". It didn't: lint,
links_audit and compile route all go through `core.utils.extract_wikilinks`,
which carried a second, looser regex — so the shell-test broken_link errors
the fix was written for survived it (10 still in the live lint results after
the guarded engine was deployed). One grammar, one place.
"""

from __future__ import annotations

import pytest

from core.utils import extract_wikilinks

_SHELL_LINES = [
    'if [[ -f "$logfile" ]]; then',
    '[[ "$status" == "complete" ]]',
    "[[ $size -gt 104857600 ]]",
    "[[ ! -o monitor ]]",
    "[[! -o monitor]]",
    "`[[ ... ]]`",
]


@pytest.mark.parametrize("line", _SHELL_LINES)
def test_shell_tests_are_not_extracted(line: str) -> None:
    assert extract_wikilinks(line) == []


def test_real_links_still_extracted_with_anchor_and_alias() -> None:
    text = (
        "see [[concepts/foo]] and [[bar|Bar Label]]\n"
        "plus [[baz#Section]] and an embed ![[diagram.png]]\n"
    )
    assert extract_wikilinks(text) == [
        "concepts/foo", "bar|Bar Label", "baz#Section", "diagram.png",
    ]


def test_round_trips_through_link_target() -> None:
    """The consumers pair extract_wikilinks with link_target; the raw string
    handed back must still resolve to the bare target."""
    from core.links import link_target

    raws = extract_wikilinks("[[a/b|Alias]] [[c/d#Head]] [[e]]")
    assert [link_target(r) for r in raws] == ["a/b", "c/d", "e"]


def test_table_escaped_pipe_survives() -> None:
    from core.links import link_target

    raws = extract_wikilinks(r"| [[concepts/foo\|Foo]] | row |")
    assert len(raws) == 1
    assert link_target(raws[0]) == "concepts/foo"
