"""Output-language knob (issue #4).

`personal.output_language` pins the prose language of compiled `knowledge/**`
articles. "auto" must render the compile substrate prompts byte-identically
(no regression for existing operators); any other value injects a
`## Output language` override section that forces the target language while
keeping code / identifiers / proper names / canonical structural headers
verbatim.

The placeholder is built by `core.prompts.build_output_language_instruction`
and injected once at the central `compile_source` render site, so every
substrate prompt that references `${output_language_instruction}` picks it up.
"""

from __future__ import annotations

import pytest

from core.prompts import build_output_language_instruction, render


# Every substrate prompt the central compile render passes the placeholder to.
# All must carry `${output_language_instruction}` (else render() raises) and
# must render byte-identically in auto mode (placeholder → "").
_SUBSTRATE_PROMPTS = [
    "compile_main",
    "compile_default",
    "compile_daily",
    "compile_health",
    "compile_calendar",
    "compile_pictures",
    "compile_screenshots",
    "compile_memories",
]


class TestBuildInstruction:
    @pytest.mark.parametrize("value", ["auto", "AUTO", "  auto ", "", "   ", None])
    def test_auto_or_empty_returns_empty(self, value):
        assert build_output_language_instruction(value) == ""

    def test_forced_language_renders_section(self):
        out = build_output_language_instruction("German")
        assert out != ""
        assert "## Output language" in out
        assert "German" in out

    def test_forced_language_carve_out_present(self):
        """Structural headers, code, and proper names must stay verbatim, and the
        directive must explicitly override the source-language rule."""
        out = build_output_language_instruction("de")
        assert "de" in out
        # canonical structural headers named as keep-verbatim
        assert "## Timeline" in out
        assert "## State" in out
        # carve-out categories
        assert "verbatim" in out.lower()
        assert "proper names" in out.lower()
        # supersedes the existing "write in source language" instruction
        assert "override" in out.lower()


class TestPlaceholderWiring:
    """Each substrate prompt references the placeholder and tolerates both modes."""

    _DUMMY = {
        "agents_md": "",
        "facts_md": "",
        "index_md": "",
        "owner_block": "",
        "source_path": "raw/notes/longform/x.md",
        "source_content": "dummy",
        "today": "2026-06-13",
        "now": "2026-06-13T12:00:00Z",
        "project_slug": "",
        "project_page": "",
    }

    @pytest.mark.parametrize("name", _SUBSTRATE_PROMPTS)
    def test_auto_mode_has_no_override_section(self, name):
        rendered = render(name, output_language_instruction="", **self._DUMMY)
        assert "## Output language" not in rendered

    @pytest.mark.parametrize("name", _SUBSTRATE_PROMPTS)
    def test_forced_mode_appends_override_section(self, name):
        instruction = build_output_language_instruction("de")
        rendered = render(name, output_language_instruction=instruction, **self._DUMMY)
        assert "## Output language" in rendered
        # appended at the tail, not buried mid-prompt
        assert rendered.rstrip().endswith(instruction.rstrip())
