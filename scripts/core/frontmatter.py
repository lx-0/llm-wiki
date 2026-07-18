"""The engine's single frontmatter grammar (C03).

Every module that reads or writes a leading YAML frontmatter block goes through
this seam. Before C03 the engine carried ~30 hand-rolled parse sites with
divergent fence/value/tolerance grammars — the router and the classifier could
legally read different ``type:`` answers from the same bytes, and the
intents→triage record seam wrote JSON-escaped values a naive reader garbled.
One grammar, one test surface; divergence is structurally impossible.

Tolerance policy (the ONE policy — do not fork it at call sites):

- **Opening fence**: the text's first line is ``---``. Trailing spaces/tabs and
  a CRLF line ending are tolerated.
- **Closing fence**: the next line consisting of ``---`` (trailing whitespace
  tolerated), *including* a fence at EOF without a trailing newline. A line
  like ``----`` or ``--- text`` does NOT close the fence.
- **No closing fence** → the text has no frontmatter; the whole text is body.
- **Malformed YAML / non-dict document**: tolerant callers (`parse`) get
  ``({}, body)``; strict callers (`parse_strict`) get `FrontmatterError`.
- **Body** = everything after the closing fence line's newline. The
  conventional blank separator line after the fence stays part of the body.

Read/write API:

- `split_fence(text)` — fence split only, no YAML parse.
- `parse(text)` — tolerant ``(dict, body)``.
- `parse_strict(text)` — raises `FrontmatterError` (for specs/reports that must
  not half-read a malformed file).
- `field(content, key)` — regex-only scalar accessor for hot paths
  (compile routing); no YAML import.
- `serialize(fm, body)` / `write(path, fm, body)` — write-anew round-trip.
  Per DECISIONS 2026-05-15, ``yaml.safe_dump`` is legal for write-anew ONLY.
- `update_fields(path, **fields)` — surgical single-key writeback: regex
  line-replace inside the fence (append-before-close for missing keys),
  everything else stays byte-identical. This is the only legal way to update
  keys in an existing on-disk file (DECISIONS 2026-05-15).
- `backup(path)` — timestamped ``.bak.<ts>`` sibling copy.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

__all__ = [
    "FrontmatterError",
    "backup",
    "field",
    "parse",
    "parse_strict",
    "serialize",
    "split_fence",
    "update_fields",
    "write",
]


class FrontmatterError(ValueError):
    """Strict-mode failure: missing fence, malformed YAML, or non-dict document."""


# Fence grammar — the single source of truth (see module docstring).
_OPEN_RE = re.compile(r"\A---[ \t]*\r?\n")
_CLOSE_RE = re.compile(r"^---[ \t]*\r?$", re.MULTILINE)

# Long scalars must stay on one line: line-oriented consumers (triage UIs,
# `update_fields`' line-replace, JS frontmatter readers) break on YAML folding.
_DUMP_WIDTH = 1_000_000


def split_fence(text: str) -> tuple[str | None, str]:
    """Split a leading YAML fence into ``(block, body)``.

    ``block`` is the raw text between the fences (final line terminator
    removed), or ``None`` when the text has no frontmatter. ``body`` follows
    the closing fence line; without a fence it is the whole text.
    """
    m = _OPEN_RE.match(text)
    if not m:
        return None, text
    rest = text[m.end():]
    close = _CLOSE_RE.search(rest)
    if close is None:
        return None, text
    block = rest[: close.start()]
    if block.endswith("\r\n"):
        block = block[:-2]
    elif block.endswith("\n"):
        block = block[:-1]
    body = rest[close.end():]
    if body.startswith("\n"):
        body = body[1:]
    return block, body


def parse(text: str) -> tuple[dict, str]:
    """Tolerant parse: ``(frontmatter_dict, body)``.

    No fence → ``({}, text)``. Malformed YAML or a non-dict document →
    ``({}, body)``. Values carry YAML types (lists, bools, dates) — coerce at
    the call site when a flat str-view is needed.
    """
    block, body = split_fence(text)
    if block is None:
        return {}, text
    import yaml  # local import keeps the hot-path module load cheap

    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return {}, body
    return (data, body) if isinstance(data, dict) else ({}, body)


def parse_strict(text: str) -> tuple[dict, str]:
    """Strict parse for specs/reports: raises `FrontmatterError` instead of
    degrading to ``{}`` on missing fence, malformed YAML, or non-dict."""
    block, body = split_fence(text)
    if block is None:
        raise FrontmatterError("no frontmatter fence")
    import yaml

    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"malformed frontmatter YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise FrontmatterError(
            f"frontmatter is not a mapping (got {type(data).__name__})"
        )
    return data, body


# Per-key compiled pattern cache for the hot path.
_FIELD_RES: dict[str, re.Pattern[str]] = {}


def field(content: str, key: str) -> str | None:
    """Fast regex scalar accessor for hot paths — no YAML parse, no yaml import.

    Returns the first ``<key>:`` value inside the leading fence, or ``None``
    when there is no fence, no key, or an empty value. Matched surrounding
    quote pairs are stripped; on unquoted values a trailing ``  # comment`` is
    dropped (YAML comment rule: ``#`` after whitespace). Single-line scalars
    only — lists/nested structures need `parse`.

    The router and the classifier both read through this function — that is
    the C03 guarantee that they see identical semantics on the same bytes.
    """
    block, _body = split_fence(content)
    if block is None:
        return None
    pat = _FIELD_RES.get(key)
    if pat is None:
        pat = re.compile(rf"^{re.escape(key)}:[ \t]*(.*?)[ \t\r]*$", re.MULTILINE)
        _FIELD_RES[key] = pat
    m = pat.search(block)
    if not m:
        return None
    value = m.group(1)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    else:
        value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
    return value or None


def serialize(fm: dict, body: str) -> str:
    """Render the canonical on-disk shape: ``---`` fence, YAML block (insertion
    order, unicode kept raw, no line folding), one blank separator line, body
    with a single trailing newline. Write-anew only (DECISIONS 2026-05-15)."""
    import yaml

    block = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, width=_DUMP_WIDTH
    ).rstrip()
    body_out = body.strip("\n")
    if body_out:
        return f"---\n{block}\n---\n\n{body_out}\n"
    return f"---\n{block}\n---\n"


def write(path: Path, fm: dict, body: str) -> None:
    """Write a file anew from ``(fm, body)`` (creates parent dirs).

    For updating keys in an EXISTING file use `update_fields` — round-tripping
    on-disk YAML through safe_dump destroys operator formatting
    (DECISIONS 2026-05-15)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize(fm, body), encoding="utf-8")


