"""`wiki update` runs everything after the pull from the engine it just pulled.

The bash that starts `wiki update` was parsed before the pull. Its post-pull steps
(dependency sync, config + operations-log migrations, skills sync) must come from the NEW
tree, or a changed spawn shape / a new step only takes effect on the *next* update. Seen
2026-10-14 on a scratch copy of the operator vault (`5b6b947` → M033-S02): the pre-S02 bash
spawned `migrations/migrate_config_keys.py` by file path, the pulled tree runs it only as a
module, and the first update warned `ModuleNotFoundError: core` and skipped the migration.

Real git + the real bash layer; only `uv` is a logging stub on PATH (the post-pull steps
would otherwise sync a venv and run the migrations for real).
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BASH_LAYER = (
    "wiki",
    "lib",
)  # everything the dispatcher sources; the update path needs nothing else
MARKER = "POST-PULL-FROM-PULLED-WIKI"
_GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_GIT_IDENTITY},
    ).stdout.strip()


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    return _world(tmp_path, monkeypatch)


def _world(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    vault_name: str = "vault",
    sync_fails: bool = False,
) -> dict[str, Path]:
    """origin = a git repo holding this checkout's bash layer; <vault>/.wiki = its clone;
    a logging `uv` stub first on PATH (its `uv sync` exits 1 when ``sync_fails``); HOME
    pointed away from the machine."""
    origin = tmp_path / "origin"
    origin.mkdir()
    for name in BASH_LAYER:
        src = REPO / name
        if src.is_dir():
            shutil.copytree(src, origin / name)
        else:
            shutil.copy2(src, origin / name)
    _git("init", "-q", "-b", "main", cwd=origin)
    _git("add", "-A", cwd=origin)
    _git("commit", "-q", "-m", "base", cwd=origin)

    vault = tmp_path / vault_name
    (vault / ".obsidian").mkdir(parents=True)  # the dispatcher's fail-closed vault guard
    _git("clone", "-q", str(origin), str(vault / ".wiki"), cwd=tmp_path)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv_log = tmp_path / "uv.log"
    stub = bin_dir / "uv"
    stub.write_text(
        "#!/bin/sh\n"
        f'printf "uv %s PYTHONPATH=%s\\n" "$*" "${{PYTHONPATH:-}}" >> "{uv_log}"\n'
        + ('[ "$1" = sync ] && exit 1\n' if sync_fails else "")
        + "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("UV_PROJECT_ENVIRONMENT", raising=False)
    return {"origin": origin, "vault": vault, "wiki": vault / ".wiki", "uv_log": uv_log}


def _wiki(world: dict[str, Path], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(world["wiki"] / "wiki"), *args],
        cwd=world["vault"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def test_post_pull_steps_run_from_the_pulled_wiki(world: dict[str, Path]) -> None:
    """origin moves on and its `wiki` becomes a stub that announces itself; the update
    started by the OLD bash must hand over to that stub for everything after the pull."""
    (world["origin"] / "wiki").write_text(
        f'#!/usr/bin/env bash\necho "{MARKER} $*"\n', encoding="utf-8"
    )
    _git("commit", "-q", "-am", "pulled engine", cwd=world["origin"])
    before = _git("rev-parse", "--short", "HEAD", cwd=world["wiki"])

    proc = _wiki(world, "update", "--no-skills")

    assert proc.returncode == 0, proc.stderr
    assert f"{MARKER} update --post-pull {before} --no-skills" in proc.stdout, (
        "the post-pull phase ran from the bash that started the update, not from the "
        "pulled one:\n" + proc.stdout + proc.stderr
    )


def test_post_pull_phase_spawns_sync_and_migrations_as_modules(world: dict[str, Path]) -> None:
    """The second phase on its own: `uv sync` plus both migrations as `-m` modules with
    scripts/ on PYTHONPATH — the shape the pre-S02 bash got wrong."""
    wiki, vault = world["wiki"], world["vault"]

    proc = _wiki(world, "update", "--post-pull", "abc1234", "--no-skills")

    assert proc.returncode == 0, proc.stderr
    calls = world["uv_log"].read_text(encoding="utf-8").splitlines()
    assert f"uv sync --project {wiki} --quiet PYTHONPATH=" in calls
    assert (
        f"uv run --quiet --project {wiki} python -m migrations.migrate_config_keys "
        f"--vault {vault} --apply PYTHONPATH={wiki}/scripts"
    ) in calls
    assert (
        f"uv run --quiet --project {wiki} python -m migrations.migrate_log_md_path "
        f"--vault {vault} PYTHONPATH={wiki}/scripts"
    ) in calls


def test_a_failed_sync_names_a_command_that_pastes_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retry command is for the operator's own shell: the environment named (that shell
    never had lib/common.sh's export) and every path quoted. `Run 'uv sync --project <dir>'`
    split an iCloud vault's `Mobile Documents` in two and synced the in-vault environment."""
    world = _world(tmp_path, monkeypatch, vault_name="Alex's Vault", sync_fails=True)

    proc = _wiki(world, "update", "--post-pull", "abc1234", "--no-skills")

    line = next(ln for ln in proc.stdout.splitlines() if "uv sync reported errors" in ln)
    assert shlex.split(line.split("run: ", 1)[1]) == [
        f"UV_PROJECT_ENVIRONMENT={world['wiki']}/.venv",
        *("uv", "sync", "--project", str(world["wiki"])),
    ]


def test_the_stale_environment_hint_quotes_its_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(tmp_path, monkeypatch, vault_name="Alex's Vault")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(tmp_path / "home" / ".venvs" / "v-wiki"))
    (world["wiki"] / ".venv").mkdir()

    proc = _wiki(world, "update", "--post-pull", "abc1234", "--no-skills")

    line = next(ln for ln in proc.stdout.splitlines() if "no longer used" in ln)
    assert shlex.split(line.split("remove it: ", 1)[1]) == ["rm", "-rf", f"{world['wiki']}/.venv"]
