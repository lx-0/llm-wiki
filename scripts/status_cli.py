"""`wiki status` (M034-S03-T05; was the bash `cmd_status`, held to the bash oracle's `status`
golden): the config summary over the hooks table. The dispatcher prints the `wiki status`
banner; `config_cli.status` prints its own."""

from __future__ import annotations

import sys

import config_cli
import hooks_cli
from core.console import say


def main() -> int:
    config_cli.status()
    say()
    hooks_cli.status_table()
    return 0


if __name__ == "__main__":
    sys.exit(main())
