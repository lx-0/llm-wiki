"""Pre-compile substrate classifier.

Decides the compile shape for a raw file BEFORE the LLM call:

- ``aggregated-memory`` — memory-seed/memory-sync substrate with N>3
  H2 sections (each section = one independent memory). Compiles
  per-chunk so the 25-turn budget binds per memory, not per aggregate.
- ``instructions`` — AGENTS.md / CLAUDE.md / README.md content
  accidentally ingested into raw/memories/ (these are project agent
  instructions, not Claude-Code memories). Routed to compile_instructions.
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


ClassifyKind = Literal["aggregated-memory", "single"]


@dataclass
class ClassifyResult:
    kind: ClassifyKind
    chunks: list[str]


_INSTRUCTIONS_SUFFIXES = ("__AGENTS.md", "__CLAUDE.md", "__README.md")
_INSTRUCTIONS_ORIGINS = ("/AGENTS.md", "/CLAUDE.md", "/README.md")
_INSTRUCTIONS_H1_HINTS = ("# AGENTS.md", "# CLAUDE.md", "# README.md")
_AGGREGATED_MIN_SECTIONS = 4
_AGGREGATED_MEMORY_TYPES = ("memory-seed", "memory-sync")


def classify(content: str, source: Path) -> ClassifyResult:
    fm_type = _frontmatter_type(content)
    if fm_type in _AGGREGATED_MEMORY_TYPES:
        sections = _split_at_h2(content)
        if len(sections) >= _AGGREGATED_MIN_SECTIONS:
            return ClassifyResult(kind="aggregated-memory", chunks=sections)
    return ClassifyResult(kind="single", chunks=[content])


def _looks_like_instructions(content: str, source: Path) -> bool:
    name = source.name
    if name.endswith(_INSTRUCTIONS_SUFFIXES):
        return True
    origin = _frontmatter_field(content, "origin") or ""
    if any(origin.endswith(s) for s in _INSTRUCTIONS_ORIGINS):
        return True
    body_head = content[:500]
    return any(h in body_head for h in _INSTRUCTIONS_H1_HINTS)


def _split_at_h2(content: str) -> list[str]:
    fm_match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
    if fm_match:
        frontmatter = fm_match.group(0)
        body = content[fm_match.end():]
    else:
        frontmatter = ""
        body = content
    parts = re.split(r"(?=^## )", body, flags=re.MULTILINE)
    pre_h2 = parts[0] if parts and not parts[0].startswith("## ") else ""
    sections = [p for p in parts if p.startswith("## ")]
    if not sections:
        return [content]
    chunks = []
    for i, section in enumerate(sections):
        if i == 0 and pre_h2.strip():
            chunks.append(frontmatter + pre_h2 + section)
        else:
            chunks.append(frontmatter + section)
    return chunks


def _frontmatter_type(content: str) -> str | None:
    return _frontmatter_field(content, "type")


def _frontmatter_field(content: str, key: str) -> str | None:
    fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return None
    fm = fm_match.group(1)
    for line in fm.splitlines():
        m = re.match(rf"^{re.escape(key)}:\s*(.+?)\s*$", line)
        if m:
            value = m.group(1)
            if (value.startswith("'") and value.endswith("'")) or \
               (value.startswith('"') and value.endswith('"')):
                value = value[1:-1]
            return value
    return None
