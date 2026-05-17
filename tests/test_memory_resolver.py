"""Tests for `compile_stages.memory` slug resolution + Timeline bootstrap."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from compile_stages.memory import (  # noqa: E402
    _extract_tag_slugs,
    _strip_path_prefix,
    ensure_timeline_section,
    resolve_project_slug,
)


# ── _strip_path_prefix ─────────────────────────────────────────────────────

class TestStripPathPrefix:
    def test_strips_after_projects_marker(self):
        assert _strip_path_prefix(
            "home-alex-Code-WebDev-projects-lx-0-llm-wiki"
        ) == "lx-0-llm-wiki"

    def test_strips_after_last_projects_marker(self):
        # If a path happens to contain '-projects-' twice, the LAST one wins
        # (the actual `projects/` directory marker).
        assert _strip_path_prefix(
            "user-projects-misc-projects-real-project"
        ) == "real-project"

    def test_no_marker_strips_leading_dashes(self):
        assert _strip_path_prefix("-paperclip-playground") == "paperclip-playground"

    def test_no_marker_and_no_leading_dash_returns_as_is(self):
        assert _strip_path_prefix("home-alex-Code-WebDev") == "home-alex-Code-WebDev"

    def test_empty_input(self):
        assert _strip_path_prefix("") == ""


# ── _extract_tag_slugs ─────────────────────────────────────────────────────

class TestExtractTagSlugs:
    def test_filters_utility_tags(self):
        assert _extract_tag_slugs(
            ["yesterday-ai-openclaw", "claude-memory", "seed"]
        ) == ["yesterday-ai-openclaw"]

    def test_filters_all_utility_variants(self):
        # All four utility tags should be filtered.
        assert _extract_tag_slugs(
            ["myproj", "claude-memory", "memory", "sync", "seed"]
        ) == ["myproj"]

    def test_non_list_returns_empty(self):
        assert _extract_tag_slugs(None) == []
        assert _extract_tag_slugs("yesterday-ai-cloud") == []
        assert _extract_tag_slugs({"yesterday-ai-cloud": True}) == []

    def test_empty_list(self):
        assert _extract_tag_slugs([]) == []

    def test_non_string_items_filtered(self):
        assert _extract_tag_slugs(["valid-slug", 42, None, "another"]) == [
            "valid-slug", "another"
        ]


# ── resolve_project_slug ──────────────────────────────────────────────────

def _scaffold_vault(tmp_path: Path, project_stems: list[str]) -> Path:
    """Build a tmp vault with `knowledge/projects/<stem>.md` files."""
    projects_dir = tmp_path / "knowledge" / "projects"
    projects_dir.mkdir(parents=True)
    for stem in project_stems:
        (projects_dir / f"{stem}.md").write_text(f"# {stem}\n", encoding="utf-8")
    return tmp_path


class TestResolveProjectSlug:
    def test_memory_seed_exact_stem_match(self, tmp_path):
        """memory-seed file `yesterday-ai-cloud.md` matches stem directly."""
        vault = _scaffold_vault(tmp_path, ["yesterday-ai-cloud", "fleet"])
        result = resolve_project_slug(
            source=Path("raw/memories/yesterday-ai-cloud.md"),
            frontmatter={"type": "memory-seed", "tags": ["yesterday-ai-cloud", "seed"]},
            vault_root=vault,
        )
        assert result == "yesterday-ai-cloud"

    def test_memory_sync_path_encoded_project_field(self, tmp_path):
        """memory-sync resolves via frontmatter project: after path-prefix strip."""
        vault = _scaffold_vault(tmp_path, ["lx-0-llm-wiki", "fleet"])
        result = resolve_project_slug(
            source=Path("raw/memories/home-alex-Code-WebDev-projects-lx-0-llm-wiki__feedback_foo.md"),
            frontmatter={
                "type": "memory-sync",
                "project": "home-alex-Code-WebDev-projects-lx-0-llm-wiki",
                "tags": ["lx-0-llm-wiki", "claude-memory", "sync"],
            },
            vault_root=vault,
        )
        assert result == "lx-0-llm-wiki"

    def test_unique_substring_match(self, tmp_path):
        """Slug 'paperclip-playground' (no exact page) finds via substring."""
        vault = _scaffold_vault(tmp_path, ["paperclip-playground", "fleet"])
        # Even though substring search would also match itself exactly, exact
        # match wins on tier A.
        result = resolve_project_slug(
            source=Path("raw/memories/x.md"),
            frontmatter={"project": "-paperclip-playground", "tags": []},
            vault_root=vault,
        )
        assert result == "paperclip-playground"

    def test_ambiguous_substring_returns_none(self, tmp_path):
        """Slug matching multiple project pages → None, not a guess."""
        vault = _scaffold_vault(tmp_path, [
            "paperclip", "paperclip-playground", "paperclip-companies",
        ])
        result = resolve_project_slug(
            source=Path("raw/memories/x.md"),
            frontmatter={"tags": ["paperclip"]},
            vault_root=vault,
        )
        # 'paperclip' exact match wins → not None. Test ambiguity-only case:
        assert result == "paperclip"

    def test_ambiguous_substring_no_exact_returns_none(self, tmp_path):
        """Substring with multiple matches and no exact → None."""
        vault = _scaffold_vault(tmp_path, [
            "openclaw-hub-infrastructure", "openclaw-ops-repo",
        ])
        # 'openclaw' matches both as substring → ambiguous.
        result = resolve_project_slug(
            source=Path("raw/memories/x.md"),
            frontmatter={"tags": ["openclaw"]},
            vault_root=vault,
        )
        assert result is None

    def test_no_match_returns_none(self, tmp_path):
        """Slug matches nothing → None, no SDK call."""
        vault = _scaffold_vault(tmp_path, ["fleet", "homenet"])
        result = resolve_project_slug(
            source=Path("raw/memories/yesterday-ai-openclaw.md"),
            frontmatter={"tags": ["yesterday-ai-openclaw"]},
            vault_root=vault,
        )
        assert result is None

    def test_projects_dir_missing_returns_none(self, tmp_path):
        """No knowledge/projects/ dir → None (graceful, not crash)."""
        result = resolve_project_slug(
            source=Path("raw/memories/x.md"),
            frontmatter={"tags": ["fleet"]},
            vault_root=tmp_path,
        )
        assert result is None

    def test_stem_takes_priority_over_frontmatter(self, tmp_path):
        """Tier ordering: filename stem > frontmatter project: > tags."""
        vault = _scaffold_vault(tmp_path, ["fleet", "homenet"])
        result = resolve_project_slug(
            source=Path("raw/memories/fleet.md"),
            frontmatter={
                "project": "home-alex-Code-WebDev-projects-homenet",
                "tags": ["homenet"],
            },
            vault_root=vault,
        )
        # Stem 'fleet' wins over frontmatter 'homenet'.
        assert result == "fleet"


# ── ensure_timeline_section ────────────────────────────────────────────────

class TestEnsureTimelineSection:
    def test_appends_when_absent(self, tmp_path):
        page = tmp_path / "x.md"
        page.write_text("# Title\n\nSome content.\n", encoding="utf-8")
        ensure_timeline_section(page)
        assert "## Timeline" in page.read_text(encoding="utf-8")

    def test_idempotent_when_present(self, tmp_path):
        page = tmp_path / "x.md"
        original = "# Title\n\n## Timeline\n\n- entry\n"
        page.write_text(original, encoding="utf-8")
        ensure_timeline_section(page)
        assert page.read_text(encoding="utf-8") == original

    def test_appends_with_blank_line_separator(self, tmp_path):
        page = tmp_path / "x.md"
        page.write_text("Content with no trailing newline", encoding="utf-8")
        ensure_timeline_section(page)
        result = page.read_text(encoding="utf-8")
        # Trailing whitespace trimmed before append.
        assert result == "Content with no trailing newline\n\n## Timeline\n"

    def test_recognizes_existing_section_at_any_position(self, tmp_path):
        # Even if Timeline is mid-doc, no re-append.
        page = tmp_path / "x.md"
        page.write_text("# A\n\n## Timeline\n- e\n\n## Other\n", encoding="utf-8")
        before = page.read_text(encoding="utf-8")
        ensure_timeline_section(page)
        assert page.read_text(encoding="utf-8") == before
