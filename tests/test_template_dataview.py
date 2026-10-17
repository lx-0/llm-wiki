"""Every Dataview query the vault templates ship keeps its clauses apart.

160f641 (2026-05-16) lost a newline in the four MOC templates —
`WHERE compile_role != "final-only"SORT file.name ASC`, the clause keyword glued to the
string before it — and every seeded vault carried it (M034-S06-T07).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
_BLOCK = re.compile(r"```dataview\n(.*?)```", re.DOTALL)
# A clause keyword straight after a quote, bracket or word character, no space between.
_GLUED = re.compile(r"[\"')\w](FROM|WHERE|SORT|GROUP BY|FLATTEN|LIMIT)\b")


def glued_clauses(text: str) -> list[str]:
    return [m.group(0) for block in _BLOCK.findall(text) for m in _GLUED.finditer(block)]


_WITH_QUERIES = sorted(
    p for p in TEMPLATES.rglob("*.md") if "```dataview" in p.read_text(encoding="utf-8")
)


def test_the_templates_ship_dataview_queries():
    assert len(_WITH_QUERIES) >= 5


@pytest.mark.parametrize("path", _WITH_QUERIES, ids=lambda p: str(p.relative_to(TEMPLATES)))
def test_dataview_clauses_are_apart(path: Path):
    assert glued_clauses(path.read_text(encoding="utf-8")) == []
