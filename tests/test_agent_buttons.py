"""The agent buttons: what the `button:` blocks of `prompts/agents/*.md` put into the vault's
two plugin registries and its dashboard, and the engine templates that must agree with them.

Meta-Bind (1.4 on) resolves a `BUTTON[id]` only against its own registry — the
`buttonTemplates` of its data.json — and a button runs a Shell commands command by its
palette name. So a dashboard button works only if both registries carry it: the engine's
own entries come from the templates, the agent entries from `dashboard.agent_buttons`.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from core.daily_capture import SUMMARIZE_BUTTON_BLOCK
from dashboard import agent_buttons

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = REPO_ROOT / "templates"
SHELL_COMMANDS = TEMPLATES / ".obsidian" / "plugins" / "obsidian-shellcommands" / "data.json"
META_BIND = TEMPLATES / ".obsidian" / "plugins" / "obsidian-meta-bind-plugin" / "data.json"


def _template(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_button_spec_yields_a_shell_command_in_the_plugins_list_form() -> None:
    specs = agent_buttons.discover()
    entries = agent_buttons.shell_commands_entries()
    assert specs, "no agent spec declares a button"
    assert [e["id"] for e in entries] == [s.button.shell_command_id for s in specs if s.button]
    for spec, entry in zip(specs, entries, strict=True):
        assert entry["alias"] == f"Wiki: agent {spec.id}"
        assert entry["platform_specific_commands"] == {"default": f"./.wiki/wiki agent {spec.id}"}


def test_every_button_spec_yields_a_meta_bind_template_that_runs_its_command() -> None:
    specs = agent_buttons.discover()
    templates = agent_buttons.meta_bind_templates()
    assert [t["id"] for t in templates] == [f"btn-{s.id}" for s in specs]
    for spec, template in zip(specs, templates, strict=True):
        assert spec.button is not None
        assert template["label"] == spec.button.label
        assert template["hidden"] is True
        assert template["actions"] == [
            {"type": "command", "command": f"Shell commands: Wiki: agent {spec.id}"}
        ]


def test_the_templates_leave_the_agent_entries_to_the_generator() -> None:
    """A template copy of a generated entry drifts from it: `btn-dream-cycle` was referenced
    by the dashboard and defined in neither registry. The generator is their one source."""
    shell_ids = {e["id"] for e in _template(SHELL_COMMANDS)["shell_commands"]}
    button_ids = {b["id"] for b in _template(META_BIND)["buttonTemplates"]}
    assert shell_ids.isdisjoint(e["id"] for e in agent_buttons.shell_commands_entries())
    assert button_ids.isdisjoint(t["id"] for t in agent_buttons.meta_bind_templates())


def test_the_shell_commands_template_is_in_the_plugins_list_form() -> None:
    """Plugin 0.23 keeps a list of `{id, …}`; the id-keyed object is the form it migrates
    away from (and the merge must not read it as a list of anonymous entries)."""
    commands = _template(SHELL_COMMANDS)["shell_commands"]
    assert isinstance(commands, list)
    assert all(isinstance(c.get("id"), str) for c in commands)


def test_the_engine_ships_the_icon_names_the_plugin_keeps() -> None:
    """Shell commands 0.23 renames these four on load (`ICON_MIGRATIONS`). The merge gives an
    engine entry the engine's fields, so an old name would be undone by every seed and redone
    by the plugin on the next start — the file flip-flopping, a backup each time."""
    renamed_by_the_plugin = {"files", "shield-check", "refresh-cw", "bot"}
    entries = _template(SHELL_COMMANDS)["shell_commands"] + agent_buttons.shell_commands_entries()
    assert {e["icon"] for e in entries}.isdisjoint(renamed_by_the_plugin)


def test_every_dashboard_button_is_defined_and_runs_a_known_command() -> None:
    shell = _template(SHELL_COMMANDS)
    prefix = shell["command_palette_prefix"]
    aliases = {c["alias"] for c in shell["shell_commands"]}
    aliases |= {e["alias"] for e in agent_buttons.shell_commands_entries()}
    buttons = _template(META_BIND)["buttonTemplates"] + agent_buttons.meta_bind_templates()
    dashboard = (TEMPLATES / "dashboard.md").read_text(encoding="utf-8")
    referenced = set(re.findall(r"BUTTON\[([^\]]+)\]", dashboard))
    assert referenced <= {b["id"] for b in buttons}, "a dashboard button is defined nowhere"
    commands = [a["command"] for b in buttons for a in b["actions"]]
    commands += re.findall(r'command: "([^"]+)"', SUMMARIZE_BUTTON_BLOCK)
    shell_runs = [c.removeprefix(prefix) for c in commands if c.startswith(prefix)]
    assert shell_runs
    assert set(shell_runs) <= aliases, "a button runs a command the plugin does not have"


def test_the_dashboard_template_already_carries_the_generated_agent_buttons(
    tmp_path: Path,
) -> None:
    """Seed rewrites this region; a template that differs from it reads as drifted on every
    run after the first."""
    dashboard = tmp_path / "dashboard.md"
    shutil.copy(TEMPLATES / "dashboard.md", dashboard)
    assert agent_buttons.update_dashboard(dashboard) is False


def test_rewriting_the_dashboard_region_says_nothing_when_its_markers_are_there(
    tmp_path: Path, capsys
) -> None:
    dashboard = tmp_path / "dashboard.md"
    dashboard.write_text(
        "# Dashboard\n<!-- agent-buttons:begin -->\nold\n<!-- agent-buttons:end -->\n",
        encoding="utf-8",
    )
    assert agent_buttons.update_dashboard(dashboard) is True
    assert agent_buttons.inline_refs() in dashboard.read_text(encoding="utf-8")
    assert capsys.readouterr().err == ""
