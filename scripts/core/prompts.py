"""Prompt loader — reads markdown prompts from `<vault>/.wiki/prompts/` and substitutes `${var}` placeholders.

Usage:
    from core.prompts import render
    prompt = render("flush_extract", context=context_text)
    system = render("flush_extract_system")  # no vars

Conventions:
- One .md file per prompt, naming `<script>_<purpose>.md` (e.g. `flush_extract.md`).
- Placeholder syntax: `${var}` — chosen over Python's `{var}` so JSON/YAML
  examples in the prompt can use literal `{` and `}` without escaping.
- Missing variables raise KeyError so prompt drift is loud, not silent.
- Files are read fresh on each call (no caching) — cheap (~ms) and lets the
  user edit prompts live without restarting the process.

Add a new prompt: drop a new .md in `prompts/`, call `render("name", ...)`.
"""
from __future__ import annotations

import re
from pathlib import Path

# scripts/core/prompts.py → parents: core → scripts → <wiki>/prompts/
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

_PLACEHOLDER_RE = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class PromptError(RuntimeError):
    """Raised when a prompt file is missing or a variable is unresolved."""


def render(name: str, **vars: object) -> str:
    """Load `prompts/<name>.md`, substitute `${var}` placeholders, return the result.

    Raises PromptError if the file is missing or a placeholder has no value.
    """
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise PromptError(f"Prompt file not found: {path}")
    text = path.read_text(encoding="utf-8")

    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in vars:
            raise PromptError(f"Prompt {name!r} references ${{{key}}} but no value provided")
        value = vars[key]
        return str(value) if value is not None else ""

    return _PLACEHOLDER_RE.sub(_sub, text)
