"""`wiki update --post-pull <rev> [--no-skills]` (M034-S05-T02) — everything after the pull.

The first phase pulls the engine and then re-executes the PULLED engine's `wiki` with
`update --post-pull <rev before the pull>`, so these steps always come from the new tree: a
changed step takes effect in the update that brought it, not the next one. That phase is
still the bash's `cmd_update` until T03, and a 0.7.3 bash pulling this engine re-executes
into it exactly so.

The steps, in the bash `_update_post_pull`'s order and words (it is recorded in
tests/golden/bash/update-*.txt, and every line there holds):
- the summary line;
- `uv sync` of the engine's environment;
- for an environment outside the vault, where it is, an in-vault one left behind, and hooks
  still running that one;
- the config.yaml and operations-log migrations, as modules of this engine;
- the skills sync, unless `--no-skills`.

Each step's failure is a warning. The update is done by then, and the exit code stays 0.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import skills_cli
from core import agents
from core.console import fail, info, ok, print_error, warn
from core.paths import ROOT_DIR, WIKI_DIR

_ENV = "UV_PROJECT_ENVIRONMENT"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(WIKI_DIR), *args], capture_output=True, text=True, check=False
    )


def _dim(text: str) -> str:
    """The bash's `${C_DIM}…${C_RESET}`, set when stdout is a terminal."""
    return f"\033[2m{text}\033[0m" if sys.stdout.isatty() else text


def sync_hint(venv: str | None) -> str:
    """The `uv sync` an operator can paste. Their shell never had the bootstrap's export,
    so the environment is named, and every path is quoted for another shell (lib/common.sh's
    `sync_hint`): a bare `uv sync` would rebuild .wiki/.venv inside a cloud-synced vault."""
    env = agents.shell_quote(venv or str(WIKI_DIR / ".venv"))
    return f"{_ENV}={env} uv sync --project {agents.shell_quote(str(WIKI_DIR))}"


def stale_hooks(*, home: Path, root: Path) -> list[str]:
    """`<agent> (<scope>)` for each installed set of wiki hooks with a command that does not
    carry the engine environment, as `wiki doctor` judges them: a hook runs with the agent's
    environment, not `wiki`'s, so each command names it literally (`core.agents.hook_cmd`)."""
    return [
        f"{name} ({scope})"
        for (name, scope), commands in agents.installed_wiki_commands(home=home, root=root).items()
        if any(f"{_ENV}=" not in command for command in commands)
    ]


def _summary(before: str) -> int:
    after = _git("rev-parse", "--short", "HEAD")
    if after.returncode != 0:
        sys.stderr.write(after.stderr)
        return 1
    rev = after.stdout.strip()
    if before == rev:
        ok(f"Already up to date ({before})")
    else:
        ok(f"Updated {before} → {rev}")
        info("If hook payloads or config schema changed, you may want to re-run:")
        info(f"  wiki hooks install      {_dim('# to refresh agent hook configs')}")
    return 0


def _environment(venv: str) -> None:
    """A cloud-synced vault's environment lives outside it (the bootstrap exported it, so
    the sync went there). Say so, and point at what is now dead weight: a real .wiki/.venv,
    never deleted here — the operator removes it once, deliberately."""
    info(f"Engine environment: {venv} (outside cloud-synced storage)")
    in_vault = WIKI_DIR / ".venv"
    if in_vault.exists() and not in_vault.is_symlink():
        warn(
            f"stale in-vault environment at {in_vault} is no longer used — remove it: "
            f"rm -rf {agents.shell_quote(str(in_vault))}"
        )
    if stale := stale_hooks(home=Path.home(), root=ROOT_DIR):
        warn(
            f"hooks still run the engine from the in-vault environment: {', '.join(stale)}"
            " — re-run: wiki hooks install"
        )


def _run(argv: list[str], env: dict[str, str] | None = None) -> int:
    """A child's exit code; this process's lines go out first, so a pipe keeps their order."""
    sys.stdout.flush()
    return subprocess.run(argv, env=env, check=False).returncode


def _migrate(module: str, *args: str) -> bool:
    """One migration as a module of this engine, in a child: each sets up its own logging,
    and a package the sync just added is importable there."""
    return not _run(
        [sys.executable, "-m", f"migrations.{module}", "--vault", str(ROOT_DIR), *args],
        env={**os.environ, "PYTHONPATH": str(WIKI_DIR / "scripts")},
    )


def _skills(sync_skills: bool) -> None:
    if not sync_skills:
        info("skills: skipped (--no-skills)")
        return
    try:
        failed = skills_cli.sync() != 0
    except Exception as exc:
        print_error(f"skills sync: {exc}")
        failed = True
    if failed:
        warn("skills sync failed — rerun: wiki skills sync")


def post_pull(before: str, *, sync_skills: bool) -> int:
    if _summary(before) != 0:
        return 1
    # pyproject.toml changes (a new dependency, a version bump) must land in the venv, or
    # the engine imports fail through whatever fallback the caller has (pillow, 2026-05-29)
    info("Syncing Python dependencies (uv sync, idempotent) …")
    venv = os.environ.get(_ENV) or None
    if _run(["uv", "sync", "--project", str(WIKI_DIR), "--quiet"]):
        warn(
            f"uv sync reported errors — runtime imports may fail. To retry, run: {sync_hint(venv)}"
        )
    if venv:
        _environment(venv)
    # Unconditionally: it says "no change" on the current schema, and otherwise applies the
    # renames, additions and drops the pull brought (with a backup)
    info("Migrating config.yaml to current schema (idempotent) …")
    if not _migrate("migrate_config_keys", "--apply"):
        warn(f"Config migration reported errors — inspect {ROOT_DIR}/.wiki/config.yaml manually.")
    # Vaults from before 2026-05-28 carry a 2 MB audit log inside knowledge/ that crashes
    # Obsidian on open; it is engine telemetry and moves to .wiki/logs/operations.md
    info("Relocating operations log out of knowledge/ (idempotent) …")
    if not _migrate("migrate_log_md_path"):
        warn(
            f"Operations-log migration reported errors — inspect {ROOT_DIR}/knowledge/log.md manually."
        )
    _skills(sync_skills)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    sync_skills, before = True, None
    while args:
        arg = args.pop(0)
        if arg == "--no-skills":
            sync_skills = False
        elif arg == "--post-pull":
            before = args.pop(0) if args else ""
        else:
            fail(f"unknown flag: {arg}")
            return 1
    if before is None:
        # the pull is the bash's `cmd_update` until M034-S05-T03: nothing here may pull
        print_error(
            "update: the pull runs from the `wiki` entry; this is its second phase (--post-pull <rev>)"
        )
        return 1
    # Ask git, don't stat `.git`: it is a file when the checkout is a linked worktree, a
    # submodule, or has its git-dir relocated (to keep 770 MB of packfiles out of iCloud).
    if _git("rev-parse", "--git-dir").returncode != 0:
        fail(
            f"Not a git checkout — {WIKI_DIR} wasn't installed via install.sh. Manual update required."
        )
        return 1
    return post_pull(before, sync_skills=sync_skills)


if __name__ == "__main__":
    sys.exit(main())