def _scalar_line(key: str, value: object) -> str:
    """One ``key: value`` line, YAML-quoted by yaml itself so the value reads
    back with the same type (timestamps/numbers-as-strings stay strings)."""
    import yaml

    dumped = yaml.safe_dump(
        {key: value}, sort_keys=False, allow_unicode=True, width=_DUMP_WIDTH
    ).rstrip("\n")
    if "\n" in dumped:
        raise ValueError(
            f"update_fields only writes single-line scalars; {key}={value!r} "
            "serializes to multiple lines"
        )
    return dumped


def update_fields(path: Path, **fields: object) -> None:
    """Surgical single-key writeback (DECISIONS 2026-05-15).

    Each key's line inside the fence is regex line-replaced in place; keys not
    present are appended before the closing fence. Everything else — operator
    formatting, comments, key order, the body — stays byte-identical. Raises
    `FrontmatterError` when the file has no parseable fence."""
    text = path.read_text(encoding="utf-8")
    m = _OPEN_RE.match(text)
    if not m:
        raise FrontmatterError(f"no frontmatter fence in {path}")
    rest = text[m.end():]
    close = _CLOSE_RE.search(rest)
    if close is None:
        raise FrontmatterError(f"unterminated frontmatter fence in {path}")
    block = rest[: close.start()]  # keeps its trailing newline
    for key, value in fields.items():
        line = _scalar_line(key, value)
        pat = re.compile(rf"^{re.escape(key)}:[^\n]*$", re.MULTILINE)
        if pat.search(block):
            block = pat.sub(lambda _m: line, block, count=1)
        else:
            if block and not block.endswith("\n"):
                block += "\n"
            block += line + "\n"
    path.write_text(text[: m.end()] + block + rest[close.start():], encoding="utf-8")


def backup(path: Path) -> Path | None:
    """Timestamped sibling copy ``<name>.bak.<ts>``; ``None`` when path missing."""
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak.{ts}")
    shutil.copy2(path, bak)
    return bak
