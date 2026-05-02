"""Agent-task spec parser.

A "task spec" lives in `prompts/agent_<id>.md`. The YAML frontmatter declares
how to invoke the Claude Agent SDK; the body is the prompt with optional
`${var}` placeholders.

See `.ytstack/M004-CONTEXT.md` and `prompts/agent_summarize-day.md` for the
full schema and a reference example.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from config import ROOT_DIR, WIKI_DIR


VALID_TOOLS = frozenset(
    {"Read", "Edit", "Write", "Glob", "Grep", "Bash", "WebFetch", "WebSearch"}
)
VALID_PERMISSION_MODES = frozenset(
    {"default", "acceptEdits", "plan", "bypassPermissions"}
)
VALID_BUTTON_STYLES = frozenset({"primary", "default", "destructive", "plain"})
VALID_CWD = frozenset({"vault", "wiki"})


class SpecError(ValueError):
    """Raised when a task spec is missing required fields or has invalid values."""


@dataclass
class ButtonSpec:
    label: str
    style: str = "default"
    tooltip: str = ""
    shell_command_id: str = ""

    def validate(self, task_id: str) -> None:
        if self.style not in VALID_BUTTON_STYLES:
            raise SpecError(
                f"agent {task_id!r}: button.style {self.style!r} not in {sorted(VALID_BUTTON_STYLES)}"
            )
        if not self.label:
            raise SpecError(f"agent {task_id!r}: button.label is required when button is declared")
        if not self.shell_command_id:
            self.shell_command_id = f"agent-{task_id}"


@dataclass
class AgentSpec:
    id: str
    title: str
    body: str
    description: str = ""
    model: str = ""  # falls back to CONFIG.models.compile_model at runtime
    allowed_tools: list[str] = field(default_factory=list)
    permission_mode: str = "acceptEdits"
    max_turns: int = 10
    cwd: str = "vault"
    button: ButtonSpec | None = None
    last_run: str | bool = False
    path: Path | None = None

    def validate(self) -> None:
        if not self.id:
            raise SpecError("spec is missing `id`")
        if not self.title:
            raise SpecError(f"agent {self.id!r}: missing `title`")
        if not self.allowed_tools:
            raise SpecError(f"agent {self.id!r}: `allowed_tools` is required (non-empty list)")
        unknown = [t for t in self.allowed_tools if t not in VALID_TOOLS]
        if unknown:
            raise SpecError(
                f"agent {self.id!r}: unknown allowed_tools {unknown} — valid: {sorted(VALID_TOOLS)}"
            )
        if self.permission_mode not in VALID_PERMISSION_MODES:
            raise SpecError(
                f"agent {self.id!r}: permission_mode {self.permission_mode!r} not in {sorted(VALID_PERMISSION_MODES)}"
            )
        if self.cwd not in VALID_CWD:
            raise SpecError(
                f"agent {self.id!r}: cwd {self.cwd!r} not in {sorted(VALID_CWD)}"
            )
        if self.max_turns < 1 or self.max_turns > 100:
            raise SpecError(f"agent {self.id!r}: max_turns must be 1..100, got {self.max_turns}")
        if self.button is not None:
            self.button.validate(self.id)

    def cwd_path(self) -> Path:
        return ROOT_DIR if self.cwd == "vault" else WIKI_DIR

    def render_body(self, **vars: str) -> str:
        """Substitute ${var} placeholders in the prompt body."""
        out = self.body
        for k, v in vars.items():
            out = out.replace(f"${{{k}}}", str(v))
        return out


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)", re.DOTALL)


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a markdown file into (frontmatter dict, body)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise SpecError("file has no YAML frontmatter (must start with `---`)")
    raw = m.group(1)
    body = m.group(2)
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise SpecError(f"YAML frontmatter is malformed: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecError(f"frontmatter must be a mapping, got {type(data).__name__}")
    return data, body


def parse_spec(path: Path) -> AgentSpec:
    """Read and validate an agent task spec from disk."""
    if not path.exists():
        raise SpecError(f"spec file not found: {path}")
    text = path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(text)

    button_data = fm.get("button")
    button: ButtonSpec | None = None
    if button_data is not None:
        if not isinstance(button_data, dict):
            raise SpecError(f"button must be a mapping, got {type(button_data).__name__}")
        button = ButtonSpec(
            label=str(button_data.get("label", "")),
            style=str(button_data.get("style", "default")),
            tooltip=str(button_data.get("tooltip", "")),
            shell_command_id=str(button_data.get("shell_command_id", "")),
        )

    spec = AgentSpec(
        id=str(fm.get("id", "")),
        title=str(fm.get("title", "")),
        description=str(fm.get("description", "")),
        body=body.strip("\n"),
        model=str(fm.get("model", "")),
        allowed_tools=list(fm.get("allowed_tools") or []),
        permission_mode=str(fm.get("permission_mode", "acceptEdits")),
        max_turns=int(fm.get("max_turns", 10)),
        cwd=str(fm.get("cwd", "vault")),
        button=button,
        last_run=fm.get("last_run", False),
        path=path,
    )
    spec.validate()
    return spec


def list_specs(prompts_dir: Path) -> list[AgentSpec]:
    """Scan `prompts/agent_*.md` and return all valid specs.

    Invalid specs raise — keep validation strict so operators see breakage early.
    """
    specs: list[AgentSpec] = []
    for path in sorted(prompts_dir.glob("agent_*.md")):
        specs.append(parse_spec(path))
    return specs
