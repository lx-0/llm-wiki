"""`wiki setup` — first-time setup: the config wizard, then the hooks step (M034-S02-T03; was
the bash `cmd_setup`, held to the bash oracle's `setup-wizard` / `setup-with-hooks` goldens).
The dispatcher prints the banner (`wiki setup` + its subtitle) before this runs.

The hooks step runs `<.wiki>/wiki hooks install` as a child that inherits stdin: hooks stay
bash until S03-T02, and the child reads its own answers from that stdin. The wizard's prompts
read byte by byte (`core/console.read_line`), so none of the child's answers is consumed
here — `setup-with-hooks` pipes both in one stream.
"""

from __future__ import annotations

import subprocess
import sys

import config_cli
from core.console import confirm, info
from core.paths import WIKI_DIR

WIKI_BIN = WIKI_DIR / "wiki"


def setup(*, fd: int = 0) -> int:
    """The wizard, then "install hooks?"; the hooks installer's exit code is setup's."""
    config_cli.wizard(fd=fd)
    print()
    sys.stdout.flush()
    if confirm("Now install hooks into agent configs?", default=True, fd=fd):
        return subprocess.run([str(WIKI_BIN), "hooks", "install"], check=False).returncode
    info("Skipped hook install — run `wiki hooks install` later.")
    return 0


def main() -> int:
    return setup()


if __name__ == "__main__":
    sys.exit(main())
