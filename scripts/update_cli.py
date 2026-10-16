"""`wiki update [--no-skills]` (M034-S05-T02 / T03) — pull the engine, then run everything
after the pull from the engine just pulled.

Phase 1 guards the checkout, stashes hand edits to tracked engine files on request, pulls
with `--ff-only` and re-applies the stash where it applies cleanly. Then it re-executes the
PULLED engine's `wiki` with `update --post-pull <rev before the pull>`. Phase 2 is that run:
the summary line, `uv sync`, the cloud-vault hints, both migrations and the skills sync. It
always comes from the new tree, so a changed step takes effect in the update that brought it,
not the next one. Every engine since 0.7.3 hands over the same way, its bash phase 1 included.

The bash `cmd_update` this replaced (deleted in T03, with lib/ui.sh) is recorded in
tests/golden/bash/update-*.txt, the stash path through a pty, and every line there holds.
Each failure after the pull is a warning: the update is done by then.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn

import skills_cli
from cli_help import H_UPDATE, print_help
from core import agents
from core.console import confirm, fail, info, ok, print_error, warn
from core.paths import ROOT_DIR, WIKI_DIR

_ENV = "UV_PROJECT_ENVIRONMENT"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(WIKI_DIR), *args], capture_output=True, text=True, check=False
    )


def _run(argv: list[str], env: dict[str, str] | None = None) -> int:
    """A child's exit code; this process's lines go out first, so a pipe keeps their order."""
    sys.stdout.flush()
    return subprocess.run(argv, env=env, check=False).returncode


def _dim(text: str) -> str:
    """The bash's `${C_DIM}…${C_RESET}`, set when stdout is a terminal."""
    return f"\033[2m{text}\033[0m" if sys.stdout.isatty() else text


# ── phase 1: the pull ──────────────────────────────────────────────────────────


def _stash() -> bool | None:
    """The dirty-tree guard. `git pull --ff-only` aborts on local edits to tracked engine
    files (config.yaml, state/ and logs/ are gitignored, so these are real edits inside
    .wiki/), so offer to stash them out of the way rather than fail with "resolve manually".
    Untracked files stay untouched (no `stash -u`). True when stashed, False when the tree
    is clean, None after a refusal, which is reported."""
    if not (_git("diff", "--quiet").returncode or _git("diff", "--cached", "--quiet").returncode):
        return False
    warn(f"Uncommitted changes in {WIKI_DIR} (tracked engine files):")
    _run(["git", "-C", str(WIKI_DIR), "status", "--short", "--untracked-files=no"])
    if not sys.stdin.isatty():
        fail(
            "Refusing to touch them non-interactively. Run `wiki update` from a terminal to "
            f"stash, or commit/stash manually in {WIKI_DIR}."
        )
        return None
    # on stdout, where the bash's prompt was
    if not confirm("Stash these changes, update, then re-apply them?", False, out=sys.stdout):
        fail(
            "Update aborted — uncommitted changes left in place. Commit or stash them, then "
            "re-run `wiki update`."
        )
        return None
    message = f"wiki-update auto-stash {time.strftime('%Y-%m-%d-%H%M%S')}"
    if _run(["git", "-C", str(WIKI_DIR), "stash", "push", "-m", message]):
        fail(f"git stash failed. Resolve manually in {WIKI_DIR}.")
        return None
    ok("Stashed local changes (will re-apply after the pull if they merge cleanly).")
    return True


def _pull(stashed: bool) -> bool:
    info(f"Pulling latest into {WIKI_DIR} …")
    if not _run(["git", "-C", str(WIKI_DIR), "pull", "--ff-only"]):
        return True
    # Not a fast-forward, or no network: HEAD did not move, so a stash made for this pull
    # pops cleanly back, and the operator's edits are not left hidden by a failed update.
    if stashed:
        if _git("stash", "pop").returncode == 0:
            warn("Restored your stashed changes (pull did not run).")
        else:
            warn(f'Could not auto-restore stash — recover with: git -C "{WIKI_DIR}" stash pop')
    fail(f"git pull failed (non-fast-forward or network). Resolve manually in {WIKI_DIR}.")
    return False


def _reapply() -> None:
    """The stash goes back onto the pulled engine only if it applies cleanly. `git apply
    --check` decides first, so a conflict leaves the stash unpopped (recoverable) instead of
    conflict markers in the checkout mid-update. The check errs safe. Bytes throughout: a
    patch need not be UTF-8."""
    git = ["git", "-C", str(WIKI_DIR)]
    patch = subprocess.run(
        [*git, "stash", "show", "-p", "stash@{0}"], capture_output=True, check=False
    )
    applies = (
        patch.returncode == 0
        and subprocess.run(
            [*git, "apply", "--check", "-"], input=patch.stdout, capture_output=True, check=False
        ).returncode
        == 0
    )
    if not applies:
        warn("Stashed changes would conflict with the update — left unpopped.")
        warn(f'  recover with: git -C "{WIKI_DIR}" stash pop  (then resolve conflicts)')
    elif _git("stash", "pop").returncode == 0:
        ok("Re-applied your stashed changes cleanly.")
    else:
        warn("Stash re-apply failed unexpectedly — your changes are still stashed.")
        warn(f'  recover with: git -C "{WIKI_DIR}" stash pop')


def _handover(before: str, *, sync_skills: bool) -> NoReturn:
    """Everything after the pull runs from the engine just pulled, not from this code, which
    was loaded before it. 2026-10-14: the pre-M033-S02 bash spawned the migrations by file
    path, the pulled tree runs them only as modules, and the first update across that change
    warned `ModuleNotFoundError: core` and skipped the config migration."""
    entry = str(WIKI_DIR / "wiki")
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(
        entry, [entry, "update", "--post-pull", before, *([] if sync_skills else ["--no-skills"])]
    )


def pull(*, sync_skills: bool) -> int:
    stashed = _stash()
    if stashed is None:
        return 1
    head = _git("rev-parse", "--short", "HEAD")
    before = head.stdout.strip() if head.returncode == 0 else "unknown"
    if not _pull(stashed):
        return 1
    if stashed:
        _reapply()
    _handover(before, sync_skills=sync_skills)


# ── phase 2: from the pulled engine ───────────────────────────────────────────


def sync_hint(venv: str | None) -> str:
    """The `uv sync` an operator can paste. Their shell never had the bootstrap's export,
    so the environment is named, and every path is quoted for another shell (the bootstrap
    `wiki`'s `sync_hint`): a bare `uv sync` would rebuild .wiki/.venv inside a cloud-synced vault."""
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
        elif arg == "--post-pull":  # internal: phase 2, with the revision from before the pull
            before = args.pop(0) if args else ""
        elif arg in ("-h", "--help", "help"):  # anywhere, as the bash's flag loop took it
            print_help(H_UPDATE)
            return 0
        else:
            fail(f"unknown flag: {arg}")
            return 1
    # Ask git, don't stat `.git`: it is a file when the checkout is a linked worktree, a
    # submodule, or has its git-dir relocated (to keep 770 MB of packfiles out of iCloud).
    if _git("rev-parse", "--git-dir").returncode != 0:
        fail(
            f"Not a git checkout — {WIKI_DIR} wasn't installed via install.sh. Manual update required."
        )
        return 1
    if before is not None:
        return post_pull(before, sync_skills=sync_skills)
    return pull(sync_skills=sync_skills)


if __name__ == "__main__":
    sys.exit(main())
