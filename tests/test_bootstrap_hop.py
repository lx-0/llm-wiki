"""The bootstrap hop (M034-S01-T04, DECISIONS 2026-10-15 "One hop").

`wiki <command>` execs the venv's Python straight into `scripts/cli.py`: no `uv run`
parent per call. `uv run` also synced the venv whenever `uv.lock` or `pyproject.toml`
changed, so the hop runs `uv sync` first when either is newer than the venv's last sync
(the `.wiki-synced` stamp), or when there is no venv yet.

The venv's `bin/python` is a stub that records what it was started as, and the `uv` shim
logs every call (`tests/_oracle.py`). The stub's parent being this test process is the
proof that nothing (no `uv`, no second bash) sits between the caller and the dispatcher.
"""

from __future__ import annotations

import os
import shlex
import time
from pathlib import Path

import pytest

from ._oracle import (
    build_engine_template,
    build_fixture_vault,
    install_engine,
    run_wiki,
    write_uv_shim,
)

STUB_PYTHON = """#!/bin/sh
{
  echo "ppid=$PPID"
  echo "virtual_env=${VIRTUAL_ENV:-}"
  echo "path=$PATH"
  for a in "$@"; do echo "arg=$a"; done
} > "$WIKI_HOP_PROBE"
"""


@pytest.fixture(scope="module")
def engine_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_engine_template(tmp_path_factory.mktemp("hop-engine") / ".wiki")


def _env(vault_dir: Path, root: Path, template: Path) -> dict[str, Path]:
    vault = build_fixture_vault(vault_dir)
    wiki = install_engine(vault, template)
    home = root / "home"
    home.mkdir()
    bin_dir = root / "bin"
    write_uv_shim(bin_dir)
    return {"vault": vault, "wiki": wiki, "home": home, "bin": bin_dir, "root": root}


@pytest.fixture
def hop(tmp_path: Path, engine_template: Path) -> dict[str, Path]:
    return _env(tmp_path / "vault", tmp_path, engine_template)


def _stub_venv(venv: Path, *, synced_ago: float = 0.0) -> Path:
    """A venv whose python is the recording stub, synced ``synced_ago`` seconds ago."""
    (venv / "bin").mkdir(parents=True)
    python = venv / "bin" / "python"
    python.write_text(STUB_PYTHON, encoding="utf-8")
    python.chmod(0o755)
    stamp = venv / ".wiki-synced"
    stamp.touch()
    at = time.time() - synced_ago
    os.utime(stamp, (at, at))
    return venv


def _run(env: dict[str, Path], *args: str, **extra: str):
    probe = env["root"] / "probe.txt"
    uv_log = env["root"] / "uv.log"
    run = run_wiki(
        env["vault"],
        env["home"],
        env["bin"],
        *args,
        extra_env={"WIKI_HOP_PROBE": str(probe), "WIKI_ORACLE_UV_LOG": str(uv_log), **extra},
    )
    record = probe.read_text(encoding="utf-8").splitlines() if probe.exists() else []
    calls = uv_log.read_text(encoding="utf-8").splitlines() if uv_log.exists() else []
    probe.unlink(missing_ok=True)
    return run, record, calls


def test_a_current_venv_is_execd_directly(hop: dict[str, Path]) -> None:
    venv = _stub_venv(hop["wiki"] / ".venv")

    run, record, calls = _run(hop, "collect", "--list")

    assert run.returncode == 0, run.stderr
    assert calls == []
    assert f"ppid={os.getpid()}" in record  # exec'd: no process between this test and Python
    assert [line[4:] for line in record if line.startswith("arg=")] == [
        str(hop["wiki"] / "scripts" / "cli.py"),
        "collect",
        "--list",
    ]
    assert f"virtual_env={venv}" in record
    path = next(line[5:] for line in record if line.startswith("path="))
    assert path.split(os.pathsep)[0] == str(venv / "bin")


