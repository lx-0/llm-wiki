"""The bash oracle (M034-S01) — what the bash-owned commands print, recorded BEFORE any of
them is ported to Python.

Each case runs the real `wiki` out of an engine copy in the fixture vault (see
tests/_oracle.py: `build_engine_copy`, `write_uv_shim`, `run_wiki`) with no TTY and a
scratch HOME, and compares the normalised exit code, stdout and stderr against
tests/golden/bash/<name>.txt. The goldens are the contract the S01–S05 ports are held to: a
port must reproduce them, or change them in the same commit with the reason.

Two kinds of case:

- **Read-only** (S01-T01): one shared vault; the golden is the command's output.
- **Mutating** (S01-T02): a fresh vault and HOME per case, the answers to the bash's
  line-based prompts scripted on stdin, an optional preparation step whose effect is not
  recorded. The golden adds the change the command made under the vault and under HOME
  (`tree_manifest` / `manifest_diff`).

`update` is S05-T01's.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ._oracle import (
    BASH_GOLDEN_DIR,
    NOT_AN_EFFECT,
    REPO_ROOT,
    assert_matches_golden,
    build_engine_template,
    build_fixture_vault,
    dump,
    install_engine,
    manifest_diff,
    normalise,
    normalise_text,
    render_run,
    run_wiki,
    tree_manifest,
    write_uv_shim,
)

READ_ONLY: dict[str, tuple[str, ...]] = {
    # the catalogue and the bare entry without a TTY
    "help": ("help",),
    "bare-no-tty": (),
    # the bash-owned help texts
    "config-help": ("config", "--help"),
    "hooks-help": ("hooks", "--help"),
    "setup-help": ("setup", "--help"),
    "skills-help": ("skills", "--help"),
    "update-help": ("update", "--help"),
    "seed-help": ("seed", "--help"),
    "menu-help": ("menu", "--help"),
    "doctor-help": ("doctor", "--help"),
    "dream-help": ("dream", "--help"),
    "dream-entity-help": ("dream-entity", "--help"),
    "install-shortcut-help": ("install-shortcut", "--help"),
    # state readers
    "version": ("version",),
    "status": ("status",),
    "menu-no-tty": ("menu",),
    "menu-json": ("menu", "--json"),
    "doctor-quick-json": ("doctor", "--quick", "--json"),
    "config-get": ("config", "get", "models.compile_model"),
    "config-keys": ("config", "keys"),
    "config-path": ("config", "path"),
    "config-status": ("config", "status"),
    "config-unknown": ("config", "bogus"),
    "hooks-status": ("hooks", "status"),
    "skills-status": ("skills", "status"),
}


@pytest.fixture(scope="session")
def engine_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The engine checkout every case's vault gets a copy of — built once per session."""
    return build_engine_template(tmp_path_factory.mktemp("engine") / ".wiki")


def _build_env(root: Path, template: Path) -> dict[str, Path]:
    """A fixture vault with an engine copy, a scratch HOME and the uv shim under ``root``."""
    vault = build_fixture_vault(root)
    install_engine(vault, template)
    # `config status` probes Ollama at the configured URL: a closed local port answers the
    # same on every machine (the default localhost:11434 would not on one running Ollama).
    (vault / ".wiki" / "config.yaml").write_text(
        "# bash-oracle fixture config — defaults, Ollama on a closed port\n"
        "models:\n  ollama_url: http://127.0.0.1:9\n",
        encoding="utf-8",
    )
    home = root / "home"
    home.mkdir()
    bin_dir = root / "bin"
    write_uv_shim(bin_dir)
    return {"vault": vault, "home": home, "bin": bin_dir, "root": root}


@pytest.fixture(scope="module")
def bash_vault(tmp_path_factory: pytest.TempPathFactory, engine_template: Path) -> dict[str, Path]:
    """One environment, built once: every read-only case only reads."""
    return _build_env(tmp_path_factory.mktemp("bash-oracle"), engine_template)


@pytest.fixture
def fresh_vault(tmp_path: Path, engine_template: Path) -> dict[str, Path]:
    """A new environment per mutating case."""
    return _build_env(tmp_path, engine_template)


def _placeholders(env: dict[str, Path]) -> dict[str, str]:
    return {
        str(env["vault"]): "<VAULT>",
        str(env["home"]): "<HOME>",
        str(env["bin"]): "<BIN>",
        str(env["root"]): "<ROOT>",
        str(REPO_ROOT): "<REPO>",
        str(Path(sys.executable).parent.parent): "<VENV>",
    }


# Counts of the machine, not the vault: the eviction check walks the interpreter's env,
# whose file count differs between a laptop and the CI runner (324 vs 321 on first run).
_MACHINE_COUNTS = frozenset({"scanned"})


