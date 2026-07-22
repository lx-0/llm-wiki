"""M012: tests for connection-article quality lint.

Covers:
  - good connection article passes lint
  - shallow co-occurrence connection fails (under_linked + missing_kind)
  - missing tension/mechanism/dependency frontmatter fails
  - word-count gate fires
  - regression: extended check_concept_domain_tag still flags concepts
  - regression: check_concept_domain_tag now also flags connections without
    a domain tag

Strategy mirrors `tests/test_two_layer_lint.py`: build a fake
`knowledge/` tree under tmp_path, build a LintContext over it,
invoke the check, assert issue codes.
"""
from __future__ import annotations

import pytest

import lint


GOOD_CONNECTION = """\
---
title: "Connection: A2A enables Work Orchestration"
type: connection
mechanism: "A2A's task-state model provides the inter-agent dispatch primitive that the work-orchestration gap had identified as missing."
connects:
  - "concepts/a2a-fleet-communication"
  - "concepts/work-orchestration-gap"
tags: [fleet]
created: 2026-04-20
---

# Connection: A2A enables Work Orchestration

## The Claim

The [[concepts/work-orchestration-gap]] surfaced on 2026-04-17 named "task
dispatch between agents" as Fleet's missing primitive. One day later,
[[concepts/a2a-fleet-communication]] adopted A2A, whose `a2a_tasks` table
with 8 spec-defined states is exactly that dispatch primitive. The gap and
the solution were discovered independently but the protocol's task model
resolves the architectural hole the gap analysis predicted.
"""


SHALLOW_COOCCURRENCE = """\
---
title: "Connection: AI and Agents"
type: connection
tags: [fleet]
---

# Connection: AI and Agents

Both AI and agents are related to LLMs. See [[concepts/ai]].
"""


MISSING_KIND = """\
---
title: "Connection: X and Y"
type: connection
connects:
  - "concepts/x"
  - "concepts/y"
tags: [fleet]
---

# Connection: X and Y

[[concepts/x]] and [[concepts/y]] interact in a few ways. The first concept
provides a substrate that the second consumes; the second produces signals
that the first then uses for routing. This wiring matters because without
it the system would deadlock on schema-mismatch errors at the boundary.
"""


SHORT_BODY = """\
---
title: "Connection: short"
type: connection
mechanism: "X drives Y."
tags: [fleet]
---

# Short

[[concepts/x]] and [[concepts/y]] connect.
"""


CONCEPT_NO_DOMAIN_TAG = """\
---
title: "Concept: orphan"
type: concept
tags: [random-non-domain]
---

# Concept: orphan

Body text.
"""


CONNECTION_NO_DOMAIN_TAG = """\
---
title: "Connection: no domain"
type: connection
mechanism: "X drives Y."
---

# Connection: no domain

[[concepts/x]] and [[concepts/y]] interact through a documented dispatch
chain that the operator surfaced in a longer review session last week —
enough body text here to clear the fifty word floor without artificial
padding loops, since the operator already explained the mechanism in
depth and the wikilink endpoints are both present already.
"""


@pytest.fixture
def with_knowledge(tmp_path):
    """Materialise a fake knowledge/ tree and build a LintContext over it."""
    def _setup(files: dict[str, str]) -> lint.LintContext:
        knowledge = tmp_path / "knowledge"
        for rel, content in files.items():
            target = knowledge / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return lint.build_context(vault=tmp_path, knowledge_dir=knowledge, state={})
    return _setup


def _codes_for_file(issues: list[lint.Issue], rel: str) -> set[str]:
    return {i.check for i in issues if i.file == rel}


# ── check_connection_depth ─────────────────────────────────────────


def test_good_connection_passes_depth_check(with_knowledge):
    ctx = with_knowledge({"connections/good.md": GOOD_CONNECTION})
    issues = lint.check_connection_depth(ctx)
    assert _codes_for_file(issues, "connections/good.md") == set(), (
        f"Expected no issues for good connection, got: {issues}"
    )


def test_shallow_cooccurrence_fails_depth_check(with_knowledge):
    ctx = with_knowledge({"connections/shallow.md": SHALLOW_COOCCURRENCE})
    issues = lint.check_connection_depth(ctx)
    codes = _codes_for_file(issues, "connections/shallow.md")
    # Co-occurrence article cites only one knowledge wikilink AND has no
    # mechanism/tension/dependency frontmatter AND has very short body.
    assert "connection_under_linked" in codes
    assert "connection_missing_kind" in codes
    assert "connection_shallow_body" in codes


