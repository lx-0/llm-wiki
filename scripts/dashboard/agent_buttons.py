"""Discovery + auto-wiring helpers for agent-task Dashboard buttons.

Walks `prompts/agents/*.md` for specs that declare a `button:` block, and
gives `wiki seed` (scripts/seed_cli.py, in-process) the data it wires into the vault:

  1. a Shell commands entry per button, merged by id into the `shell_commands`
     of `.obsidian/plugins/obsidian-shellcommands/data.json`
  2. a Meta-Bind button template per button, merged by id into the
     `buttonTemplates` of `.obsidian/plugins/obsidian-meta-bind-plugin/data.json`
     — Meta-Bind (1.4 on) resolves `BUTTON[id]` against that registry only
  3. the inline `BUTTON[id]` references in a marked region of `dashboard.md`

The engine templates carry the engine's own entries and none of these: the
generator is the one source of the agent entries (`tests/test_agent_buttons.py`
holds the templates to that). The bash seed ran this module as a CLI through
`uv run`; with the seed in Python (M034-S04-T04) that entry point went.
"""

from __future__ import annotations

import sys
from pathlib import Path

from core import markers
from core.agent_spec import AgentSpec, parse_spec
from core.console import say
from core.paths import AGENT_SPECS_DIR

REGION_BEGIN = "<!-- agent-buttons:begin -->"
REGION_END = "<!-- agent-buttons:end -->"


def discover() -> list[AgentSpec]:
    specs: list[AgentSpec] = []
    if not AGENT_SPECS_DIR.exists():
        return specs
    for path in sorted(AGENT_SPECS_DIR.glob("*.md")):
        try:
            spec = parse_spec(path)
        except Exception as exc:
            say(
                f"# warn: skipping {path.name} — invalid spec: {exc}",
                file=sys.stderr,
            )
            continue
        if spec.button is None:
            continue
        specs.append(spec)
    return specs


def shell_commands_entries() -> list[dict]:
    """The agent buttons' entries for `data.json["shell_commands"]`, in the plugin's own
    list form (`{id, …}`). A button runs its entry by palette name, the alias."""
    out: list[dict] = []
    for spec in discover():
        assert spec.button is not None
        out.append(
            {
                "id": spec.button.shell_command_id,
                "platform_specific_commands": {
                    "default": f"./.wiki/wiki agent {spec.id}",
                },
                "shells": {},
                "alias": f"Wiki: agent {spec.id}",
                # the name the plugin migrates `bot` to — shipping the old one, every
                # seed would undo the plugin's migration and the plugin redo it
                "icon": "lucide-bot",
                "confirm_execution": False,
                "ignore_error_codes": [],
                "input_contents": {"stdin": None},
                "output_handlers": {
                    "stdout": {"handler": "notification", "convert_ansi_code": True},
                    "stderr": {"handler": "notification-bigger", "convert_ansi_code": True},
                },
                "output_wrappers": {"stdout": None, "stderr": None},
                "output_channel_order": "stdout-first",
                "output_handling_mode": "buffered",
                "events": {},
                "command_palette_availability": "enabled",
                "preactions": [],
                "variable_default_values": {},
            }
        )
    return out


def meta_bind_templates() -> list[dict]:
    """The agent buttons' entries for Meta-Bind's `data.json["buttonTemplates"]`: hidden
    templates the dashboard's inline `BUTTON[btn-<id>]` references render."""
    out: list[dict] = []
    for spec in discover():
        assert spec.button is not None
        b = spec.button
        out.append(
            {
                "label": b.label,
                "hidden": True,
                "class": "",
                "tooltip": b.tooltip or f"Run agent {spec.id}",
                "id": f"btn-{spec.id}",
                "style": b.style,
                "actions": [
                    {"type": "command", "command": f"Shell commands: Wiki: agent {spec.id}"}
                ],
            }
        )
    return out


def registry_entries(key: str) -> list[dict]:
    """The agent buttons' entries for one plugin registry, named by its key in the plugin's
    data.json: `shell_commands` (Shell commands) or `buttonTemplates` (Meta-Bind)."""
    makers = {"shell_commands": shell_commands_entries, "buttonTemplates": meta_bind_templates}
    return makers[key]()


def inline_refs() -> str:
    """Return a single-line string of inline `BUTTON[btn-<id>]` refs for the visible Run row."""
    refs = [f"`BUTTON[btn-{spec.id}]`" for spec in discover()]
    return " ".join(refs)


def has_region(text: str) -> bool:
    return markers.find_region(text, REGION_BEGIN, REGION_END) is not None


def update_dashboard(dashboard_path: Path) -> bool:
    """Replace the marked region `<!-- agent-buttons:begin --> … <!-- agent-buttons:end -->`
    in dashboard.md with the current inline refs.

    Idempotent — re-running with no spec changes produces no diff. Returns True
    if the file changed; a dashboard without the region (the markers are
    operator-seeded, not auto-inserted) is left untouched.
    """
    text = dashboard_path.read_text(encoding="utf-8")
    region = markers.find_region(text, REGION_BEGIN, REGION_END)
    if region is None:
        return False
    refs = inline_refs()
    if not refs:
        refs = "_(no agent buttons declared yet — drop a `prompts/agents/<id>.md` with a `button:` block.)_"
    new_text = text[: region.start] + f"{REGION_BEGIN}\n{refs}\n{REGION_END}" + text[region.end :]
    if new_text != text:
        dashboard_path.write_text(new_text, encoding="utf-8")
        return True
    return False
