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

import yaml

# scripts/core/prompts.py → parents: core → scripts → <wiki>/prompts/
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

_PLACEHOLDER_RE = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
# Optional Prompty-style YAML frontmatter: a prompt MAY open with `---\n…\n---`
# declaring per-prompt settings (notably `model:`). Stripped from the rendered
# body so it never reaches the LLM; read via prompt_frontmatter / prompt_model.
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)


class PromptError(RuntimeError):
    """Raised when a prompt file is missing or a variable is unresolved."""


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter dict, body). ({}, text) when no valid block.

    Only a file that OPENS with `---\\n` counts; a `---` mid-prompt (a markdown
    rule or a YAML example in the body) is left untouched.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}, text
    return (meta, m.group(2)) if isinstance(meta, dict) else ({}, text)


def prompt_frontmatter(name: str) -> dict:
    """Parse a prompt's optional YAML frontmatter. {} if absent/malformed."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise PromptError(f"Prompt file not found: {path}")
    meta, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
    return meta


def prompt_model(name: str, *fallbacks: str) -> str:
    """Resolve the model for a prompt: frontmatter `model:` wins, else the first
    truthy fallback (caller default → config knob → compile_model)."""
    m = prompt_frontmatter(name).get("model")
    if isinstance(m, str) and m.strip():
        return m.strip()
    for fb in fallbacks:
        if fb:
            return fb
    return ""


def render(name: str, **vars: object) -> str:
    """Load `prompts/<name>.md`, strip any frontmatter, substitute `${var}`
    placeholders, return the body.

    Raises PromptError if the file is missing or a placeholder has no value.
    """
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise PromptError(f"Prompt file not found: {path}")
    _meta, text = _split_frontmatter(path.read_text(encoding="utf-8"))

    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in vars:
            raise PromptError(f"Prompt {name!r} references ${{{key}}} but no value provided")
        value = vars[key]
        return str(value) if value is not None else ""

    return _PLACEHOLDER_RE.sub(_sub, text)


def build_output_language_instruction(output_language: str) -> str:
    """Render the `${output_language_instruction}` fragment for compile prompts.

    Pure (takes the configured value, not CONFIG) so it's trivially testable and
    free of import cycles. `"auto"` (or empty / unset) returns the empty string,
    so the substrate prompts render byte-identically to their pre-issue-#4 form —
    today's "write in the source material's language" behavior. Any other value
    (`"de"`, `"German"`, `"fr"`, …) renders the `compile_output_language.md`
    section, which forces all compiled prose into that language while keeping
    code, identifiers, proper names, and the canonical structural headers
    verbatim. Injected once for every substrate prompt at the central
    `compile_source` render site. See issue #4.
    """
    value = (output_language or "").strip()
    if not value or value.lower() == "auto":
        return ""
    return render("compile_output_language", output_language=value)