def test_missing_kind_frontmatter_fails(with_knowledge):
    ctx = with_knowledge({"connections/no_kind.md": MISSING_KIND})
    issues = lint.check_connection_depth(ctx)
    codes = _codes_for_file(issues, "connections/no_kind.md")
    assert "connection_missing_kind" in codes
    # Body has two distinct wikilinks and >50 words — only the kind field is missing.
    assert "connection_under_linked" not in codes
    assert "connection_shallow_body" not in codes


def test_short_body_fails_word_count_gate(with_knowledge):
    ctx = with_knowledge({"connections/short.md": SHORT_BODY})
    issues = lint.check_connection_depth(ctx)
    codes = _codes_for_file(issues, "connections/short.md")
    assert "connection_shallow_body" in codes


def test_tension_field_accepted_as_kind(with_knowledge):
    """`tension:` is one of the three valid kind discriminators (mechanism /
    tension / dependency). A connection that uses `tension:` should clear the
    missing_kind check even though it lacks `mechanism:`."""
    article = GOOD_CONNECTION.replace(
        'mechanism: "A2A\'s task-state model provides the inter-agent dispatch primitive that the work-orchestration gap had identified as missing."',
        'tension: "A2A spec assumes a single dispatcher, but Fleet\'s work-orchestration model requires multiple."',
    )
    ctx = with_knowledge({"connections/tension.md": article})
    issues = lint.check_connection_depth(ctx)
    assert "connection_missing_kind" not in _codes_for_file(
        issues, "connections/tension.md"
    )


def test_dependency_field_accepted_as_kind(with_knowledge):
    article = GOOD_CONNECTION.replace(
        'mechanism: "A2A\'s task-state model provides the inter-agent dispatch primitive that the work-orchestration gap had identified as missing."',
        'dependency: "Work orchestration cannot ship until A2A is in place."',
    )
    ctx = with_knowledge({"connections/dep.md": article})
    issues = lint.check_connection_depth(ctx)
    assert "connection_missing_kind" not in _codes_for_file(
        issues, "connections/dep.md"
    )


def test_substrate_wikilinks_do_not_count_as_endpoints(with_knowledge):
    """A connection that cites two `daily/` files but only one `concepts/`
    wikilink should still fire `connection_under_linked` — substrate is the
    source layer, not a concept endpoint."""
    article = """\
---
title: "Connection: substrate-only"
type: connection
mechanism: "X drives Y."
tags: [fleet]
---

# Connection: substrate-only

[[concepts/x]] showed up in [[daily/2026-05-01]] and again in
[[daily/2026-05-02]]. The pattern of recurrence suggests an emerging
relationship worth tracking in detail across multiple coming weeks, but
for now the substrate citations are all we have to anchor it.
"""
    ctx = with_knowledge({"connections/sub.md": article})
    issues = lint.check_connection_depth(ctx)
    codes = _codes_for_file(issues, "connections/sub.md")
    assert "connection_under_linked" in codes


def test_index_and_log_files_are_skipped(with_knowledge):
    """`connections/index.md` and `connections/log.md` are meta-files, not
    connection articles — they must not trigger the depth check."""
    ctx = with_knowledge({
        "connections/index.md": "# Index\n",
        "connections/log.md": "# Log\n",
    })
    issues = lint.check_connection_depth(ctx)
    rels = {i.file for i in issues}
    assert "connections/index.md" not in rels
    assert "connections/log.md" not in rels


# ── check_concept_domain_tag regression + extension ────────────────


def test_concept_without_domain_tag_still_flagged(with_knowledge):
    """Regression: extending the check to walk connections/ must NOT break
    the original concept walk."""
    ctx = with_knowledge({"concepts/orphan.md": CONCEPT_NO_DOMAIN_TAG})
    issues = lint.check_concept_domain_tag(ctx)
    codes = _codes_for_file(issues, "concepts/orphan.md")
    assert "concept_no_domain_tag" in codes


def test_connection_without_domain_tag_now_flagged(with_knowledge):
    """Extension: connection without a domain tag should fire the same
    issue code (`concept_no_domain_tag` — kept for backwards-compat)."""
    ctx = with_knowledge({"connections/no_tag.md": CONNECTION_NO_DOMAIN_TAG})
    issues = lint.check_concept_domain_tag(ctx)
    codes = _codes_for_file(issues, "connections/no_tag.md")
    assert "concept_no_domain_tag" in codes


def test_good_connection_has_no_domain_tag_issue(with_knowledge):
    """The GOOD_CONNECTION fixture carries `tags: [fleet]` — must not fire
    the domain-tag check."""
    ctx = with_knowledge({"connections/good.md": GOOD_CONNECTION})
    issues = lint.check_concept_domain_tag(ctx)
    codes = _codes_for_file(issues, "connections/good.md")
    assert "concept_no_domain_tag" not in codes
