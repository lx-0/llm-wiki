"""The bash oracle (M034-S01) — what the bash-owned commands print, recorded BEFORE any of
them is ported to Python.

Each case runs the real `wiki` out of an engine copy in the fixture vault (see
tests/_oracle.py: `build_engine_copy`, `write_uv_shim`, `run_wiki`) with no TTY and a
scratch HOME, and compares the normalised exit code, stdout and stderr against
tests/golden/bash/<name>.txt. The goldens are the contract the S01–S05 ports are held to: a
port must reproduce them, or change them in the same commit with the reason.

Two kinds of case:

- **Read-only** (S01-T01, plus four that reach `_dispatch_python`, S01-T04): one shared
  vault; the golden is the command's output.
- **Mutating** (S01-T02): a fresh vault and HOME per case, the answers to the bash's
  line-based prompts scripted on stdin, an optional preparation step whose effect is not
  recorded. The golden adds the change the command made under the vault and under HOME
  (`tree_manifest` / `manifest_diff`).

`update` is S05-T01's.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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
    # through `_dispatch_python` into scripts/cli.py (S01-T04's hop is held to these): a
    # handler child, the unknown-command path, the dispatcher's help intercept, an OAuth alias
    "collect-list": ("collect", "--list"),
    "dispatch-unknown": ("bogus",),
    "dispatch-command-help": ("links", "--help"),
    "auth-alias": ("gmail-auth",),
    # error and alternate-spelling paths of the wrappers S01-T05 ports
    "menu-unknown": ("menu", "bogus"),
    "help-short-flag": ("-h",),
    # the argv routing S01-T06 ports, on its deterministic paths (a dry-run sweep's stderr
    # carries clock times and probabilistic weights — unit tests pin those routes)
    "dream-unknown": ("dream", "bogus"),
    "dream-entity-bare": ("dream-entity",),
    "dream-web-research-help": ("dream", "web-research", "--help"),
    "auth-alias-help": ("gmeet-auth", "--help"),
    # `wiki config`'s error paths, before S02-T02 ports it
    "config-get-usage": ("config", "get"),
    "config-set-usage": ("config", "set", "models.compile_model"),
    "config-get-unknown-key": ("config", "get", "nope.key"),
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
        # <VENV> is the engine's Python environment: the test venv the shim's `uv run`
        # execs, or the vault's own `.wiki/.venv` that the one hop (S01-T04) runs from — in
        # the fixture a venv of links onto the test venv, the same interpreter either way
        str(Path(sys.executable).parent.parent): "<VENV>",
        str(env["vault"] / ".wiki" / ".venv"): "<VENV>",
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


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _operator_data_in_every_merged_file(env: dict[str, Path]) -> None:
    """After a seed, the operator's own data in each file seed merges instead of copying."""
    _seeded(env)
    obs = env["vault"] / ".obsidian"
    plugins = json.loads((obs / "community-plugins.json").read_text(encoding="utf-8"))
    _write_json(obs / "community-plugins.json", [p for p in plugins if p != "homepage"] + ["mine"])
    _write_json(obs / "appearance.json", {"cssTheme": "Minimal", "enabledCssSnippets": ["mine"]})
    meta_bind = obs / "plugins" / "obsidian-meta-bind-plugin" / "data.json"
    data = json.loads(meta_bind.read_text(encoding="utf-8"))
    data["devMode"] = True
    data["buttonTemplates"][0]["label"] = "an operator's label on an engine button"
    data["buttonTemplates"].append({"id": "btn-mine", "label": "Mine", "actions": []})
    _write_json(meta_bind, data)
    own = {"id": "my-own-command", "alias": "Mine", "platform_specific_commands": {"default": "x"}}
    stale = {"id": "agent-daily-digest", "alias": "a stale engine entry"}
    shell = obs / "plugins" / "obsidian-shellcommands" / "data.json"
    _write_json(shell, {"settings_version": "0.23.0", "shell_commands": [own, stale]})
    env_example = env["vault"] / ".claude" / ".env.example"
    kept = [
        ln for ln in env_example.read_text(encoding="utf-8").splitlines() if ln != "EXA_API_KEY="
    ]
    env_example.write_text("\n".join(kept) + "\n", encoding="utf-8")


