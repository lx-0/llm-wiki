"""Tests for the daily-digest runner's deterministic Captures-section injection
(M025-S02-T02). The section content itself is built + tested in
test_capture_index.py; here we test the idempotent replace-or-append wiring."""

from __future__ import annotations

import daily_digest_runner as r

SECTION = "## Captures\n\n- `abc12345` · buy milk → [[knowledge/projects/groceries.md]]\n"


def test_inject_appends_when_absent():
    text = "---\ntitle: x\n---\n# Daily\n\n## Highlights\n- a\n"
    out = r._inject_captures_section(text, SECTION)
    assert "## Highlights" in out
    assert out.rstrip().endswith("→ [[knowledge/projects/groceries.md]]")
    assert "## Captures" in out


def test_inject_replaces_existing_and_is_idempotent():
    text = "# Daily\n\n## Highlights\n- a\n\n## Captures\n\n- `old` → stale\n"
    once = r._inject_captures_section(text, SECTION)
    assert "`abc12345`" in once and "`old`" not in once
    assert "## Highlights" in once
    # re-running the digest must not stack a second Captures section
    twice = r._inject_captures_section(once, SECTION)
    assert twice == once
    assert once.count("## Captures") == 1


def test_inject_replace_preserves_following_section():
    text = "# Daily\n\n## Captures\n\n- `old` → stale\n\n## Email\n- mail summary\n"
    out = r._inject_captures_section(text, SECTION)
    assert "`abc12345`" in out and "`old`" not in out
    assert "## Email" in out and "- mail summary" in out
    assert out.count("## Captures") == 1
