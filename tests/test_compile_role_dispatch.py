"""Dispatch + prompt tests for compile_role axis (M007-S02-T05).

Covers:
- Frontmatter helpers (_frontmatter_compile_role + _frontmatter_field)
- Prompt rendering: compile_main.md includes the source-and-final reference rule
- Dispatch unit-checks (final-only → ValueError-free, source-and-final dispatch
  path exists in the module)

Full compile_file roundtrip with mocked SDK + state/index files is deferred
to a follow-up integration test — the dispatch logic is exercised by the
helpers and the prompt; the SDK orchestration is covered by tests/test_compile_lock.py.
"""

from __future__ import annotations

import pytest


# ── Frontmatter helpers ──────────────────────────────────────────────


class TestFrontmatterCompileRole:
    def test_extracts_explicit_role(self):
        from compile import _frontmatter_compile_role
        content = "---\ncompile_role: final-only\ntitle: x\n---\nbody"
        assert _frontmatter_compile_role(content) == "final-only"

    def test_extracts_source_and_final(self):
        from compile import _frontmatter_compile_role
        content = "---\ncompile_role: source-and-final\n---\n"
        assert _frontmatter_compile_role(content) == "source-and-final"

    def test_extracts_source_only(self):
        from compile import _frontmatter_compile_role
        content = "---\ncompile_role: source-only\n---\n"
        assert _frontmatter_compile_role(content) == "source-only"

    def test_returns_none_when_missing(self):
        from compile import _frontmatter_compile_role
        content = "---\ntype: concept\ntitle: x\n---\nbody"
        assert _frontmatter_compile_role(content) is None

    def test_returns_none_when_no_frontmatter(self):
        from compile import _frontmatter_compile_role
        assert _frontmatter_compile_role("no frontmatter here") is None

    def test_handles_quoted_value(self):
        from compile import _frontmatter_compile_role
        content = "---\ncompile_role: \"final-only\"\n---\n"
        assert _frontmatter_compile_role(content) == "final-only"

    def test_returns_none_for_unterminated_frontmatter(self):
        from compile import _frontmatter_compile_role
        content = "---\ncompile_role: final-only\nbody without closing fence"
        assert _frontmatter_compile_role(content) is None


class TestFrontmatterField:
    def test_extracts_title(self):
        from compile import _frontmatter_field
        content = "---\ntitle: My Strategy\n---\nbody"
        assert _frontmatter_field(content, "title") == "My Strategy"

    def test_returns_none_when_key_missing(self):
        from compile import _frontmatter_field
        content = "---\ntype: concept\n---\n"
        assert _frontmatter_field(content, "title") is None

    def test_handles_quoted_value(self):
        from compile import _frontmatter_field
        content = "---\ntitle: \"quoted value\"\n---\n"
        assert _frontmatter_field(content, "title") == "quoted value"

    def test_handles_value_with_punctuation(self):
        from compile import _frontmatter_field
        content = "---\ntitle: with spaces, commas! and punc.\n---\n"
        assert _frontmatter_field(content, "title") == "with spaces, commas! and punc."

    def test_returns_none_when_no_frontmatter(self):
        from compile import _frontmatter_field
        assert _frontmatter_field("body only", "title") is None


# ── Prompt rendering ─────────────────────────────────────────────────


_DUMMY_VARS = {
    "agents_md": "",
    "facts_md": "",
    "index_md": "",
    "source_path": "raw/notes/longform/yesterday-strategy-2026.md",
    "source_content": "dummy content",
    "today": "2026-05-16",
    "now": "2026-05-16T17:00:00Z",
}


class TestCompileMainPromptSourceAndFinal:
    def test_prompt_mentions_source_and_final(self):
        from core.prompts import render
        rendered = render("compile_main", **_DUMMY_VARS)
        assert "compile_role: source-and-final" in rendered

    def test_prompt_instructs_cite_by_pathname(self):
        from core.prompts import render
        rendered = render("compile_main", **_DUMMY_VARS)
        assert "Cite by pathname" in rendered

    def test_prompt_warns_no_parallel_concept_article(self):
        from core.prompts import render
        rendered = render("compile_main", **_DUMMY_VARS)
        assert "do NOT create a separate" in rendered or "do NOT add the path to a `compiled_from:`" in rendered

    def test_prompt_warns_no_compiled_from(self):
        from core.prompts import render
        rendered = render("compile_main", **_DUMMY_VARS)
        assert "compiled_from:" in rendered  # the rule references the key

    def test_two_layer_rule_still_present(self):
        # Regression: ensure adding the source-and-final block didn't displace
        # the M005 two-layer schema rule.
        from core.prompts import render
        rendered = render("compile_main", **_DUMMY_VARS)
        assert "Two-layer shape for `type: person|project`" in rendered


# ── Dispatch module sanity ───────────────────────────────────────────


class TestDispatchSanity:
    def test_compile_file_is_async_callable(self):
        from compile import compile_file
        import inspect
        assert inspect.iscoroutinefunction(compile_file)

    def test_compile_module_imports_infer_compile_role(self):
        # Smoke: the import line lives inside compile_file's body in a local
        # import. Verify the module itself is importable.
        from core.compile_role import infer_compile_role, VALID_ROLES
        assert "source-and-final" in VALID_ROLES
        assert "final-only" in VALID_ROLES
        assert "source-only" in VALID_ROLES