def _shell_commands_in_the_legacy_object_form(env: dict[str, Path]) -> None:
    """A shell-commands config in the object form the engine's template carried (commands
    keyed by id, no `id` field) — the plugin, at the same settings_version, keeps an array."""
    _seeded(env)
    legacy = {
        "wiki-compile": {"alias": "Wiki: compile", "platform_specific_commands": {"default": "c"}},
        "my-own-command": {"alias": "Mine", "platform_specific_commands": {"default": "x"}},
    }
    shell = env["vault"] / ".obsidian" / "plugins" / "obsidian-shellcommands" / "data.json"
    _write_json(shell, {"settings_version": "0.23.0", "shell_commands": legacy})


def _graph_overlay_and_a_live_edit(env: dict[str, Path]) -> None:
    """An overlay for graph.json in .wiki/custom/, and the live file edited apart from it."""
    _seeded(env)
    _write_json(env["vault"] / ".wiki" / "custom" / ".obsidian" / "graph.json", {"scale": 1.5})
    graph = env["vault"] / ".obsidian" / "graph.json"
    data = json.loads(graph.read_text(encoding="utf-8"))
    data["scale"] = 3
    _write_json(graph, data)


def _two_configs_that_are_not_json(env: dict[str, Path]) -> None:
    _seeded(env)
    (env["vault"] / ".obsidian" / "community-plugins.json").write_text('["dataview",\n')
    (env["vault"] / ".obsidian" / "app.json").write_text('{"x": \n')


def _graph_search_now_an_object(env: dict[str, Path]) -> None:
    """A text setting replaced by an object — the leaf diff must not follow it into the
    template's string (M034-S04-T02)."""
    _seeded(env)
    graph = env["vault"] / ".obsidian" / "graph.json"
    data = json.loads(graph.read_text(encoding="utf-8"))
    data["search"] = {"query": "path:knowledge", "caseSensitive": True}
    graph.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _graph_overlay_not_json_and_a_live_edit(env: dict[str, Path]) -> None:
    """The overlay for graph.json broken, the live file edited — what `--force` must keep."""
    _graph_overlay_and_a_live_edit(env)
    (env["vault"] / ".wiki" / "custom" / ".obsidian" / "graph.json").write_text('{"scale": \n')


def _claude_hooks_at_user_scope(env: dict[str, Path]) -> None:
    _wiki(env, "hooks", "install", stdin="1\n1\ny\n")


def _drop_backups(cfg: Path) -> None:
    """The preparation's own backups. Backups are named to the second, so without this the
    case's backup is `<stamp>` or `<stamp>-2` depending on whether both landed in one."""
    for bak in cfg.parent.glob(f"{cfg.name}.bak.*"):
        bak.unlink()


def _claude_hooks_beside_another_tools(env: dict[str, Path]) -> None:
    _foreign_user_settings(env)
    _claude_hooks_at_user_scope(env)
    _drop_backups(env["home"] / ".claude" / "settings.json")


def _cursor_hooks_beside_another_tools(env: dict[str, Path]) -> None:
    """Cursor at project scope: another tool's bare entry, then the wiki's beside it."""
    cfg = env["vault"] / ".cursor" / "hooks.json"
    cfg.parent.mkdir(parents=True)
    other = {"type": "command", "command": "other-tool --start", "timeout": 5}
    cfg.write_text(
        json.dumps({"version": 1, "hooks": {"sessionStart": [other]}}, indent=2) + "\n",
        encoding="utf-8",
    )
    _wiki(env, "hooks", "install", stdin="4\n2\ny\n")
    _drop_backups(cfg)


def _claude_hooks_at_project_scope_only(env: dict[str, Path]) -> None:
    """The wiki's Claude hooks in the vault; the user's settings hold another tool's only."""
    _foreign_user_settings(env)
    _wiki(env, "hooks", "install", stdin="1\n2\ny\n")


