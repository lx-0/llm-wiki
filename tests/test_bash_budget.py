"""The bash budget (M034 exit criterion 1): `wiki` is a bootstrap of at most 150 lines, and
there is no bash library beside it.

Every command is Python since M034-S05-T03, and the last library, `lib/common.sh`, folded
into `wiki` in T05. What is left in bash is what has to run before Python can: resolving
the entry's own path, the vault guard, the engine environment's location (the bootstrap
needs it to find the interpreter), and the hop into `scripts/cli.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
BUDGET = 150


def test_wiki_is_a_bootstrap_of_at_most_150_lines():
    lines = (ENGINE / "wiki").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= BUDGET, f"wiki is {len(lines)} lines; the budget is {BUDGET}"


def test_there_is_no_bash_library():
    assert not (ENGINE / "lib").exists(), sorted(p.name for p in (ENGINE / "lib").iterdir())


def test_the_bootstrap_sources_nothing():
    """A `source` / `.` line would bring a library back by another name."""
    sourced = [
        line.strip()
        for line in (ENGINE / "wiki").read_text(encoding="utf-8").splitlines()
        if re.match(r"\s*(source|\.)\s+\S", line)
    ]
    assert sourced == []