def _blank_machine_counts(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("N" if k in _MACHINE_COUNTS else _blank_machine_counts(v)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_blank_machine_counts(v) for v in value]
    return value


def record(env: dict[str, Path], args: tuple[str, ...]) -> str:
    run = run_wiki(env["vault"], env["home"], env["bin"], *args)
    placeholders = _placeholders(env)
    if "--json" in args and run.returncode in (0, 1):
        # A JSON payload is compared as parsed + normalised JSON (the M033 oracle's rule:
        # digits in free text → N), so a humanised age cannot flake it. Paths and git
        # revisions go first, on the raw text: the engine copy's commit hash depends on the
        # tree it was copied from.
        raw = normalise_text(run.stdout, placeholders=placeholders)
        payload = _blank_machine_counts(normalise(json.loads(raw), placeholders=placeholders))
        run = type(run)(run.args, run.returncode, dump(payload), run.stderr)
    return render_run(args, run, placeholders)


@pytest.mark.parametrize("name", sorted(READ_ONLY))
def test_bash_command_matches_golden(bash_vault, request, name: str) -> None:
    text = record(bash_vault, READ_ONLY[name])
    assert_matches_golden(request, f"{name}.txt", text, BASH_GOLDEN_DIR)


# ── mutating commands (S01-T02) ───────────────────────────────────────────────


def _wiki(env: dict[str, Path], *args: str, stdin: str | None = None) -> None:
    """A preparation step: run, and insist it worked (its effect is not recorded)."""
    run = run_wiki(env["vault"], env["home"], env["bin"], *args, stdin=stdin)
    assert run.returncode == 0, f"preparation `wiki {' '.join(args)}` failed:\n{run.stderr}"


def _seeded(env: dict[str, Path]) -> None:
    _wiki(env, "seed")


def _seeded_then_agents_md_edited(env: dict[str, Path]) -> None:
    _seeded(env)
    agents_md = env["vault"] / "AGENTS.md"
    agents_md.write_text(agents_md.read_text(encoding="utf-8") + "\nAn operator edit.\n")


def _seeded_then_app_json_edited(env: dict[str, Path]) -> None:
    _seeded(env)
    app = env["vault"] / ".obsidian" / "app.json"
    data = json.loads(app.read_text(encoding="utf-8"))
    data["oracleEdit"] = True
    app.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _seeded_then_graph_scaled(env: dict[str, Path]) -> None:
    _seeded(env)
    graph = env["vault"] / ".obsidian" / "graph.json"
    data = json.loads(graph.read_text(encoding="utf-8"))
    data["scale"] = 2.5
    graph.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _claude_hooks_at_user_scope(env: dict[str, Path]) -> None:
    _wiki(env, "hooks", "install", stdin="1\n1\ny\n")


def _foreign_user_settings(env: dict[str, Path]) -> None:
    """Another tool's hook and a permission in the user's Claude settings, which the
    merge must keep."""
    settings = env["home"] / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Bash(ls:*)"]},
                "hooks": {
                    "SessionStart": [
                        {"matcher": "", "hooks": [{"type": "command", "command": "other-tool"}]}
                    ]
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _global_skills_installed(env: dict[str, Path]) -> None:
    _wiki(env, "skills", "install", "--global")


Prepare = Callable[[dict[str, Path]], None] | None

# name → (argv, scripted stdin, preparation)
MUTATING: dict[str, tuple[tuple[str, ...], str | None, Prepare]] = {
    "config-set": (("config", "set", "models.compile_model", "claude-sonnet-4-6"), None, None),
    # URL kept, sonnet, hour 20, procmail no, local LLM default, global skill no, hooks no
    "setup-wizard": (("setup",), "\n2\n20\nn\n\nn\nn\n", None),
    "hooks-install-claude-user": (("hooks", "install"), "1\n1\ny\n", None),
    "hooks-install-all-project": (("hooks", "install"), "1 2 3 4\n2\ny\n", None),
    "hooks-install-merges-existing": (("hooks", "install"), "1\n1\ny\n", _foreign_user_settings),
    "hooks-uninstall": (("hooks", "uninstall"), "\n1\ny\n", _claude_hooks_at_user_scope),
    "skills-install": (("skills", "install"), None, None),
    "skills-sync": (("skills", "sync"), None, None),
    "skills-install-global": (("skills", "install", "--global"), None, None),
    "skills-uninstall-global": (
        ("skills", "uninstall", "--global"),
        None,
        _global_skills_installed,
    ),
    "seed-fresh": (("seed",), None, None),
    "seed-check-after-edit": (("seed", "--check"), None, _seeded_then_agents_md_edited),
    "seed-force-after-edit": (("seed", "--force"), None, _seeded_then_agents_md_edited),
    "seed-one-path-force": (
        ("seed", ".obsidian/app.json", "--force"),
        None,
        _seeded_then_app_json_edited,
    ),
    "seed-extract-custom": (
        ("seed", "--extract-custom", ".obsidian/graph.json"),
        None,
        _seeded_then_graph_scaled,
    ),
    "install-shortcut": (("install-shortcut",), None, None),
    "install-shortcut-print-only": (("install-shortcut", "--print-only"), None, None),
}


def record_effect(
    env: dict[str, Path], args: tuple[str, ...], stdin: str | None, prepare: Prepare
) -> str:
    """Prepare, snapshot vault + HOME, run, snapshot again: the output and the change."""
    if prepare is not None:
        prepare(env)
    placeholders = _placeholders(env)

    def norm(text: str) -> str:
        return normalise_text(text, placeholders=placeholders)

    vault_before = tree_manifest(env["vault"], skip=NOT_AN_EFFECT)
    home_before = tree_manifest(env["home"])
    run = run_wiki(env["vault"], env["home"], env["bin"], *args, stdin=stdin)
    change = manifest_diff(
        vault_before, tree_manifest(env["vault"], skip=NOT_AN_EFFECT), "<VAULT>", norm
    ) + manifest_diff(home_before, tree_manifest(env["home"]), "<HOME>", norm)
    text = render_run(args, run, placeholders)
    if stdin is not None:
        text = text.replace("\nexit:", f"\nstdin: {stdin!r}\nexit:", 1)
    return (
        text + "--- change ---\n" + normalise_text(change or "(none)\n", placeholders=placeholders)
    )


@pytest.mark.parametrize("name", sorted(MUTATING))
def test_bash_mutating_command_matches_golden(fresh_vault, request, name: str) -> None:
    args, stdin, prepare = MUTATING[name]
    text = record_effect(fresh_vault, args, stdin, prepare)
    assert_matches_golden(request, f"{name}.txt", text, BASH_GOLDEN_DIR)
