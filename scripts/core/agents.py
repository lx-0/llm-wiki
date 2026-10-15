"""The agent registry: which coding agents get the engine's capture hooks, where their
configs live, what the hook commands are, and how to recognise them.

Pure data and small functions (no I/O beyond reading a config's text); the `wiki hooks`
commands sit on top. Ported from `lib/agents.sh`, and held to it byte for byte: an
operator's installed hook commands must not change on reinstall (M034).

One grammar recognises a wiki-managed hook command, for the installed probe, the merge
and the uninstall alike. The bash carried three drifted copies of it (the uninstall's
matched nothing current) and the doctor a fourth.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

SCOPES = ("user", "project")

# A command that runs one of the engine's hook scripts from under a `.wiki` path. Covers
# today's `cd '<vault>/.wiki' && [UV_PROJECT_ENVIRONMENT='…' ]uv run python hooks/<x>.py`
# and the older `uv run --project .wiki python .wiki/hooks/<x>.py`. `_transcript` came in
# with the probe as "one of the engine's hook scripts"; no installer ever wrote it.
HOOK_CMD_RE = re.compile(r"""\.wiki['"/ ].*hooks/(session-(start|end)|pre-compact|_transcript)""")


@dataclass(frozen=True)
class Hook:
    event: str
    script: str  # relative to the engine checkout, which the command cd's into
    timeout: int  # in the agent's unit: Gemini counts milliseconds, the others seconds


@dataclass(frozen=True)
class Agent:
    name: str
    detect: str  # the directory whose presence in a scope means the agent is there
    config: str  # the config file, relative to the scope directory
    hooks: tuple[Hook, ...]
    # Cursor's schema: `version: 1` on top, and each event's array holds the commands
    # themselves instead of `{matcher, hooks: [...]}` groups.
    flat: bool = False


_START, _END, _COMPACT = "hooks/session-start.py", "hooks/session-end.py", "hooks/pre-compact.py"

AGENTS = (
    Agent(
        "claude",
        ".claude",
        ".claude/settings.json",
        (
            Hook("SessionStart", _START, 15),
            Hook("SessionEnd", _END, 10),
            Hook("PreCompact", _COMPACT, 10),
        ),
    ),
    # Codex has no session-end event; its Stop fires per turn, and the captures are
    # coalesced by dedup and the daily block replacement.
    Agent(
        "codex",
        ".codex",
        ".codex/hooks.json",
        (Hook("SessionStart", _START, 15), Hook("Stop", _END, 10)),
    ),
    Agent(
        "gemini",
        ".gemini",
        ".gemini/settings.json",
        (
            Hook("SessionStart", _START, 15000),
            Hook("SessionEnd", _END, 10000),
            Hook("PreCompress", _COMPACT, 10000),
        ),
    ),
    Agent(
        "cursor",
        ".cursor",
        ".cursor/hooks.json",
        (
            Hook("sessionStart", _START, 15),
            Hook("sessionEnd", _END, 10),
            Hook("preCompact", _COMPACT, 10),
        ),
        flat=True,
    ),
)
_BY_NAME = {a.name: a for a in AGENTS}


def agent(name: str) -> Agent:
    """The registry entry for ``name``; KeyError for an agent the engine doesn't know."""
    return _BY_NAME[name]


def scope_dir(scope: str, *, home: Path, root: Path) -> Path:
    """`user` is the operator's home, `project` the vault root."""
    if scope == "user":
        return home
    if scope == "project":
        return root
    raise KeyError(scope)


def config_path(name: str, scope: str, *, home: Path, root: Path) -> Path:
    return scope_dir(scope, home=home, root=root) / agent(name).config


def present(name: str, scope: str, *, home: Path, root: Path) -> bool:
    return (scope_dir(scope, home=home, root=root) / agent(name).detect).is_dir()


def is_wiki_hook(command: str) -> bool:
    return HOOK_CMD_RE.search(command) is not None


def hooks_installed(cfg: Path) -> bool:
    """True when the config's text names a wiki hook command anywhere: the probe reads
    the file as text, as the bash `grep` did, not as JSON."""
    try:
        text = cfg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return HOOK_CMD_RE.search(text) is not None


def shell_quote(value: str) -> str:
    """``value`` in single quotes for a POSIX shell, each ' written as '\\'' (lib/common.sh's
    shell_quote). Always quoted, unlike shlex.quote, so a path without an apostrophe comes
    out exactly as earlier installs wrote it."""
    return "'" + value.replace("'", "'\\''") + "'"


def hook_cmd(script: str, *, wiki_dir: Path, venv: str | None) -> str:
    """The command an agent runs for one hook. It cd's into the engine so uv finds its
    project, and it carries the engine environment literally when there is one outside
    the vault (``venv``: the dispatcher's UV_PROJECT_ENVIRONMENT): the agent spawns the
    hook with its own environment, not `wiki`'s, and everything the hook starts (flush,
    compile, the piggybacks) inherits it."""
    prefix = f"UV_PROJECT_ENVIRONMENT={shell_quote(venv)} " if venv else ""
    return f"cd {shell_quote(str(wiki_dir))} && {prefix}uv run python {script}"


def payload(name: str, *, wiki_dir: Path, venv: str | None) -> dict[str, object]:
    """The wiki-managed part of one agent's config: its hooks block, one entry per event."""
    spec = agent(name)
    events: dict[str, object] = {}
    for hook in spec.hooks:
        entry = {
            "type": "command",
            "command": hook_cmd(hook.script, wiki_dir=wiki_dir, venv=venv),
            "timeout": hook.timeout,
        }
        events[hook.event] = [entry] if spec.flat else [{"matcher": "", "hooks": [entry]}]
    return {"version": 1, "hooks": events} if spec.flat else {"hooks": events}


def render(config: object) -> str:
    """A config as `jq .` writes it: two-space indent, UTF-8 as is, a trailing newline."""
    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"
