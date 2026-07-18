"""Idempotent sentinel-marker region splicing — the one primitive behind every
``<!-- x:begin --> … <!-- x:end -->`` managed block in the engine.

A *sentinel region* is a span of text bracketed by a `begin` marker and an `end`
marker. Engine passes (backlinks footer, health-trends block, per-day summarize
button, agent-buttons dashboard region, per-session capture block, …) all own
such a region: they must be able to insert it once, replace it in place on
re-run, and strip it — while operator/compiler text *outside* the markers
survives untouched. Historically each site re-implemented this with a different
`str.find`/`str.index`/regex splice and a different (or missing) guard for the
degenerate cases, and one of those bugs — the first-occurrence `.index` splice
with NO ordering guard — writes corrupted garbage back when the end marker
precedes the begin marker. This module makes the location logic one deep,
table-tested function so every consumer inherits the same defined behaviour.

Defined behaviour for the three degenerate marker states (see `find_region`):

- **missing** — either marker absent → region not found (`None`); callers pick a
  policy (append / insert-at-anchor / leave unchanged / raise). Never a partial
  splice.
- **reversed** — an `end` marker that occurs *before* the `begin` marker is
  ignored: `find_region` searches for `end` strictly *after* `begin`, so a lone
  stray `end` can never drive a reversed splice.
- **duplicated** — the first `begin` and the first `end` after it win; trailing
  duplicate markers are left in the surrounding text for the caller to notice.

Callers own the *bytes* of the block (markers included, newline discipline);
this module owns only *where* the region is and the degenerate-case contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

OnMissing = Literal["append", "skip", "raise"]


@dataclass(frozen=True)
class Region:
    """Half-open span of a sentinel region within some text.

    ``start`` indexes the first character of the begin marker; ``end`` indexes
    one past the last character of the end marker (so ``text[start:end]`` is the
    whole region, markers included).
    """

    start: int
    end: int


def find_region(text: str, begin: str, end: str) -> Region | None:
    """Locate the first well-formed ``begin`` … ``end`` span in ``text``.

    Returns ``None`` — never a partial or reversed span — when the begin marker
    is absent, or when no end marker occurs after it. See the module docstring
    for the missing / reversed / duplicated contract.
    """
    b = text.find(begin)
    if b == -1:
        return None
    e = text.find(end, b + len(begin))
    if e == -1:
        return None
    return Region(start=b, end=e + len(end))


def replace_region(
    text: str,
    begin: str,
    end: str,
    block: str,
    *,
    on_missing: OnMissing = "append",
    separator: str = "\n\n",
) -> str:
    """Replace the located ``begin`` … ``end`` region with ``block``.

    ``block`` must carry the markers itself — this function owns only the span
    location and the missing-region policy, not the block's contents.

    When no region is present, ``on_missing`` decides:

    - ``"append"`` — append ``separator`` + ``block`` after the existing text
      (trailing newlines of the existing text are normalized away first so the
      join is exactly ``separator``); an empty ``text`` yields just ``block``.
    - ``"skip"`` — return ``text`` unchanged.
    - ``"raise"`` — raise ``ValueError``.
    """
    region = find_region(text, begin, end)
    if region is not None:
        return text[: region.start] + block + text[region.end :]
    if on_missing == "append":
        base = text.rstrip("\n")
        return base + separator + block if base else block
    if on_missing == "skip":
        return text
    raise ValueError(
        f"markers.replace_region: region {begin!r}..{end!r} not found in text"
    )


def ensure_region(
    text: str,
    begin: str,
    end: str,
    block: str,
    *,
    insert: Callable[[str, str], str],
) -> str:
    """Replace the region if present, else insert it via the ``insert`` callback.

    ``insert(text, block)`` returns the new text with ``block`` placed wherever
    the caller wants it (after an H1, before another sentinel, appended, …). The
    replace path is reversed-marker safe (unlike a bare ``find``/``index``
    splice); the insert path is entirely the caller's placement policy.
    """
    region = find_region(text, begin, end)
    if region is not None:
        return text[: region.start] + block + text[region.end :]
    return insert(text, block)


def strip_region(text: str, begin: str, end: str) -> str:
    """Remove the ``begin`` … ``end`` region and collapse the seam.

    Text before the region is right-stripped; text after it keeps a single
    newline boundary. Idempotent: with no region present, ``text`` is returned
    unchanged. The result is *not* guaranteed to end in a newline — callers that
    need a trailing newline add one.
    """
    region = find_region(text, begin, end)
    if region is None:
        return text
    head = text[: region.start].rstrip()
    tail = text[region.end :]
    if head and not tail.startswith("\n"):
        return head + tail
    return head + tail.lstrip("\n")
