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

What seed reports (0.7.21):
- the plugin-list audit gave the merged count as what "the engine ships";
- the plugin-list merges rewrote a current file in their own order and format;
- a config that is not JSON was called drifted, with advice to capture it into an overlay,
  which then said it already matched the engine template;
- a broken overlay was ignored in silence — `--force` re-derived the template alone over
  the operator's file and reported "template⊕overlay";
- a path that matched nothing exited 0, and its list of seedable paths was short of two;
- the audit said "kept existing", and the drift advice was `--force` for the whole vault.
"""

from __future__ import annotations

import fnmatch
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


def test_seed_refuses_a_directory_that_is_not_a_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Seed writes a whole vault's templates. Called straight through `cli.main`, as a test
    did, it ran against the checkout's parent and filled it with a vault (M034-S04-T04). The
    bash `wiki` guards every command; the command guards itself too."""
    import seed_cli

    not_a_vault = tmp_path / "somewhere"
    not_a_vault.mkdir()
    monkeypatch.setattr(seed_cli, "ROOT_DIR", not_a_vault)
    for argv in ([], ["--force"], ["--extract-custom", ".obsidian/graph.json"]):
        assert seed_cli.main(argv) == 1
        assert "is not an Obsidian vault" in capsys.readouterr().err
    assert list(not_a_vault.iterdir()) == []


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


# ── what seed reports (0.7.21) ────────────────────────────────────────────────

COMMUNITY = Path(".obsidian/community-plugins.json")
APPEARANCE = Path(".obsidian/appearance.json")
APP = Path(".obsidian/app.json")
GRAPH = Path(".obsidian/graph.json")


def test_the_audit_names_the_plugins_seed_would_enable(env: dict[str, Path]) -> None:
    _seed(env)
    _write(env, COMMUNITY, [p for p in _read(env, COMMUNITY) if p != "homepage"])
    lines = _lines_about(_seed(env, "--check"), "community-plugins.json")
    assert len(lines) == 1
    assert "drifted" in lines[0]
    assert "homepage" in lines[0]


def test_seed_leaves_a_current_plugin_list_as_the_operator_wrote_it(
    env: dict[str, Path],
) -> None:
    _seed(env)
    reversed_list = json.dumps(_read(env, COMMUNITY)[::-1]) + "\n"
    (env["vault"] / COMMUNITY).write_text(reversed_list, encoding="utf-8")
    compact = '{"cssTheme":"Minimal","enabledCssSnippets":["wiki-dashboard"]}\n'
    (env["vault"] / APPEARANCE).write_text(compact, encoding="utf-8")
    before = {rel: (env["vault"] / rel).read_bytes() for rel in (COMMUNITY, APPEARANCE)}
    out = _seed(env)
    assert {rel: (env["vault"] / rel).read_bytes() for rel in before} == before
    for rel in before:
        assert "up-to-date" in _lines_about(out, rel.name)[0]


def test_a_config_that_is_not_json_is_named_so(env: dict[str, Path]) -> None:
    _seed(env)
    (env["vault"] / APP).write_text('{"x": \n', encoding="utf-8")
    for args in ((), ("--check",)):
        lines = _lines_about(_seed(env, *args), str(APP))
        assert len(lines) == 1
        assert "not valid JSON" in lines[0]
        assert "extract-custom" not in lines[0]


def test_extract_custom_refuses_a_file_that_is_not_json(env: dict[str, Path]) -> None:
    _seed(env)
    (env["vault"] / APP).write_text('{"x": \n', encoding="utf-8")
    run = run_wiki(env["vault"], env["home"], env["bin"], "seed", "--extract-custom", str(APP))
    assert run.returncode == 1
    assert "not valid JSON" in run.stderr
    assert not (env["vault"] / ".wiki" / "custom" / APP).exists()


def test_extract_custom_captures_a_value_whose_type_changed(env: dict[str, Path]) -> None:
    """Text replaced by an object: the leaf diff followed the new object's path into the
    template's string, jq stopped, and `set -e` ended the run with exit 5 and no word
    (M034-S04-T02, 0.7.22)."""
    _seed(env)
    data = _read(env, GRAPH)
    data["search"] = {"query": "path:knowledge", "caseSensitive": True}
    _write(env, GRAPH, data)
    run = run_wiki(env["vault"], env["home"], env["bin"], "seed", "--extract-custom", str(GRAPH))
    assert run.returncode == 0, run.stdout + run.stderr
    overlay = json.loads((env["vault"] / ".wiki" / "custom" / GRAPH).read_text(encoding="utf-8"))
    assert overlay == {"search": data["search"]}
    before = (env["vault"] / GRAPH).read_bytes()
    _seed(env, str(GRAPH), "--force")
    assert json.loads((env["vault"] / GRAPH).read_bytes()) == json.loads(before)