def _unreadable_user_settings(env: dict[str, Path]) -> None:
    """The user's Claude settings, half written by another program: not JSON."""
    settings = env["home"] / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text('{"permissions": {"allow": [\n', encoding="utf-8")


def _truncated_user_settings_with_a_wiki_hook(env: dict[str, Path]) -> None:
    """The user's Claude settings cut off mid-write, after a wiki hook command: the text
    names the hook, the file is not JSON. The older relative form of the command, so the
    parse error's character offset does not depend on where the test vault lives."""
    settings = env["home"] / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    command = "uv run --project .wiki python .wiki/hooks/session-end.py"
    settings.write_text(
        '{"hooks": {"SessionEnd": [{"hooks": [{"command": ' + json.dumps(command) + "}\n",
        encoding="utf-8",
    )


def _a_permission_names_a_wiki_hook(env: dict[str, Path]) -> None:
    """A permission rule that names the wiki's hook command, and no hooks at all."""
    settings = env["home"] / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    command = f"cd '{env['vault']}/.wiki' && uv run python hooks/session-start.py"
    settings.write_text(
        json.dumps({"permissions": {"allow": [f"Bash({command})"]}}, indent=2) + "\n",
        encoding="utf-8",
    )


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


def _foreign_skill_dir(env: dict[str, Path]) -> None:
    """Another tool's skill under the engine skill's name, in the vault."""
    (env["vault"] / ".claude" / "skills" / "use-llm-wiki").mkdir(parents=True)


def _skills_linked_and_one_gone(env: dict[str, Path]) -> None:
    """The engine's skills linked, and an engine-owned link whose skill was removed."""
    _wiki(env, "skills", "install")
    gone = env["vault"] / ".claude" / "skills" / "gone-skill"
    gone.symlink_to("../../.wiki/skills/gone-skill")


def _skills_in_every_state(env: dict[str, Path]) -> None:
    """Global on; linked locally; a stale link; the global link into another vault; the
    registry holding this vault and one that is gone."""
    _skills_linked_and_one_gone(env)
    _wiki(env, "config", "set", "skills.global_install", "true")
    link = env["home"] / ".claude" / "skills" / "use-llm-wiki"
    link.parent.mkdir(parents=True)
    link.symlink_to(env["root"] / "other-vault" / ".wiki" / "skills" / "use-llm-wiki")
    registry = env["home"] / ".config" / "llm-wiki" / "vaults"
    registry.parent.mkdir(parents=True)
    registry.write_text(f"{env['vault']}\n{env['root'] / 'gone-vault'}\n", encoding="utf-8")


def _foreign_entries_at_both_link_paths(env: dict[str, Path]) -> None:
    _foreign_skill_dir(env)
    link = env["home"] / ".claude" / "skills" / "use-llm-wiki"
    link.parent.mkdir(parents=True)
    link.write_text("another tool's file\n", encoding="utf-8")


def _skills_linked_beside_a_foreign_one(env: dict[str, Path]) -> None:
    _wiki(env, "skills", "install")
    (env["vault"] / ".claude" / "skills" / "my-own-skill").mkdir()


def _engine_not_a_checkout(env: dict[str, Path]) -> None:
    """An engine that is not a git checkout (copied without its `.git`)."""
    shutil.rmtree(env["vault"] / ".wiki" / ".git")


def _shortcut_path(env: dict[str, Path]) -> Path:
    link = env["home"] / ".local" / "bin" / "wiki"
    link.parent.mkdir(parents=True, exist_ok=True)
    return link


def _shortcut_installed(env: dict[str, Path]) -> None:
    _wiki(env, "install-shortcut")


def _shortcut_to_another_vault(env: dict[str, Path]) -> None:
    _shortcut_path(env).symlink_to(env["root"] / "other-vault" / ".wiki" / "wiki")


