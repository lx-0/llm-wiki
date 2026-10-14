"""`core.utils.slugify` is the engine's one slug function (M033-S03-T03).

Two grammars are load-bearing for operator filenames and both live here, selected by a
keyword. The default keeps Unicode word characters and drops punctuation — it names
`knowledge/facts/<slug>.md`, `knowledge/takes/<slug>.md`, voice notes and html ingests. The
collectors' filename grammar (`ascii_only=True`, formerly four byte-identical private
copies in jamie / gmeet / calendar / youtube) maps every run of non-`[a-z0-9]` to `-`,
never ends a cut in `-`, and falls back to `untitled`. The inputs below mirror the shapes
behind real vault filenames (recomputed from the operator vault as evidence in the T03
summary).
"""

from __future__ import annotations

import pytest

from core.utils import slugify


@pytest.mark.parametrize(
    ("text", "max_len", "expected"),
    [
        ("Friday Meeting", 60, "friday-meeting"),
        (
            "Vollautomatische Softwareentwicklung ist möglich",
            60,
            "vollautomatische-softwareentwicklung-ist-m-glich",
        ),
        (
            "Yesterday Tech Deep Dive with Alex – 2025/12/03 11:29 CET",
            60,
            "yesterday-tech-deep-dive-with-alex-2025-12-03-11-29-cet",
        ),
        ("Alex × Sid", 60, "alex-sid"),
        ("Don't Panic", 60, "don-t-panic"),
        ("", 60, "untitled"),
        ("---", 60, "untitled"),
        ("a b a b a b", 5, "a-b-a"),  # a cut never ends in a dash
        (
            "BIG 3 SUPER AGENT: Gemini 2.5 Computer Use, OpenAI Realtime API, Claude",
            50,
            "big-3-super-agent-gemini-2-5-computer-use-openai-r",
        ),
    ],
)
def test_collector_filename_grammar(text: str, max_len: int, expected: str) -> None:
    assert slugify(text, max_len=max_len, ascii_only=True) == expected


@pytest.mark.parametrize(
    ("text", "max_len", "expected"),
    [
        ("Hello World", None, "hello-world"),
        ("José García-López", None, "josé-garcía-lópez"),  # facts / takes identity keeps accents
        ("Don't Panic", None, "dont-panic"),
        ("snake_case  and   spaces", None, "snake-case-and-spaces"),
        ("a b a b a b", 5, "a-b-a"),
        ("a-b-c", 4, "a-b-"),  # the default cut is a plain slice (existing filenames)
        ("", None, ""),
    ],
)
def test_default_grammar_unchanged(text: str, max_len: int | None, expected: str) -> None:
    assert slugify(text, max_len=max_len) == expected
