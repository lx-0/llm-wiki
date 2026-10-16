"""`wiki hooks install / uninstall / status` (M034-S03-T05; were lib/hooks.sh and
lib/agents.sh, held to the bash oracle's hooks-* / status / setup-with-hooks goldens).

Agent configs change the way the bash changed them, with core/agents' merge and uninstall
filter (byte-identical to its jq). Every write is backed up first (core/backup, never over
an earlier backup) and lands through a temp file. The prompts follow the bash's (the
deleted lib/ui.sh): the pickers on stderr, the confirmation on stdout. They read byte by byte, so `wiki setup` runs the
install in-process on the same piped stdin.

One decided difference: the table counts a config as installed when an entry under its
`hooks` block runs a wiki command (core/agents.wiki_commands), not when the file's text
names one. A config that is not JSON shows as unreadable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from cli_help import H_HOOKS
from core import agents
from core.backup import backup
from core.console import banner, confirm, fail, info, ok, print_error, select_many, select_one, warn
from core.paths import ROOT_DIR, WIKI_DIR

# Scope picker labels → the scopes, in the bash's order: "both" did project first.
SCOPES = {
    "user only (recommended)": ("user",),
    "project only": ("project",),
    "both": ("project", "user"),
}


def _styled(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def _pad(text: str, width: int) -> str:
    """Left-justified to ``width`` BYTES, as bash's `printf %-Ns` does: `—` takes three."""
    return text + " " * max(0, width - len(text.encode()))


def _config(name: str, scope: str) -> Path:
    return agents.config_path(name, scope, home=Path.home(), root=ROOT_DIR)


def _present(name: str, scope: str) -> bool:
    return agents.present(name, scope, home=Path.home(), root=ROOT_DIR)


def _commands(name: str, scope: str) -> list[str]:
    """The wiki commands in one config; ValueError / OSError when it cannot be read."""
    return agents.wiki_commands(agents.read_config(_config(name, scope)))


def _may_hold_ours(name: str, scope: str) -> bool:
    """Whether uninstall offers this config: it runs a wiki hook, or it cannot be parsed and
    its text names one, so it may hold one. The attempt then reports it unreadable instead
    of uninstall claiming there is nothing to remove."""
    try:
        return bool(_commands(name, scope))
    except OSError:
        return False
    except ValueError:
        try:
            text = _config(name, scope).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return agents.HOOK_CMD_RE.search(text) is not None


def _cell(name: str, scope: str) -> str:
    try:
        installed = bool(_commands(name, scope))
    except (OSError, ValueError):
        return _styled("unreadable", "31")
    if installed:
        return _styled("installed", "32")
    return _styled("detected" if _present(name, scope) else "—", "2")


def status_table() -> None:
    print(f"{'AGENT':<10} {'USER':<22} {'PROJECT':<22} PROJECT CONFIG")
    print("─" * 78)
    for spec in agents.AGENTS:
        user = _pad(_cell(spec.name, "user"), 30)
        project = _pad(_cell(spec.name, "project"), 30)
        print(f"{spec.name:<10} {user} {project} {_config(spec.name, 'project')}")


def _pick_scopes(fd: int) -> tuple[str, ...]:
    """Default user scope: the wiki captures sessions from every project the operator works
    in, not only those started in the vault; project scope is the niche case."""
    return SCOPES[select_one("Install scope", list(SCOPES), 1, fd=fd)]


