"""Action catalogue — the engine's operator-facing vocabulary for everything a consumer can run.

One table: action id → plain-English title (singular / plural on ``{n}``), the verb a button
should carry, the intent group of the home screen, and the argv the `wiki` dispatcher executes.
`menu_context` keys its probes on these ids and emits the rendered fields in `wiki menu --json`;
`doctor` derives verbs for checks that carry ``dispatch_args``; `tools()` lists the maintenance
actions that are available at any time. Consumers (desktop app, agents) render these fields
verbatim — the vocabulary lives here, not in per-consumer rewrite maps.

The TUI keeps its own operator-term labels (DECISIONS 2026-06-24: engine and CLI speak operator,
GUI speaks plain English); this module is the GUI-facing half of that split.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.contracts import ActionJSON

#: Bumped whenever a consumer-visible key is added, renamed or removed in `menu --json` /
#: `doctor --json`. Consumers refuse payloads whose schema they do not know.
SCHEMA = 2

#: Fallback verbs by leading subcommand, for argv that are not a catalogue row (doctor
#: ``dispatch_args``). An unknown command renders as the neutral "Run".
VERB_BY_COMMAND: dict[str, str] = {
    "setup": "Set up",
    "hooks": "Set up",
    "install-shortcut": "Install",
    "update": "Update",
    "compile": "Add",
    "process-inbox": "Sort",
    "reindex": "Fix",
    "dream": "Refresh",
    "dream-entity": "Refresh",
    "links": "Fix",
    "lint": "Check",
    "dedup": "Review",
    "review-wiki": "Review",
    "curiosity": "Explore",
    "suggestions": "Run",
    "gmail-auth": "Sign in",
    "gmeet-auth": "Sign in",
    "calendar-auth": "Sign in",
    "auth": "Sign in",
}


@dataclass(frozen=True)
class ActionSpec:
    id: str
    verb: str
    group: str  # do | auto | review | tools
    argv: tuple[str, ...]
    title_one: str  # used for n == 1 or when no count applies; may carry ``{n}``
    title_many: str  # used for every other n; may carry ``{n}``
    tool: bool = False  # also listed under `tools` (available without a pending count)

    def title(self, n: int | None = None) -> str:
        template = self.title_one if n is None or n == 1 else self.title_many
        return template.format(n="" if n is None else n)

    def to_json(self, n: int | None = None) -> ActionJSON:
        return {
            "id": self.id,
            "title": self.title(n),
            "verb": self.verb,
            "group": self.group,
            "argv": list(self.argv),
        }


def _spec(
    id: str,
    verb: str,
    group: str,
    argv: Sequence[str],
    title_one: str,
    title_many: str | None = None,
    *,
    tool: bool = False,
) -> ActionSpec:
    return ActionSpec(id, verb, group, tuple(argv), title_one, title_many or title_one, tool)


_SPECS: tuple[ActionSpec, ...] = (
    # "library" is the operator-facing noun everywhere (welcome, settings, panel) — never
    # "wiki" or "vault"; "files" not "captures", which collides with screen/audio capture.
    _spec(
        "process-inbox",
        "Sort",
        "do",
        ["process-inbox"],
        "{n} new file to sort into your library",
        "{n} new files to sort into your library",
    ),
    _spec(
        "compile",
        "Add",
        "do",
        ["compile"],
        "{n} new item to add to your library",
        "{n} new items to add to your library",
    ),
    _spec(
        "curiosity-folder",
        "Review",
        "review",
        ["curiosity", "--type", "folder-deep-scan"],
        "{n} folder-scan request to review",
        "{n} folder-scan requests to review",
    ),
    _spec(
        "curiosity-email",
        "Explore",
        "auto",
        ["curiosity", "--type", "email-deep-scan"],
        "{n} email scan pending",
        "{n} email scans pending",
    ),
    _spec(
        "suggestions",
        "Run",
        "do",
        ["suggestions"],
        "{n} approved suggestion to run",
        "{n} approved suggestions to run",
    ),
    _spec(
        "dream-sweep",
        "Refresh",
        "auto",
        ["dream", "--all-entities"],
        "{n} page needs refreshing",
        "{n} pages need refreshing",
        tool=True,
    ),
    _spec(
        "lint",
        "Check",
        "auto",
        ["lint", "--structural-only"],
        "Notes changed since the last health check",
        tool=True,
    ),
    # Tools stay non-destructive and $0: `links` reports, `dedup --suggest-only` never merges.
    _spec("links", "Check", "tools", ["links"], "Check links", tool=True),
    _spec(
        "dedup", "Review", "tools", ["dedup", "--suggest-only"], "Find duplicate pages", tool=True
    ),
    _spec("review-wiki", "Review", "tools", ["review-wiki"], "Review page quality", tool=True),
)

#: Plain-English titles for the tool listing of probe-backed rows (their ``title_one`` is the
#: counted phrasing, which makes no sense without a pending count).
_TOOL_TITLES: dict[str, str] = {
    "dream-sweep": "Refresh people & project pages",
    "lint": "Check for problems",
}

CATALOGUE: dict[str, ActionSpec] = {spec.id: spec for spec in _SPECS}
_BY_ARGV: dict[tuple[str, ...], ActionSpec] = {spec.argv: spec for spec in _SPECS}


def get(action_id: str) -> ActionSpec:
    """The catalogue row for ``action_id``; raises ``KeyError`` for unknown ids."""
    return CATALOGUE[action_id]


def verb_for(argv: Sequence[str]) -> str:
    """Verb for an arbitrary ``wiki`` argv: exact catalogue match, else by subcommand, else Run."""
    spec = _BY_ARGV.get(tuple(argv))
    if spec is not None:
        return spec.verb
    if not argv:
        return "Run"
    return VERB_BY_COMMAND.get(argv[0], "Run")


def tools() -> list[ActionJSON]:
    """The always-available maintenance actions, rendered without a count under group ``tools``."""
    out: list[ActionJSON] = []
    for spec in _SPECS:
        if not spec.tool:
            continue
        payload = spec.to_json(None)
        payload["group"] = "tools"
        payload["title"] = _TOOL_TITLES.get(spec.id, spec.title_one)
        out.append(payload)
    return out
