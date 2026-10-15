"""Discovery + auto-wiring helpers for agent-task Dashboard buttons.

Walks `prompts/agents/*.md` for specs that declare a `button:` block, and
emits the data `lib/seed.sh` wires into the vault:

  1. a Shell commands entry per button, merged by id into the `shell_commands`
     of `.obsidian/plugins/obsidian-shellcommands/data.json`
  2. a Meta-Bind button template per button, merged by id into the
     `buttonTemplates` of `.obsidian/plugins/obsidian-meta-bind-plugin/data.json`
     — Meta-Bind (1.4 on) resolves `BUTTON[id]` against that registry only
  3. the inline `BUTTON[id]` references in a marked region of `dashboard.md`

The engine templates carry the engine's own entries and none of these: the
generator is the one source of the agent entries (`tests/test_agent_buttons.py`
holds the templates to that).

Usage from bash (the lines lib/seed.sh spells):
    PYTHONPATH="$WIKI_DIR/scripts" uv run --quiet --project "$WIKI_DIR" python -m dashboard.agent_buttons shell-commands       # JSON list for the shell-commands merge
    PYTHONPATH="$WIKI_DIR/scripts" uv run --quiet --project "$WIKI_DIR" python -m dashboard.agent_buttons meta-bind-templates  # JSON list for the meta-bind merge
    PYTHONPATH="$WIKI_DIR/scripts" uv run --quiet --project "$WIKI_DIR" python -m dashboard.agent_buttons update-dashboard <dashboard.md>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from core import markers
from core.agent_spec import AgentSpec, parse_spec
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
            print(
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


def main() -> int:
    modes = {"shell-commands", "meta-bind-templates", "update-dashboard"}
    if len(sys.argv) < 2 or sys.argv[1] not in modes:
        print(
            "usage: scripts/dashboard/agent_buttons.py {shell-commands | meta-bind-templates | update-dashboard <path>}",
            file=sys.stderr,
        )
        return 2
    mode = sys.argv[1]
    if mode == "shell-commands":
        print(json.dumps(shell_commands_entries(), indent=2, ensure_ascii=False))
    elif mode == "meta-bind-templates":
        print(json.dumps(meta_bind_templates(), indent=2, ensure_ascii=False))
    elif mode == "update-dashboard":
        if len(sys.argv) != 3:
            print(
                "usage: scripts/dashboard/agent_buttons.py update-dashboard <dashboard.md>",
                file=sys.stderr,
            )
            return 2
        dashboard = Path(sys.argv[2])
        if not has_region(dashboard.read_text(encoding="utf-8")):
            print("no-region")
        else:
            print("changed" if update_dashboard(dashboard) else "unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
