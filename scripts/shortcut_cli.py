"""`wiki install-shortcut` — a `wiki` on PATH: the `~/.local/bin/wiki` symlink to this vault's
entry (M034-S02-T04; was the bash `cmd_install_shortcut`, held to the bash oracle's
`install-shortcut*` goldens). The dispatcher prints the banner; no vault is needed.

Idempotent: a link to this entry — through any path that resolves to it — is left alone, a
link to another vault is replaced. Anything that is not a symlink is refused: the bash
`rm -f`'d it, another program called `wiki` included. It never edits a shell rc file; when
`~/.local/bin` is not on PATH it prints the line to add.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from core.console import info, ok, print_error, say, warn
from core.paths import WIKI_DIR

TARGET = WIKI_DIR / "wiki"
RC_LINE = 'export PATH="$HOME/.local/bin:$PATH"'


def _points_at(link: Path, target: Path) -> bool:
    """Whether the symlink ``link`` resolves to ``target`` (macOS /tmp → /private/tmp)."""
    return (link.parent / os.readlink(link)).resolve() == target.resolve()


def _report_path(bin_dir: Path) -> None:
    if str(bin_dir) in os.environ.get("PATH", "").split(os.pathsep):
        ok(f"{bin_dir} is on PATH — typing `wiki` from any cwd will work")
        return
    warn(f"{bin_dir} is NOT on PATH")
    say()
    info("Add this line to your shell rc (~/.zshrc on macOS default):")
    bold, reset = ("\033[1m", "\033[0m") if sys.stdout.isatty() else ("", "")
    say(f"  {bold}{RC_LINE}{reset}")
    info("Then reload: `source ~/.zshrc` (or open a new terminal).")


def install(*, print_only: bool = False) -> int:
    bin_dir = Path.home() / ".local" / "bin"
    link = bin_dir / "wiki"
    if not os.access(TARGET, os.X_OK):
        print_error(f"target {TARGET} is not executable (engine install broken?)")
        return 1
    if print_only:
        info(f"would create: {link} → {TARGET}")
    elif link.exists() and not link.is_symlink():
        print_error(
            f"{link} is not a symlink — another program may be called `wiki`. Move it "
            "away, then run `wiki install-shortcut` again."
        )
        return 1
    elif link.is_symlink() and _points_at(link, TARGET):
        ok(f"already linked: {link} → {TARGET}")
    else:
        if link.is_symlink():
            info(f"replacing existing: {link} → {os.readlink(link)}")
            link.unlink()
        bin_dir.mkdir(parents=True, exist_ok=True)
        link.symlink_to(TARGET)
        ok(f"linked: {link} → {TARGET}")
    _report_path(bin_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    # the bash looked at the first argument only and ignored the rest
    return install(print_only=bool(args) and args[0] == "--print-only")


if __name__ == "__main__":
    sys.exit(main())
