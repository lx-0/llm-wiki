"""`docs/cli.md` is the full command reference: every catalogue command has a row there.

The catalogue (`cli_catalog.COMMANDS`) is the one table behind `wiki help` and the home menu
(M034 exit criterion 4). cli.md is written by hand beside it, and at M034-S06-T06 ten
commands had never been given a row: auth, backfill, bridge, dream-entity,
install-shortcut, pin, preprocess, stats, take, triage. A new command now needs its row
before the suite passes.
"""

from __future__ import annotations

import re
from pathlib import Path

import cli_catalog

CLI_MD = Path(__file__).resolve().parent.parent / "docs" / "cli.md"


def test_every_catalogue_command_has_a_row_in_cli_md():
    text = CLI_MD.read_text(encoding="utf-8")
    absent = [
        command.name
        for command in cli_catalog.COMMANDS
        if not re.search(rf"`wiki {re.escape(command.name)}(?=[\s`\[])", text)
    ]
    assert absent == [], f"docs/cli.md shows no `wiki <name>` for: {', '.join(absent)}"
