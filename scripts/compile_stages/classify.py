"""Pre-compile substrate classifier.

Decides the compile shape for a raw file BEFORE the LLM call:

- ``aggregated-memory`` — memory-seed/memory-sync substrate with N>3
  H2 sections (each section = one independent memory). Compiles
  per-chunk so the 25-turn budget binds per memory, not per aggregate.
- ``single`` — every other substrate; one compile call as before.

raw/ is RAW: this module never mutates source files. Splitting and
re-attaching frontmatter to chunks happens in memory, the substrate file
on disk stays byte-identical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from core import frontmatter


ClassifyKind = Literal["aggregated-memory", "single"]


@dataclass
class ClassifyResult:
    kind: ClassifyKind
    chunks: list[str]


_AGGREGATED_MIN_SECTIONS = 4
_AGGREGATED_MEMORY_TYPES = ("memory-seed", "memory-sync")


def classify(content: str, source: Path) -> ClassifyResult:
    fm_type = _frontmatter_type(content)
    if fm_type in _AGGREGATED_MEMORY_TYPES:
        sections = _split_at_h2(content)
        if len(sections) >= _AGGREGATED_MIN_SECTIONS:
            return ClassifyResult(kind="aggregated-memory", chunks=sections)
    return ClassifyResult(kind="single", chunks=[content])


def _split_at_h2(content: str) -> list[str]:
    # Fence detection via the single core.frontmatter grammar (C03).
    # `split_fence` returns the body as an exact suffix of `content`, so the
    # raw fence prefix (re-attached to every chunk) is the remaining head —
    # the substrate file itself is never re-serialized.
    block, body = frontmatter.split_fence(content)
    fence_prefix = content[: len(content) - len(body)] if block is not None else ""
    parts = re.split(r"(?=^## )", body, flags=re.MULTILINE)
    pre_h2 = parts[0] if parts and not parts[0].startswith("## ") else ""
    sections = [p for p in parts if p.startswith("## ")]
    if not sections:
        return [content]
    chunks = []
    for i, section in enumerate(sections):
        if i == 0 and pre_h2.strip():
            chunks.append(fence_prefix + pre_h2 + section)
        else:
            chunks.append(fence_prefix + section)
    return chunks


def _frontmatter_type(content: str) -> str | None:
    """`type:` scalar via the single core.frontmatter grammar (C03) — the
    identical accessor the router uses, so the same bytes can never get a
    different answer here than in `decide_route`."""
    return frontmatter.field(content, "type")
