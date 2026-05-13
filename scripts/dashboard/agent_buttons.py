"""Discovery + auto-wiring helpers for agent-task Dashboard buttons.

Walks `prompts/agent_*.md` for specs that declare a `button:` block, and
emits the data needed by `lib/seed.sh` to:

  1. merge entries into `.obsidian/plugins/obsidian-shellcommands/data.json`
  2. emit hidden `meta-bind-button` blocks + inline `BUTTON[id]` references
     into a marked region of `dashboard.md`

Designed to be called from bash (JSON output to stdout) so seeding stays
idempotent and additive (operator's existing buttons untouched).

Usage from bash:
    uv run python scripts/dashboard/agent_buttons.py shell-commands  # JSON for shell-commands merge
    uv run python scripts/dashboard/agent_buttons.py meta-bind-defs  # markdown blocks for dashboard.md
    uv run python scripts/dashboard/agent_buttons.py inline-refs     # inline `BUTTON[id]` refs (one line)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_spec import AgentSpec, parse_spec
from config import WIKI_DIR

PROMPTS_DIR = WIKI_DIR / "prompts"


def discover() -> list[AgentSpec]:
    specs: list[AgentSpec] = []
    if not PROMPTS_DIR.exists():
        return specs
    for path in sorted(PROMPTS_DIR.glob("agent_*.md")):
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


def shell_commands_entries() -> dict[str, dict]:
    """Return a dict shaped like `data.json["shell_commands"]` — keys are shell_command_id."""
    out: dict[str, dict] = {}
    for spec in discover():
        assert spec.button is not None
        cmd_id = spec.button.shell_command_id
        out[cmd_id] = {
            "platform_specific_commands": {
                "default": f"./.wiki/wiki agent {spec.id}",
            },
            "shells": {},
            "alias": f"Wiki: agent {spec.id}",
            "icon": "bot",
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
    return out


def meta_bind_blocks() -> str:
    """Return a markdown chunk: hidden meta-bind-button blocks for every discovered spec."""
    parts: list[str] = []
    for spec in discover():
        assert spec.button is not None
        b = spec.button
        parts.append(
            "```meta-bind-button\n"
            f"label: {b.label}\n"
            "hidden: true\n"
            'class: ""\n'
            f"tooltip: {json.dumps(b.tooltip or f'Run agent {spec.id}', ensure_ascii=False)}\n"
            f"id: btn-{spec.id}\n"
            f"style: {b.style}\n"
            "actions:\n"
            "  - type: command\n"
            f"    command: {json.dumps(f'Shell commands: Wiki: agent {spec.id}', ensure_ascii=False)}\n"
            "```\n"
        )
    return "\n".join(parts)


def inline_refs() -> str:
    """Return a single-line string of inline `BUTTON[btn-<id>]` refs for the visible Run row."""
    refs = [f"`BUTTON[btn-{spec.id}]`" for spec in discover()]
    return " ".join(refs)


def update_dashboard(dashboard_path: Path) -> bool:
    """Replace the two marked regions in dashboard.md with current discovery.

    Regions:
      <!-- agent-buttons:begin --> ... <!-- agent-buttons:end -->        (inline refs)
      <!-- agent-button-defs:begin --> ... <!-- agent-button-defs:end --> (hidden meta-bind blocks)

    Idempotent — re-running with no spec changes produces no diff. Returns True
    if the file changed.
    """
    if not dashboard_path.exists():
        print(f"# warn: {dashboard_path} does not exist; skipping dashboard rewrite", file=sys.stderr)
        return False

    text = dashboard_path.read_text(encoding="utf-8")
    original = text

    refs = inline_refs()
    if not refs:
        refs = "_(no agent buttons declared yet — drop a `prompts/agent_<id>.md` with a `button:` block.)_"
    defs = meta_bind_blocks()

    text = _replace_region(
        text,
        "<!-- agent-buttons:begin -->",
        "<!-- agent-buttons:end -->",
        refs,
    )
    text = _replace_region(
        text,
        "<!-- agent-button-defs:begin -->",
        "<!-- agent-button-defs:end -->",
        defs.rstrip(),
    )
    if text != original:
        dashboard_path.write_text(text, encoding="utf-8")
        return True
    return False


def _replace_region(text: str, begin: str, end: str, body: str) -> str:
    bi = text.find(begin)
    ei = text.find(end)
    if bi == -1 or ei == -1 or ei < bi:
        print(f"# warn: markers {begin!r}..{end!r} not found in dashboard; skipping", file=sys.stderr)
        return text
    body_block = body.strip("\n")
    return text[: bi + len(begin)] + "\n" + body_block + "\n" + text[ei:]


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in {
        "shell-commands", "meta-bind-defs", "inline-refs", "update-dashboard",
    }:
        print(
            "usage: scripts/dashboard/agent_buttons.py {shell-commands | meta-bind-defs | inline-refs | update-dashboard <path>}",
            file=sys.stderr,
        )
        return 2
    mode = sys.argv[1]
    if mode == "shell-commands":
        print(json.dumps(shell_commands_entries(), indent=2, ensure_ascii=False))
    elif mode == "meta-bind-defs":
        sys.stdout.write(meta_bind_blocks())
    elif mode == "inline-refs":
        sys.stdout.write(inline_refs())
    elif mode == "update-dashboard":
        if len(sys.argv) != 3:
            print("usage: scripts/dashboard/agent_buttons.py update-dashboard <dashboard.md>", file=sys.stderr)
            return 2
        changed = update_dashboard(Path(sys.argv[2]))
        print("changed" if changed else "unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