@pytest.mark.parametrize("changed", ["uv.lock", "pyproject.toml"])
def test_a_project_file_newer_than_the_last_sync_syncs_once(
    hop: dict[str, Path], changed: str
) -> None:
    _stub_venv(hop["wiki"] / ".venv", synced_ago=120)
    edited = time.time() - 60
    os.utime(hop["wiki"] / changed, (edited, edited))

    run, record, calls = _run(hop, "collect", "--list")

    assert run.returncode == 0, run.stderr
    assert calls == [f"sync --quiet --inexact --project {hop['wiki']}"]
    assert f"ppid={os.getpid()}" in record

    run, record, calls = _run(hop, "collect", "--list")

    assert calls == [f"sync --quiet --inexact --project {hop['wiki']}"]  # no second sync
    assert f"ppid={os.getpid()}" in record


def test_a_vault_without_a_venv_syncs_one_first(hop: dict[str, Path]) -> None:
    run, _, calls = _run(hop, "collect", "--list")

    assert run.returncode == 0, run.stderr
    assert calls == [f"sync --quiet --inexact --project {hop['wiki']}"]
    assert "NAME" in run.stdout  # the real dispatcher ran from the venv uv created
    assert (hop["wiki"] / ".venv" / ".wiki-synced").exists()


def test_a_cloud_synced_vault_runs_the_venv_under_home(
    tmp_path: Path, engine_template: Path
) -> None:
    # lib/common.sh's one rule: a vault in iCloud Drive keeps its venv at ~/.venvs/<vault>-wiki
    env = _env(tmp_path / "Library" / "Mobile Documents", tmp_path, engine_template)
    venv = _stub_venv(env["home"] / ".venvs" / f"{env['vault'].name}-wiki")

    run, record, calls = _run(env, "collect", "--list")

    assert run.returncode == 0, run.stderr
    assert calls == []
    assert f"virtual_env={venv}" in record
    assert f"ppid={os.getpid()}" in record


def test_a_failing_sync_says_so_and_runs_nothing(hop: dict[str, Path]) -> None:
    """A uv that cannot run used to end `wiki` with its exit code and no word (found on the
    scratch vault, M034-S02-T03: an asdf shim under a foreign HOME, exit 126, empty output)."""
    venv = _stub_venv(hop["wiki"] / ".venv", synced_ago=120)
    stamp_before = (venv / ".wiki-synced").stat().st_mtime
    edited = time.time() - 60
    os.utime(hop["wiki"] / "uv.lock", (edited, edited))

    run, record, _ = _run(hop, "collect", "--list", WIKI_ORACLE_UV_FAIL="126")

    assert run.returncode != 0
    assert record == []  # Python never started on the stale environment
    assert "uv sync failed" in run.stderr
    assert _hint(run.stderr) == [
        f"UV_PROJECT_ENVIRONMENT={venv}",
        *("uv", "sync", "--project", str(hop["wiki"])),
    ]
    assert (venv / ".wiki-synced").stat().st_mtime == stamp_before


def test_the_sync_hint_pastes_back_for_a_path_with_a_space_and_an_apostrophe(
    tmp_path: Path, engine_template: Path
) -> None:
    """The hint is for the operator's own shell, so its paths are quoted: unquoted, every
    iCloud vault (`…/Mobile Documents/…`) split `--project` in two."""
    env = _env(tmp_path / "Alex's Vault", tmp_path, engine_template)
    venv = _stub_venv(env["wiki"] / ".venv", synced_ago=120)
    edited = time.time() - 60
    os.utime(env["wiki"] / "uv.lock", (edited, edited))

    run, record, _ = _run(env, "collect", "--list", WIKI_ORACLE_UV_FAIL="126")

    assert record == []
    assert _hint(run.stderr) == [
        f"UV_PROJECT_ENVIRONMENT={venv}",
        *("uv", "sync", "--project", str(env["wiki"])),
    ]


def _hint(stderr: str) -> list[str]:
    """The command on the failure's last line, as the operator's shell would split it."""
    return shlex.split(stderr.strip().splitlines()[-1])


def test_a_relative_project_environment_stays_on_uv_run(hop: dict[str, Path]) -> None:
    # uv resolves a relative UV_PROJECT_ENVIRONMENT itself, so the bash does not guess where
    # the venv is: the call stays the `uv run` it was before the hop
    run, _, calls = _run(hop, "collect", "--list", UV_PROJECT_ENVIRONMENT="rel-venv")

    assert run.returncode == 0, run.stderr
    assert calls == [
        f"run --quiet --project {hop['wiki']} python {hop['wiki'] / 'scripts' / 'cli.py'} "
        "collect --list"
    ]
    assert "NAME" in run.stdout
