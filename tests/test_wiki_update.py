"""`wiki update` runs everything after the pull from the engine it just pulled.

The code that starts `wiki update` was loaded before the pull. Its post-pull steps
(dependency sync, config + operations-log migrations, skills sync) must come from the NEW
tree, or a changed spawn shape / a new step only takes effect on the *next* update. Seen
2026-10-14 on a scratch copy of the operator vault (`5b6b947` → M033-S02): the pre-S02 bash
spawned `migrations/migrate_config_keys.py` by file path, the pulled tree runs it only as a
module, and the first update warned `ModuleNotFoundError: core` and skipped the migration.

Both phases are `scripts/update_cli.py` (M034-S05-T02 / T03). The tests run a real engine
copy (the bash oracle's template) behind the oracle's `uv` shim, which logs how uv was
called and syncs nothing; the bash oracle's update records hold the rest.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import pytest

from ._oracle import (
    build_engine_template,
    git,
    install_engine,
    run_wiki,
    track_local_origin,
    write_uv_shim,
)

MARKER = "POST-PULL-FROM-PULLED-WIKI"


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


# ── phase 1 hands over to the pulled engine ─────────────────────────────────────


def test_post_pull_steps_run_from_the_pulled_wiki(tmp_path: Path, engine_template: Path) -> None:
    """origin moves on and its `wiki` becomes a stub that announces itself; the update
    started by the OLD engine must hand over to that stub, with the revision from before
    the pull, for everything after the pull."""
    env = _vault(tmp_path, engine_template)
    origin = track_local_origin(env["wiki"], tmp_path / "origin", ahead=False)
    (origin / "wiki").write_text(f'#!/usr/bin/env bash\necho "{MARKER} $*"\n', encoding="utf-8")
    git(origin, "commit", "-q", "-am", "pulled engine")
    before = git(env["wiki"], "rev-parse", "--short", "HEAD")

    proc = run_wiki(env["vault"], env["home"], env["bin"], "update", "--no-skills")

    assert proc.returncode == 0, proc.stderr
    assert f"{MARKER} update --post-pull {before} --no-skills" in proc.stdout, (
        "the post-pull phase ran from the code that started the update, not from the "
        "pulled one:\n" + proc.stdout + proc.stderr
    )


# ── phase 2, `wiki update --post-pull <rev>` ────────────────────────────────────


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


def test_help_anywhere_in_the_flags(tmp_path: Path, engine_template: Path) -> None:
    """The bash's flag loop took `--help` in any position; the dispatcher intercepts only
    the first argument, so the handler answers the rest."""
    env = _vault(tmp_path, engine_template)

    proc = run_wiki(env["vault"], env["home"], env["bin"], "update", "--no-skills", "--help")

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("wiki update — git pull --ff-only the .wiki/ checkout\n")
