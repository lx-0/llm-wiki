"""`wiki update` runs everything after the pull from the engine it just pulled.

The code that starts `wiki update` was loaded before the pull. Its post-pull steps
(dependency sync, config + operations-log migrations, skills sync) must come from the NEW
tree, or a changed spawn shape / a new step only takes effect on the *next* update. Seen
2026-10-14 on a scratch copy of the operator vault (`5b6b947` → M033-S02): the pre-S02 bash
spawned `migrations/migrate_config_keys.py` by file path, the pulled tree runs it only as a
module, and the first update warned `ModuleNotFoundError: core` and skipped the migration.

Phase 1, the pull, is still the bash's until M034-S05-T03. Phase 2, `--post-pull`, is
`scripts/update_cli.py` since T02, so its tests run a real engine copy (the bash oracle's
template) behind the oracle's `uv` shim, which logs how uv was called and syncs nothing.
The re-exec test keeps a bare bash world: the pulled `wiki` it hands over to is a stub.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from ._oracle import build_engine_template, install_engine, run_wiki, write_uv_shim

REPO = Path(__file__).resolve().parent.parent
BASH_LAYER = (
    "wiki",
    "lib",
)  # everything the dispatcher sources; phase 1 needs nothing else
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


# ── phase 1 hands over to the pulled engine ─────────────────────────────────────


def test_post_pull_steps_run_from_the_pulled_wiki(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """origin moves on and its `wiki` becomes a stub that announces itself; the update
    started by the OLD bash must hand over to that stub for everything after the pull."""
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
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)  # the dispatcher's fail-closed vault guard
    wiki = vault / ".wiki"
    _git("clone", "-q", str(origin), str(wiki), cwd=tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "uv").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (bin_dir / "uv").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("UV_PROJECT_ENVIRONMENT", raising=False)
    (origin / "wiki").write_text(f'#!/usr/bin/env bash\necho "{MARKER} $*"\n', encoding="utf-8")
    _git("commit", "-q", "-am", "pulled engine", cwd=origin)
    before = _git("rev-parse", "--short", "HEAD", cwd=wiki)

    proc = subprocess.run(
        [str(wiki / "wiki"), "update", "--no-skills"],
        cwd=vault,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert f"{MARKER} update --post-pull {before} --no-skills" in proc.stdout, (
        "the post-pull phase ran from the code that started the update, not from the "
        "pulled one:\n" + proc.stdout + proc.stderr
    )


# ── phase 2, `wiki update --post-pull <rev>` ────────────────────────────────────


@pytest.fixture(scope="module")
def engine_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_engine_template(tmp_path_factory.mktemp("engine") / ".wiki")


def _vault(tmp_path: Path, template: Path, name: str = "vault") -> dict[str, Path]:
    """A vault called ``name`` with a copy of the engine, a scratch HOME and the uv shim."""
    vault = tmp_path / name
    vault.mkdir()
    install_engine(vault, template)
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    write_uv_shim(bin_dir)
    return {"vault": vault, "wiki": vault / ".wiki", "home": home, "bin": bin_dir}


def _post_pull(
    env: dict[str, Path], *flags: str, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return run_wiki(
        env["vault"],
        env["home"],
        env["bin"],
        "update",
        "--post-pull",
        "abc1234",
        *flags,
        extra_env=extra_env,
    )


def test_phase_two_syncs_and_runs_both_migrations_from_the_engine(
    tmp_path: Path, engine_template: Path
) -> None:
    """The second phase: one `uv sync` of the engine, then both migrations as modules of
    the engine's scripts/ — the shape the pre-S02 bash got wrong. A module that cannot be
    found would end in the step's own warning instead of the migration's output."""
    env = _vault(tmp_path, engine_template)
    uv_log = tmp_path / "uv.log"

    proc = _post_pull(env, "--no-skills", extra_env={"WIKI_ORACLE_UV_LOG": str(uv_log)})

    assert proc.returncode == 0, proc.stderr
    assert f"sync --project {env['wiki']} --quiet" in uv_log.read_text(encoding="utf-8")
    assert "reported errors" not in proc.stdout
    assert "config.yaml not found" in proc.stderr  # migrate_config_keys ran, and looked
    assert "has no knowledge/ dir" in proc.stderr  # migrate_log_md_path ran, and looked
    assert proc.stdout.rstrip().endswith("skills: skipped (--no-skills)")


def test_a_failed_sync_names_a_command_that_pastes_back(
    tmp_path: Path, engine_template: Path
) -> None:
    """The retry command is for the operator's own shell: the environment named (that shell
    never had the bootstrap's export) and every path quoted. `Run 'uv sync --project <dir>'`
    split an iCloud vault's `Mobile Documents` in two and synced the in-vault environment."""
    env = _vault(tmp_path, engine_template, name="Alex's Vault")
    # the bootstrap syncs a venv it has not stamped yet, before Python runs: stamp it first
    assert run_wiki(env["vault"], env["home"], env["bin"], "version").returncode == 0

    proc = _post_pull(env, "--no-skills", extra_env={"WIKI_ORACLE_UV_FAIL": "1"})

    line = next(ln for ln in proc.stdout.splitlines() if "uv sync reported errors" in ln)
    assert shlex.split(line.split("run: ", 1)[1]) == [
        f"UV_PROJECT_ENVIRONMENT={env['wiki']}/.venv",
        *("uv", "sync", "--project", str(env["wiki"])),
    ]


def test_the_stale_environment_hint_quotes_its_path(tmp_path: Path, engine_template: Path) -> None:
    env = _vault(tmp_path, engine_template, name="Alex's Vault")
    (env["wiki"] / ".venv").mkdir()
    venv = str(env["home"] / ".venvs" / "v-wiki")

    proc = _post_pull(env, "--no-skills", extra_env={"UV_PROJECT_ENVIRONMENT": venv})

    line = next(ln for ln in proc.stdout.splitlines() if "no longer used" in ln)
    assert shlex.split(line.split("remove it: ", 1)[1]) == ["rm", "-rf", f"{env['wiki']}/.venv"]


def test_phase_two_refuses_an_unknown_flag(tmp_path: Path, engine_template: Path) -> None:
    env = _vault(tmp_path, engine_template)

    proc = _post_pull(env, "--nope")

    assert proc.returncode == 1
    assert proc.stderr == "✗ unknown flag: --nope\n"
    assert proc.stdout == ""


def test_the_python_handler_pulls_nothing_without_post_pull(capsys) -> None:
    """Until T03 ports phase 1, the bash pulls; `update_cli` without `--post-pull` refuses
    instead of syncing or migrating anything. T03 replaces this test: called in-process
    with phase 1 ported, `main([])` would pull this checkout."""
    import update_cli

    assert update_cli.main([]) == 1
    assert "--post-pull" in capsys.readouterr().err


def test_the_update_help_is_the_recorded_bash_text(capsys) -> None:
    """The catalogue holds `update`'s help now (a `py` command carries its text), while
    `wiki update --help` is still the bash heredoc until T03 deletes it. Held to the record
    of that heredoc, so the switch changes nothing an operator reads."""
    import cli

    record = (REPO / "tests" / "golden" / "bash" / "update-help.txt").read_text(encoding="utf-8")
    recorded = record.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)[0]

    assert cli.main(["update", "--help"]) == 0
    assert re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out) == recorded
