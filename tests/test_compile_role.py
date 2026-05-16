"""Schema + inference tests for `scripts/core/compile_role.py` (M007-S01-T04).

Covers:
- VALID_ROLES set membership
- explicit override wins (returns whatever's in frontmatter)
- default-by-location inference for raw/daily/inbox/knowledge
- `default_by_location=False` short-circuits to source-only
- invalid enum values raise ValueError
- path outside known top-levels falls back to source-only
- vault_root makes path relative correctly
- LOCATION_DEFAULTS covers all 4 known segments
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.core.compile_role import (
    LOCATION_DEFAULTS,
    VALID_ROLES,
    infer_compile_role,
)


class TestValidRoles:
    def test_three_canonical_values(self):
        assert VALID_ROLES == frozenset(
            {"source-only", "source-and-final", "final-only"}
        )

    def test_membership(self):
        assert "source-only" in VALID_ROLES
        assert "source-and-final" in VALID_ROLES
        assert "final-only" in VALID_ROLES

    @pytest.mark.parametrize(
        "bad",
        ["bogus", "final", "source", "", "SOURCE-ONLY", "source_only", None],
    )
    def test_invalid_values_not_in_set(self, bad):
        assert bad not in VALID_ROLES


class TestExplicitOverride:
    @pytest.mark.parametrize(
        "role",
        ["source-only", "source-and-final", "final-only"],
    )
    def test_explicit_role_returned_regardless_of_location(self, role):
        # File in raw/ but frontmatter says final-only → final-only wins
        assert (
            infer_compile_role(Path("raw/notes/x.md"), {"compile_role": role})
            == role
        )
        # File in knowledge/ but frontmatter says source-and-final → wins
        assert (
            infer_compile_role(
                Path("knowledge/concepts/x.md"), {"compile_role": role}
            )
            == role
        )

    def test_invalid_explicit_raises_value_error(self):
        with pytest.raises(ValueError, match="invalid compile_role"):
            infer_compile_role(Path("raw/x.md"), {"compile_role": "bogus"})

    def test_invalid_explicit_includes_value_in_message(self):
        with pytest.raises(ValueError, match="'bogus'"):
            infer_compile_role(Path("raw/x.md"), {"compile_role": "bogus"})


class TestDefaultByLocation:
    @pytest.mark.parametrize(
        "location, expected",
        [
            ("raw", "source-only"),
            ("daily", "source-only"),
            ("inbox", "source-only"),
            ("knowledge", "source-only"),
        ],
    )
    def test_known_segments_resolve_to_defaults(self, location, expected):
        path = Path(f"{location}/sub/x.md")
        assert infer_compile_role(path, {}) == expected

    def test_path_outside_known_segments_fallback(self):
        # imported/lx/foo.md is NOT one of the 4 known top-levels
        assert infer_compile_role(Path("imported/lx/x.md"), {}) == "source-only"

    def test_default_by_location_false_short_circuits(self):
        # knowledge/ would normally resolve to source-only anyway, but with the
        # knob off we want explicit "no inference, just source-only"
        assert (
            infer_compile_role(
                Path("knowledge/concepts/x.md"), {}, default_by_location=False
            )
            == "source-only"
        )
        # Even from raw/, with knob off
        assert (
            infer_compile_role(
                Path("raw/notes/x.md"), {}, default_by_location=False
            )
            == "source-only"
        )

    def test_default_by_location_false_does_not_override_explicit(self):
        # Explicit always wins, even with knob off
        assert (
            infer_compile_role(
                Path("raw/x.md"),
                {"compile_role": "final-only"},
                default_by_location=False,
            )
            == "final-only"
        )


class TestVaultRoot:
    def test_absolute_path_with_vault_root(self, tmp_path):
        vault = tmp_path
        target = vault / "knowledge" / "concepts" / "x.md"
        assert (
            infer_compile_role(target, {}, vault_root=vault) == "source-only"
        )

    def test_absolute_path_outside_vault_root_falls_back(self, tmp_path):
        vault = tmp_path
        outside = Path("/tmp/totally-other/x.md")
        # path.relative_to(vault) raises; helper catches and uses parts as-is
        # /tmp/totally-other/x.md has no known segment → fallback source-only
        assert (
            infer_compile_role(outside, {}, vault_root=vault) == "source-only"
        )

    def test_vault_root_none_uses_path_parts_directly(self):
        # Absolute-looking path with known segment somewhere in it
        path = Path("/Users/alex/vault/raw/notes/x.md")
        assert infer_compile_role(path, {}) == "source-only"


class TestLocationDefaults:
    def test_covers_four_known_segments(self):
        assert set(LOCATION_DEFAULTS.keys()) == {
            "raw",
            "daily",
            "inbox",
            "knowledge",
        }

    def test_all_defaults_are_valid_roles(self):
        for role in LOCATION_DEFAULTS.values():
            assert role in VALID_ROLES
