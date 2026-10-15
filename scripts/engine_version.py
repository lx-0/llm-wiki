"""`wiki version` — the engine checkout's revision, tag and origin (M034-S01-T05; was the
bash `cmd_version`, whose output it keeps: `%-12s %s` rows, the tag only when one other than
the bare revision describes HEAD, and a warning line outside a git checkout).

Arguments are ignored, as the bash ignored them. Works without a vault: the bash guard
exempts `version`, and nothing here reads one.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from core.paths import WIKI_DIR

_YELLOW, _RESET = ("\033[33m", "\033[0m") if sys.stdout.isatty() else ("", "")


def _git(wiki_dir: Path, *args: str) -> str | None:
    """Stdout of one git call in ``wiki_dir`` (stripped), or None when it fails. A
    `.git` file (worktrees, submodules, relocated git dirs) works, because git is asked
    instead of the path being stat-ed."""
    run = subprocess.run(
        ["git", "-C", str(wiki_dir), *args], capture_output=True, text=True, check=False
    )
    return run.stdout.strip() if run.returncode == 0 else None


def report(wiki_dir: Path) -> list[str]:
    """The lines `wiki version` prints for the engine at ``wiki_dir``."""
    if _git(wiki_dir, "rev-parse", "--git-dir") is None:
        return [f"{_YELLOW}! Not a git checkout. Cannot report version.{_RESET}"]
    rev = _git(wiki_dir, "rev-parse", "--short", "HEAD") or ""
    tag = _git(wiki_dir, "describe", "--tags", "--always") or ""
    origin = _git(wiki_dir, "config", "--get", "remote.origin.url") or ""
    lines = [f"{'revision':<12} {rev}"]
    if tag and tag != rev:
        lines.append(f"{'tag':<12} {tag}")
    if origin:
        lines.append(f"{'origin':<12} {origin}")
    return lines


def main() -> int:
    for line in report(WIKI_DIR):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
