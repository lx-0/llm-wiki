"""`wiki seed` on a real vault: what recording the bash seed turned up (M034-S04-T01).

Each test runs the real `wiki` out of an engine copy in a fixture vault.

The dashboard's buttons (0.7.20):
- a fresh vault got no Shell commands config at all — the template was only ever merged
  into an existing file;
- the merge read the template's id-keyed object form as a list of anonymous entries;
- the engine's own commands never reached an existing config (a vault's "refresh stats"
  ran a script that had moved months before);
- two agent buttons were defined in neither registry;
- the dashboard rewrite said "already up to date" about a file it had just changed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from core.daily_capture import SUMMARIZE_BUTTON_BLOCK
from dashboard import agent_buttons

from ._oracle import (
    build_engine_template,
    build_fixture_vault,
    install_engine,
    run_wiki,
    write_uv_shim,
)

SHELL = Path(".obsidian/plugins/obsidian-shellcommands/data.json")
META_BIND = Path(".obsidian/plugins/obsidian-meta-bind-plugin/data.json")


@pytest.fixture(scope="module")
def engine_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_engine_template(tmp_path_factory.mktemp("engine") / ".wiki")


@pytest.fixture
def env(tmp_path: Path, engine_template: Path) -> dict[str, Path]:
    vault = build_fixture_vault(tmp_path)
    install_engine(vault, engine_template)
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    write_uv_shim(bin_dir)
    return {"vault": vault, "home": home, "bin": bin_dir}


def _seed(env: dict[str, Path], *args: str) -> str:
    run = run_wiki(env["vault"], env["home"], env["bin"], "seed", *args)
    assert run.returncode == 0, run.stdout + run.stderr
    return run.stdout


def _read(env: dict[str, Path], rel: Path) -> dict:
    return json.loads((env["vault"] / rel).read_text(encoding="utf-8"))


def _write(env: dict[str, Path], rel: Path, data: object) -> None:
    (env["vault"] / rel).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _engine_command_ids(env: dict[str, Path]) -> set[str]:
    template = json.loads(
        (env["vault"] / ".wiki" / "templates" / SHELL).read_text(encoding="utf-8")
    )["shell_commands"]
    own = set(template) if isinstance(template, dict) else {c["id"] for c in template}
    return own | {e["id"] for e in agent_buttons.shell_commands_entries()}


def _lines_about(out: str, name: str) -> list[str]:
    return [line for line in out.splitlines() if name in line]


def test_a_fresh_seed_wires_every_dashboard_button(env: dict[str, Path]) -> None:
    _seed(env)
    shell = _read(env, SHELL)
    commands = shell["shell_commands"]
    assert isinstance(commands, list)
    assert {c["id"] for c in commands} == _engine_command_ids(env)
    prefix = shell["command_palette_prefix"]
    aliases = {c["alias"] for c in commands}
    buttons = _read(env, META_BIND)["buttonTemplates"]
    dashboard = (env["vault"] / "dashboard.md").read_text(encoding="utf-8")
    referenced = set(re.findall(r"BUTTON\[([^\]]+)\]", dashboard))
    assert referenced <= {b["id"] for b in buttons}, "a dashboard button is defined nowhere"
    runs = [a["command"] for b in buttons for a in b["actions"]]
    runs += re.findall(r'command: "([^"]+)"', SUMMARIZE_BUTTON_BLOCK)
    missing = {r for r in runs if r.startswith(prefix) and r.removeprefix(prefix) not in aliases}
    assert not missing, f"buttons run commands the vault does not have: {missing}"


def test_seed_brings_the_engine_commands_into_an_existing_config_in_place(
    env: dict[str, Path],
) -> None:
    """The live vault's case: an engine command with the plugin's own fields and an outdated
    command line, after one of the operator's."""
    _seed(env)
    own = {"id": "my-own-command", "alias": "Mine", "platform_specific_commands": {"default": "x"}}
    stale = {
        "id": "wiki-refresh-stats",
        "alias": "Wiki: refresh dashboard stats",
        "platform_specific_commands": {
            "default": "uv run --project .wiki python .wiki/scripts/dashboard_stats.py"
        },
        "debounce": None,
    }
    _write(env, SHELL, {"settings_version": "0.23.0", "shell_commands": [own, stale]})
    _seed(env)
    commands = _read(env, SHELL)["shell_commands"]
    assert commands[0] == own
    assert commands[1]["id"] == "wiki-refresh-stats"
    assert commands[1]["platform_specific_commands"] == {
        "default": "./.wiki/wiki refresh-dashboards"
    }
    assert "debounce" in commands[1], "a field the engine does not ship was dropped"
    assert {c["id"] for c in commands} == _engine_command_ids(env) | {"my-own-command"}


