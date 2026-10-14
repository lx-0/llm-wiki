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

import re
from pathlib import Path

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


def test_empty_fallback_is_a_keyword() -> None:
    """The health collector's account slug falls back to "account", not "untitled"."""
    assert slugify("", ascii_only=True, empty="account") == "account"
    assert slugify("???", ascii_only=True, empty="account") == "account"
    assert slugify("Oura Main", ascii_only=True, empty="account") == "oura-main"
    assert slugify("", empty="note") == "note"


def test_curiosity_request_slug_shape() -> None:
    """`raw/requests/request-<slug>-<date>.json` — formerly an inline `re.sub` cut at 40."""
    topic = "Why did the Q3 pipeline review stall? (follow-up with Sid)"
    assert slugify(topic, max_len=40, ascii_only=True) == "why-did-the-q3-pipeline-review-stall-fol"


# ── no second slug grammar outside core/utils ─────────────────────────────────

_ASCII_GRAMMAR = re.compile(r"\[\^a-z0-9\]\+")
# publish/corpus.server_slug is an exact port of context-mcp's slugifySkillName (NFKD fold +
# diacritics stripped + the same run rule) — the SERVER's grammar, pinned as a fixpoint in
# tests/test_publish_corpus.py; it is not a copy of ours and must not drift towards it.
_ALLOWED = {"scripts/core/utils.py", "scripts/publish/corpus.py"}


def test_no_second_slug_grammar_outside_the_seam() -> None:
    repo = Path(__file__).resolve().parent.parent
    offenders = [
        f"{p.relative_to(repo)}:{n}"
        for p in sorted((repo / "scripts").rglob("*.py"))
        if str(p.relative_to(repo)) not in _ALLOWED
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if _ASCII_GRAMMAR.search(line)
    ]
    assert offenders == [], "slug grammar copies outside core/utils.slugify:\n" + "\n".join(
        offenders
    )