def _regular_file_at_shortcut(env: dict[str, Path]) -> None:
    """Another program called `wiki` where the shortcut goes."""
    link = _shortcut_path(env)
    link.write_text("#!/bin/sh\necho another tool\n", encoding="utf-8")
    link.chmod(0o755)


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
    # S03-T02's fixes, recorded from the fixed bash: an uninstall removes only the wiki's
    # entries (a Claude group, a Cursor bare entry), says when there is nothing to remove,
    # and an install whose payload cannot be built fails instead of saying Done
    "hooks-uninstall-keeps-foreign": (
        ("hooks", "uninstall"),
        "\n1\ny\n",
        _claude_hooks_beside_another_tools,
    ),
    "hooks-uninstall-cursor-keeps-foreign": (
        ("hooks", "uninstall"),
        "\n2\ny\n",
        _cursor_hooks_beside_another_tools,
    ),
    "hooks-uninstall-nothing-to-remove": (
        ("hooks", "uninstall"),
        "\n1\ny\n",
        _claude_hooks_at_project_scope_only,
    ),
    # S03-T05's oracle-first record of three cases its port changed on purpose (see the
    # commit and CHANGELOG 0.7.18): a config that is not JSON, on install and on uninstall,
    # and a status whose only wiki command is a permission rule's text. Its port also
    # dropped `hooks-install-payload-fails`: hooks no longer use jq.
    "hooks-install-unreadable-config": (
        ("hooks", "install"),
        "1\n1\ny\n",
        _unreadable_user_settings,
    ),
    "hooks-uninstall-unreadable-config": (
        ("hooks", "uninstall"),
        "1\n1\ny\n",
        _truncated_user_settings_with_a_wiki_hook,
    ),
    "hooks-status-command-outside-hooks": (
        ("hooks", "status"),
        None,
        _a_permission_names_a_wiki_hook,
    ),
    "skills-install": (("skills", "install"), None, None),
    "skills-sync": (("skills", "sync"), None, None),
    "skills-install-global": (("skills", "install", "--global"), None, None),
    "skills-uninstall-global": (
        ("skills", "uninstall", "--global"),
        None,
        _global_skills_installed,
    ),
    # S03-T06's oracle-first record: the branches the four cases above do not reach
    "skills-install-with-collision": (("skills", "install"), None, _foreign_skill_dir),
    "skills-sync-prunes-stale": (("skills", "sync"), None, _skills_linked_and_one_gone),
    "skills-status-mixed": (("skills", "status"), None, _skills_in_every_state),
    "skills-status-collision": (
        ("skills", "status"),
        None,
        _foreign_entries_at_both_link_paths,
    ),
    "skills-uninstall": (("skills", "uninstall"), None, _skills_linked_beside_a_foreign_one),
    "skills-install-no-global": (
        ("skills", "install", "--no-global"),
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
    # before S04-T02: the merges over operator data, the overlay paths, the refusals
    "seed-merges-operator-data": (("seed",), None, _operator_data_in_every_merged_file),
    "seed-check-merges-pending": (("seed", "--check"), None, _operator_data_in_every_merged_file),
    "seed-shell-commands-legacy-form": (
        ("seed",),
        None,
        _shell_commands_in_the_legacy_object_form,
    ),
    "seed-check-with-overlay": (("seed", "--check"), None, _graph_overlay_and_a_live_edit),
    "seed-force-with-overlay": (
        ("seed", ".obsidian/graph.json", "--force"),
        None,
        _graph_overlay_and_a_live_edit,
    ),
    "seed-path-matches-nothing": (("seed", "nope.md"), None, _seeded),
    "seed-check-and-force": (("seed", "--check", "--force"), None, None),
    "seed-extract-custom-no-drift": (
        ("seed", "--extract-custom", ".obsidian/graph.json"),
        None,
        _seeded,
    ),
    "seed-broken-json": (("seed",), None, _two_configs_that_are_not_json),
    # what fixing the recording's finds added: the audit of a vault never seeded (every
    # missing-file branch), and the not-JSON paths of the audit, the capture and the overlay
    "seed-check-unseeded": (("seed", "--check"), None, None),
    "seed-check-broken-json": (("seed", "--check"), None, _two_configs_that_are_not_json),
    "seed-extract-custom-broken-json": (
        ("seed", "--extract-custom", ".obsidian/app.json"),
        None,
        _two_configs_that_are_not_json,
    ),
    "seed-force-broken-overlay": (
        ("seed", ".obsidian/graph.json", "--force"),
        None,
        _graph_overlay_not_json_and_a_live_edit,
    ),
    # T02's fix first: a value whose type changed (0.7.22)
    "seed-extract-custom-type-changed": (
        ("seed", "--extract-custom", ".obsidian/graph.json"),
        None,
        _graph_search_now_an_object,
    ),
    "install-shortcut": (("install-shortcut",), None, None),
    "install-shortcut-print-only": (("install-shortcut", "--print-only"), None, None),
    # before S02-T04: a second run, a link to another vault, and a regular file in the way
    "install-shortcut-already-linked": (("install-shortcut",), None, _shortcut_installed),
    "install-shortcut-replaces-other-vault": (
        ("install-shortcut",),
        None,
        _shortcut_to_another_vault,
    ),
    "install-shortcut-regular-file": (("install-shortcut",), None, _regular_file_at_shortcut),
    "version-not-a-checkout": (("version",), None, _engine_not_a_checkout),
    # `wiki config` before S02-T02: a value that does not coerce writes nothing; bare
    # `wiki config` is the interactive editor — exit at once (8), or models (1) →
    # models.dream_model (4) → a value, then exit
    "config-set-uncoercible": (
        ("config", "set", "scheduling.compile_after_hour", "late"),
        None,
        None,
    ),
    "config-edit-exit": (("config",), "8\n", None),
    "config-edit-set": (("config",), "1\n4\nclaude-sonnet-4-6\n8\n", None),
    # the wizard before S02-T03: a refused URL then the current one, haiku, a refused hour
    # then 7, procmail / local-LLM / global skill all yes
    "config-wizard-validates": (
        ("config", "wizard"),
        "ftp://x\n\n3\n25\n7\ny\ny\ny\n",
        None,
    ),
    # every wizard answer the default, then the hooks step — whose own answers (claude, user
    # scope, confirm) come from the same stdin: after the port a child reads them
    "setup-with-hooks": (("setup",), "\n\n\n\n\n\ny\n1\n1\ny\n", None),
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


def test_an_install_that_fails_is_not_reported_done(fresh_vault: dict[str, Path]) -> None:
    """Found in S02-T05's end-to-end run: an install that wrote nothing ended `✓ Done.
    Restart agent CLIs…` with exit 0 (then a `jq` that could not run; since the port, any
    agent that fails, here a config that is not JSON)."""
    _unreadable_user_settings(fresh_vault)
    settings = fresh_vault["home"] / ".claude" / "settings.json"

    run = run_wiki(
        fresh_vault["vault"],
        fresh_vault["home"],
        fresh_vault["bin"],
        *("hooks", "install"),
        stdin="1\n1\ny\n",
    )

    assert run.returncode == 1
    assert "Done" not in run.stdout
    assert "claude (user): " in run.stderr
    assert "is not valid JSON — left as it was" in run.stderr
    assert "1 of 1" in run.stderr
    assert settings.read_text(encoding="utf-8") == '{"permissions": {"allow": [\n'


def test_the_engine_template_spawns_no_background_git_maintenance(tmp_path: Path) -> None:
    """A commit starts a detached `git maintenance run --auto`. On the CI runner (git 2.55)
    it packed a fresh template's loose objects while a test was copying the template
    (`shutil.Error: … .git/objects/0a: No such file or directory`). The template, and every
    copy of it, has automatic maintenance off."""
    template = build_engine_template(tmp_path / ".wiki")
    identity = ["-c", "user.name=probe", "-c", "user.email=probe@example.invalid"]
    trace = subprocess.run(
        ["git", "-C", str(template), *identity, "commit", "-q", "--allow-empty", "-m", "probe"],
        env={**os.environ, "GIT_TRACE": "1"},
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    assert "maintenance run" not in trace
    assert "gc --auto" not in trace