def test_seed_reads_the_legacy_object_form_without_dropping_ids(env: dict[str, Path]) -> None:
    _seed(env)
    mine = {"alias": "Mine", "platform_specific_commands": {"default": "x"}}
    legacy = {
        "wiki-compile": {"alias": "Wiki: compile", "platform_specific_commands": {"default": "c"}},
        "my-own-command": mine,
    }
    _write(env, SHELL, {"settings_version": "0.23.0", "shell_commands": legacy})
    _seed(env)
    commands = _read(env, SHELL)["shell_commands"]
    assert [c.get("id") for c in commands[:2]] == ["wiki-compile", "my-own-command"]
    assert commands[1] == {**mine, "id": "my-own-command"}
    assert commands[0]["platform_specific_commands"] == {"default": "./.wiki/wiki compile"}


def _seeded_files(vault: Path) -> dict[str, bytes]:
    """What seed owns: everything but the engine and the dashboard caches it refreshes."""
    return {
        str(p.relative_to(vault)): p.read_bytes()
        for p in sorted(vault.rglob("*"))
        if p.is_file()
        and p.relative_to(vault).parts[0] != ".wiki"
        and not p.name.startswith("_dashboard-")
    }


def test_a_second_seed_changes_nothing_and_the_audit_finds_no_drift(
    env: dict[str, Path],
) -> None:
    _seed(env)
    before = _seeded_files(env["vault"])
    _seed(env)
    after = _seeded_files(env["vault"])
    assert [name for name in before if before[name] != after.get(name)] == []
    audit = _seed(env, "--check")
    assert _lines_about(audit, "drifted") == []
    assert _lines_about(audit, "missing") == []


def test_the_audit_reports_an_engine_button_seed_would_restore(env: dict[str, Path]) -> None:
    _seed(env)
    data = _read(env, META_BIND)
    data["buttonTemplates"][0]["label"] = "an operator's label"
    _write(env, META_BIND, data)
    audit = _seed(env, "--check")
    lines = _lines_about(audit, "obsidian-meta-bind-plugin/data.json")
    assert len(lines) == 1
    assert "drifted" in lines[0]
    assert data["buttonTemplates"][0]["id"] in lines[0]


def test_the_audit_names_a_missing_shell_commands_config(env: dict[str, Path]) -> None:
    audit = _seed(env, "--check")
    lines = _lines_about(audit, "obsidian-shellcommands/data.json")
    assert len(lines) == 1
    assert "missing" in lines[0]


def test_the_dashboard_rewrite_reports_what_it_did(env: dict[str, Path]) -> None:
    _seed(env)
    dashboard = env["vault"] / "dashboard.md"
    refs = agent_buttons.inline_refs()
    dashboard.write_text(
        dashboard.read_text(encoding="utf-8").replace(refs, "`BUTTON[btn-gone]`"),
        encoding="utf-8",
    )
    out = _seed(env)
    assert refs in dashboard.read_text(encoding="utf-8")
    lines = _lines_about(out, "agent-buttons")
    assert len(lines) == 1
    assert "already up to date" not in lines[0]
