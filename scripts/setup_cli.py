"""`wiki setup` — first-time setup: the config wizard, then the hooks step (M034-S02-T03; was
the bash `cmd_setup`, held to the bash oracle's `setup-wizard` / `setup-with-hooks` goldens).
The dispatcher prints the banner (`wiki setup` + its subtitle) before this runs.

The hooks step is `hooks_cli.install`, in-process since hooks are Python (M034-S03-T05). It
reads its answers from the same stdin as the wizard: both read byte by byte
(`core/console.read_line`), so neither consumes the other's — `setup-with-hooks` pipes both in
one stream.
"""

from __future__ import annotations

import sys

import config_cli
import hooks_cli
from core.console import confirm, info


def setup(*, fd: int = 0) -> int:
    """The wizard, then "install hooks?"; the hooks installer's exit code is setup's."""
    config_cli.wizard(fd=fd)
    print()
    sys.stdout.flush()
    if confirm("Now install hooks into agent configs?", default=True, fd=fd):
        return hooks_cli.install(fd=fd)
    info("Skipped hook install — run `wiki hooks install` later.")
    return 0


def main() -> int:
    return setup()


if __name__ == "__main__":
    sys.exit(main())
