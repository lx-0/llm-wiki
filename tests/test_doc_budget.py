"""The surface budget (M034 exit criterion 7): `README.md` at most 300 lines, `AGENTS.md`
at most 250.

README is read by someone deciding whether to use the engine, and by the operator who
installs and runs it. AGENTS.md is read by whoever changes the code, human or agent. Each
file's Contents names those readers per section. What only the internals need lives in
`docs/` (`engine-layout.md` file by file, `FEATURES.md` per feature, `cli.md` per command,
`config.md` per knob). Before the cut, at M034-S06-T05: 378 and 326 lines.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(("name", "budget"), [("README.md", 300), ("AGENTS.md", 250)])
def test_the_surface_stays_within_its_budget(name: str, budget: int):
    lines = (ENGINE / name).read_text(encoding="utf-8").splitlines()
    assert len(lines) <= budget, f"{name} is {len(lines)} lines; the budget is {budget}"