def _write(cfg: Path, text: str) -> None:
    """Through a temp file, so a failed write leaves the config, or its absence, as it was."""
    cfg.parent.mkdir(parents=True, exist_ok=True)
    tmp = cfg.with_name(f"{cfg.name}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(cfg)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _read(name: str, scope: str, cfg: Path) -> tuple[bool, dict | None]:
    """(readable, config). An unreadable config is reported here, as a failed item."""
    try:
        return True, agents.read_config(cfg)
    except ValueError as exc:
        fail(f"{name} ({scope}): {cfg} is not valid JSON — left as it was ({exc})")
    except OSError as exc:
        fail(f"{name} ({scope}): could not read {cfg} — left as it was ({exc.strerror or exc})")
    return False, None


def _install_one(name: str, scope: str) -> bool:
    cfg = _config(name, scope)
    readable, config = _read(name, scope, cfg)
    if not readable:
        return False
    venv = os.environ.get("UV_PROJECT_ENVIRONMENT") or None
    payload = agents.payload(name, wiki_dir=WIKI_DIR, venv=venv)
    try:
        bak = backup(cfg) if config is not None else None
    except OSError:
        fail(f"{name} ({scope}): could not back up {cfg} — left as it was")
        return False
    try:
        _write(cfg, agents.render(payload if config is None else agents.merge(config, payload)))
    except OSError as exc:
        fail(f"{name} ({scope}): could not write {cfg} ({exc.strerror or exc})")
        return False
    if bak is None:
        ok(f"{name} ({scope}): created {cfg}")
    else:
        ok(f"{name} ({scope}): updated {cfg} {_styled(f'(backup: {bak})', '2')}")
    return True


def _uninstall_one(name: str, scope: str) -> bool:
    cfg = _config(name, scope)
    if not cfg.is_file():
        warn(f"{name} ({scope}): no config at {cfg} — skipping")
        return True
    readable, config = _read(name, scope, cfg)
    if not readable or config is None:
        return False
    kept = agents.without_wiki_hooks(config)
    if kept == config:
        info(f"{name} ({scope}): no wiki hooks in {cfg} — nothing to remove")
        return True
    try:
        bak = backup(cfg)
    except OSError:
        fail(f"{name} ({scope}): could not back up {cfg} — left as it was")
        return False
    try:
        _write(cfg, agents.render(kept))
    except OSError as exc:
        fail(f"{name} ({scope}): could not write {cfg} ({exc.strerror or exc})")
        return False
    ok(f"{name} ({scope}): removed wiki hooks {_styled(f'(backup: {bak})', '2')}")
    return True


def _run(chosen: list[str], scopes: tuple[str, ...], one, what: str) -> int:
    """Every agent × scope; the failures named above get a count and exit 1, never Done."""
    failed = total = 0
    for name in chosen:
        for scope in scopes:
            total += 1
            failed += not one(name, scope)
    print()
    if failed:
        fail(f"{failed} of {total} {what} failed — see above.")
        return 1
    return 0


def install(*, fd: int = 0) -> int:
    banner(
        "wiki hooks — install",
        "Adds session hooks to one or more AI agent configs. Backups + idempotent.",
    )
    status_table()
    print()
    names = [spec.name for spec in agents.AGENTS]
    defaults = [n for n in names if _present(n, "user") or _present(n, "project")] or ["claude"]
    chosen = select_many("Select agents to install hooks for", names, defaults, fd=fd)
    if not chosen:
        warn("No agents selected.")
        return 0
    scopes = _pick_scopes(fd)
    print()
    info("Will install hooks:")
    for name in chosen:
        for scope in scopes:
            print(f"  - {name} @ {scope} → {_config(name, scope)}")
    print()
    if not confirm("Proceed?", True, fd=fd, out=sys.stdout):
        warn("Aborted.")
        return 0
    print()
    code = _run(chosen, scopes, _install_one, "hook installs")
    if code == 0:
        ok("Done. Restart agent CLIs to pick up the new hooks.")
    return code


def uninstall(*, fd: int = 0) -> int:
    banner(
        "wiki hooks — uninstall", "Removes wiki-managed hook entries; preserves user's other hooks."
    )
    status_table()
    print()
    names = [spec.name for spec in agents.AGENTS]
    defaults = [n for n in names if _may_hold_ours(n, "user") or _may_hold_ours(n, "project")]
    if not defaults:
        warn("No wiki hooks installed anywhere.")
        return 0
    chosen = select_many("Select agents to uninstall hooks from", names, defaults, fd=fd)
    if not chosen:
        warn("No agents selected.")
        return 0
    scopes = _pick_scopes(fd)
    print()
    if not confirm("Remove wiki hooks from selected configs?", True, fd=fd, out=sys.stdout):
        warn("Aborted.")
        return 0
    print()
    code = _run(chosen, scopes, _uninstall_one, "hook removals")
    if code == 0:
        ok("Done.")
    return code


def status() -> int:
    banner("wiki hooks — status")
    status_table()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    command = args[0] if args else "install"
    if command == "install":
        return install()
    if command == "uninstall":
        return uninstall()
    if command == "status":
        return status()
    print_error(f"unknown: wiki hooks {command}")
    print(H_HOOKS)
    return 1


if __name__ == "__main__":
    sys.exit(main())