def test_extract_custom_keeps_a_setting_turned_off(env: dict[str, Path]) -> None:
    """jq's `paths(scalars)` drops a leaf whose value is false (its `select` tests the value
    itself), so a setting turned off never reached the overlay, and the `--force` seed
    advised afterwards turned it back on — lxw's graph lost showTags / hideUnresolved
    that way (M034-S04-T02, 0.7.23)."""
    _seed(env)
    data = _read(env, GRAPH)
    assert data["showTags"] is True
    data["showTags"] = False
    data["scale"] = 2
    _write(env, GRAPH, data)
    run = run_wiki(env["vault"], env["home"], env["bin"], "seed", "--extract-custom", str(GRAPH))
    assert run.returncode == 0, run.stdout + run.stderr
    overlay = json.loads((env["vault"] / ".wiki" / "custom" / GRAPH).read_text(encoding="utf-8"))
    assert overlay == {"showTags": False, "scale": 2}
    assert "(2 override(s))" in run.stdout
    _seed(env, str(GRAPH), "--force")
    assert _read(env, GRAPH)["showTags"] is False


def test_extract_custom_refuses_a_file_seed_merges(env: dict[str, Path]) -> None:
    """community-plugins.json has a template, so the capture went on, and on a changed list
    it said "could not compute the drift" — the cause is that seed merges it (0.7.24)."""
    _seed(env)
    _write(env, COMMUNITY, _read(env, COMMUNITY)[1:])
    run = run_wiki(
        env["vault"], env["home"], env["bin"], "seed", "--extract-custom", str(COMMUNITY)
    )
    assert run.returncode == 1
    assert "merged by seed" in run.stderr
    assert not (env["vault"] / ".wiki" / "custom" / COMMUNITY).exists()


def test_extract_custom_refuses_a_file_without_an_overlay(env: dict[str, Path]) -> None:
    """README.md has a template too; the capture called it "not valid JSON" (0.7.24)."""
    _seed(env)
    run = run_wiki(env["vault"], env["home"], env["bin"], "seed", "--extract-custom", "README.md")
    assert run.returncode == 1
    assert "not overlay-managed" in run.stderr


def test_a_broken_overlay_leaves_its_file_alone(env: dict[str, Path]) -> None:
    _seed(env)
    overlay = env["vault"] / ".wiki" / "custom" / GRAPH
    overlay.parent.mkdir(parents=True)
    overlay.write_text('{"scale": \n', encoding="utf-8")
    data = _read(env, GRAPH)
    data["scale"] = 3
    _write(env, GRAPH, data)
    before = (env["vault"] / GRAPH).read_bytes()
    out = _seed(env, str(GRAPH), "--force")
    assert (env["vault"] / GRAPH).read_bytes() == before
    lines = _lines_about(out, "not valid JSON")
    assert len(lines) == 1
    assert ".wiki/custom/.obsidian/graph.json" in lines[0]
    assert "re-derived" not in out


def test_a_path_that_matches_nothing_is_an_error_naming_every_seedable_path(
    env: dict[str, Path],
) -> None:
    seeded = [line.split("seeded ", 1)[1] for line in _seed(env).splitlines() if "seeded " in line]
    run = run_wiki(env["vault"], env["home"], env["bin"], "seed", "nope.md")
    assert run.returncode == 1
    assert "'nope.md'" in run.stderr
    listed = re.findall(r"[\w.<>*/-]+", run.stderr.split("seedable paths:", 1)[1])
    patterns = [re.sub(r"<[^>]+>", "*", p) for p in listed]
    unlisted = [s for s in seeded if not any(fnmatch.fnmatch(s, p) for p in patterns)]
    assert seeded
    assert not unlisted, f"seedable but not listed: {unlisted}"


def test_the_audit_never_says_it_kept_anything(env: dict[str, Path]) -> None:
    _seed(env)
    assert _lines_about(_seed(env, "--check"), "kept existing") == []


def test_drift_advice_overwrites_the_one_file_not_the_vault(env: dict[str, Path]) -> None:
    """`wiki seed --force` overwrites every drifted file; the advice is about one."""
    _seed(env)
    agents_md = env["vault"] / "AGENTS.md"
    agents_md.write_text(agents_md.read_text(encoding="utf-8") + "\nAn operator edit.\n")
    for args in ((), ("--check",)):
        lines = _lines_about(_seed(env, *args), "AGENTS.md")
        assert len(lines) == 1
        assert "`wiki seed AGENTS.md --force`" in lines[0]
