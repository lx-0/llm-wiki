"""Tests for the M014 dream-cycle entity-page re-synthesis pipeline.

Covered:

1. Prompt-render contract — `prompts/dream_entity.md` substitutes all
   declared placeholders without raising PromptError.
2. Cost-cap enforcement — when prompt cost-estimate exceeds the per-entity
   cap, `dream_entity()` returns skipped="cost_cap_exceeded" and DOES NOT
   call the SDK (no silent burn).
3. Cooldown — entities whose `last_synthesized_at:` is within the
   cooldown window are correctly skipped; older ones are eligible.
4. Idempotency — a second invocation while still inside the cooldown is
   a no-op (skip).
5. Two-layer State+Timeline shape — the prompt explicitly cites the State
   block above `---` separator + Timeline below, so the rendered prompt
   exposes both layer markers to the model.

Also covered: corpus collection greps both raw/** and daily/** and matches
the slug as a whole word (no false positives on substring matches).

The SDK is mocked via `monkeypatch` so no Claude calls are made; only the
control-flow gates are exercised.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest


# ── Helpers ───────────────────────────────────────────────────────────


def _write_entity_page(
    vault: Path, kind: str, slug: str, *, last_synthesized_at: str | None = None,
    body: str | None = None,
) -> Path:
    """Drop a minimal entity page with the two-layer State+Timeline shape."""
    dir_ = vault / "knowledge" / kind
    dir_.mkdir(parents=True, exist_ok=True)
    fm_lines = [
        "---",
        f'title: "{slug.replace("-", " ").title()}"',
        f"type: {kind.rstrip('s')}",
        "tags: []",
        "created: 2026-04-01",
        "updated: 2026-04-01",
    ]
    if last_synthesized_at:
        fm_lines.append(f'last_synthesized_at: "{last_synthesized_at}"')
    fm_lines.append("---")
    body_text = body or (
        f"# {slug.title()}\n\n## State\n\n- **Role:** existing\n\n## Action Items\n\n"
        "## Open Threads\n\n## What they're building\n\nExisting prose.\n\n## See also\n\n"
        "---\n\n## Timeline\n\n- **2026-04-01** | `raw/notes/seed.md` — Seed mention.\n"
    )
    page = dir_ / f"{slug}.md"
    page.write_text("\n".join(fm_lines) + "\n\n" + body_text, encoding="utf-8")
    return page


def _write_substrate(vault: Path, rel: str, body: str) -> Path:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Temporary vault with the standard knowledge/{people,projects,areas} tree
    plus raw/ and daily/ substrate roots. dream module's path constants are
    monkey-patched to point here so the test never touches the real lxw vault.
    """
    for sub in (
        "knowledge/people", "knowledge/projects", "knowledge/areas",
        "knowledge/concepts", "knowledge/facts",
        "raw/transcripts", "raw/notes", "daily",
    ):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    (tmp_path / "knowledge" / "index.md").write_text(
        "# Knowledge Base Index\n\n| Article | Summary | Compiled From | Updated |\n|---|---|---|---|\n",
        encoding="utf-8",
    )
    (tmp_path / "knowledge" / "log.md").write_text("# Compile Log\n", encoding="utf-8")

    # Late-import so the monkeypatched paths take effect inside dream.
    import dream

    monkeypatch.setattr(dream, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(dream, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(dream, "DAILY_DIR", tmp_path / "daily")
    monkeypatch.setattr(dream, "KNOWLEDGE_DIR", tmp_path / "knowledge")
    monkeypatch.setattr(dream, "PEOPLE_DIR", tmp_path / "knowledge" / "people")
    monkeypatch.setattr(dream, "PROJECTS_DIR", tmp_path / "knowledge" / "projects")
    monkeypatch.setattr(dream, "AREAS_DIR", tmp_path / "knowledge" / "areas")
    monkeypatch.setattr(dream, "INDEX_FILE", tmp_path / "knowledge" / "index.md")
    monkeypatch.setattr(dream, "LOG_FILE", tmp_path / "knowledge" / "log.md")
    monkeypatch.setattr(dream, "_SUBSTRATE_ROOTS", (tmp_path / "raw", tmp_path / "daily"))
    # _ENTITY_KINDS holds Path values captured at module-import time — rebuild
    # so the test's monkeypatched dirs are visible to _resolve_entity / _list_all_entities.
    monkeypatch.setattr(
        dream, "_ENTITY_KINDS",
        {
            "people":   (tmp_path / "knowledge" / "people",   "person"),
            "projects": (tmp_path / "knowledge" / "projects", "project"),
            "areas":    (tmp_path / "knowledge" / "areas",    "area"),
        },
    )
    yield tmp_path


# ── 1. Prompt-render contract ───────────────────────────────────────


def test_prompt_render_substitutes_all_placeholders(vault: Path) -> None:
    """dream_entity.md must render without unresolved ${var} placeholders."""
    import dream
    from core.prompts import render

    _write_entity_page(vault, "people", "demo")
    _write_substrate(vault, "raw/notes/n1.md", "Note mentioning demo with details.\n")

    ent = dream._resolve_entity("demo")
    assert ent is not None

    paths = dream.collect_corpus(ent)
    assert len(paths) == 1
    prompt, _ = dream._build_prompt(ent, paths, max_turns=20)
    # No raw ${...} placeholders left.
    assert "${" not in prompt, f"unresolved placeholder in prompt: {prompt[:200]}"
    # Required strings show up.
    assert "demo" in prompt
    assert "knowledge/people/demo.md" in prompt
    # Two-layer markers are exposed to the model.
    assert "## State" in prompt
    assert "## Timeline" in prompt
    assert "---" in prompt


def test_prompt_render_explains_state_above_timeline_below(vault: Path) -> None:
    """The shape rule must be present so the model preserves State|Timeline."""
    from core.prompts import render

    body = render(
        "dream_entity",
        entity_slug="alice",
        entity_title="Alice",
        entity_type="person",
        entity_page="knowledge/people/alice.md",
        current_page="(file does not exist yet — create it from the two-layer template)",
        corpus_block="(no substrate)",
        corpus_count=0,
        corpus_chars=0,
        owner_block="",
        facts_md="(no hard facts recorded)",
        max_turns=20,
        today="2026-05-16",
        now="2026-05-16T12:00:00+00:00",
        entity_link="knowledge/people/alice",
    )
    # The shape rules:
    assert "State block lives above the `---` separator" in body or "State block above" in body
    assert "Timeline" in body and "append-only" in body
    # Cost discipline / generic-reject rule visible:
    assert "BANNED" in body or "generic" in body.lower()
    # Frontmatter housekeeping for cooldown stamp:
    assert "last_synthesized_at" in body


# ── 2. Cost-cap enforcement ──────────────────────────────────────────


def test_cost_cap_rejects_sdk_call(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When pre-flight estimate > cap, dream_entity must NOT call the SDK."""
    import dream

    _write_entity_page(vault, "people", "alex")
    # Pile up substrate to push the estimate over a tight cap.
    big = "alex " * 5000  # ~25 KB, enough that estimate exceeds $0.01
    for i in range(5):
        _write_substrate(vault, f"raw/notes/big-{i}.md", big)

    sdk_called = {"n": 0}

    async def _fake_query(*args, **kwargs):
        sdk_called["n"] += 1
        if False:  # make it an async iterator with no yields
            yield

    monkeypatch.setattr(dream, "query", _fake_query)

    ent = dream._resolve_entity("alex")
    assert ent is not None
    result = asyncio.run(dream.dream_entity(ent, cost_cap_usd=0.0001))

    assert result.skipped == "cost_cap_exceeded", f"expected cost_cap_exceeded, got {result.skipped!r}"
    assert result.actual_cost_usd == 0.0
    assert sdk_called["n"] == 0, "SDK was invoked despite cost-cap rejection — silent burn!"
    assert "COST_CAP_EXCEEDED" in result.sdk_result_text


# ── 3. Cooldown ──────────────────────────────────────────────────────


def test_cooldown_skips_recent_synthesis(vault: Path) -> None:
    """An entity synthesized today is within cooldown; older one is eligible."""
    import dream

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    long_ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

    _write_entity_page(vault, "people", "fresh", last_synthesized_at=today)
    _write_entity_page(vault, "people", "stale", last_synthesized_at=long_ago)
    _write_entity_page(vault, "people", "never")  # no last_synthesized_at

    fresh = dream._resolve_entity("fresh")
    stale = dream._resolve_entity("stale")
    never = dream._resolve_entity("never")
    assert fresh and stale and never

    assert dream.is_within_cooldown(fresh, cooldown_days=7) is True
    assert dream.is_within_cooldown(stale, cooldown_days=7) is False
    assert dream.is_within_cooldown(never, cooldown_days=7) is False, \
        "never-synthesized entity must be eligible (not within cooldown)"


def test_cooldown_zero_disables_gate(vault: Path) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _write_entity_page(vault, "people", "fresh", last_synthesized_at=today)
    import dream
    ent = dream._resolve_entity("fresh")
    assert ent is not None
    assert dream.is_within_cooldown(ent, cooldown_days=0) is False


# ── 4. Idempotency (re-run within cooldown is a no-op) ──────────────


def test_sweep_skips_cooldown_entities(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`dream_all_entities` must skip entities still within cooldown."""
    import dream

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    long_ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    _write_entity_page(vault, "people", "fresh", last_synthesized_at=today)
    _write_entity_page(vault, "people", "stale", last_synthesized_at=long_ago)

    # Even a fresh entity has substrate so non-empty corpus
    _write_substrate(vault, "raw/notes/n.md", "fresh and stale both appear here.\n")

    invocations: list[str] = []

    async def _fake_dream_entity(entity, **kwargs):
        invocations.append(entity.slug)
        return dream.DreamResult(
            entity=entity, corpus_count=1, corpus_chars=100,
            estimated_cost_usd=0.01, actual_cost_usd=0.01,
            input_tokens=10, output_tokens=10, sdk_result_text="ok",
            skipped=None, elapsed_s=0.0,
        )

    monkeypatch.setattr(dream, "dream_entity", _fake_dream_entity)

    results = asyncio.run(dream.dream_all_entities(cooldown_days=7, dry_run=False))
    assert "stale" in invocations
    assert "fresh" not in invocations, "cooldown gate failed — fresh entity was invoked"
    assert len(results) == 1


def test_sweep_respects_per_run_cost_cap(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cumulative actual_cost_usd > per_run_cap stops the sweep."""
    import dream

    # Three stale entities, all eligible.
    for slug in ("a", "b", "c"):
        _write_entity_page(vault, "people", slug, last_synthesized_at="2026-01-01")
    _write_substrate(vault, "raw/notes/all.md", "a, b, c all mentioned.\n")

    async def _fake_dream_entity(entity, **kwargs):
        return dream.DreamResult(
            entity=entity, corpus_count=1, corpus_chars=100,
            estimated_cost_usd=0.5, actual_cost_usd=0.5,
            input_tokens=10, output_tokens=10, sdk_result_text="ok",
            skipped=None, elapsed_s=0.0,
        )

    monkeypatch.setattr(dream, "dream_entity", _fake_dream_entity)

    # cap = 0.6: first run costs 0.5 (cumulative 0.5 < 0.6, OK), second pushes
    # cumulative to 1.0 > 0.6 so it gates BEFORE the third. Result: 2 ran.
    results = asyncio.run(dream.dream_all_entities(per_run_cap=0.6, cooldown_days=7))
    assert len(results) == 2, f"expected 2 entities under per-run cap, got {len(results)}"


# ── 5. Two-layer shape preserved (corpus / collection sanity) ───────


def test_collect_corpus_matches_whole_word(vault: Path) -> None:
    """Slug 'al' must NOT match 'algorithm'; it must match 'al' as a token."""
    import dream

    _write_entity_page(vault, "people", "al")
    _write_substrate(vault, "raw/notes/algo.md", "discussion of algorithms only\n")
    _write_substrate(vault, "raw/notes/mention.md", "al said hello yesterday\n")
    _write_substrate(vault, "daily/2026-05-10.md", "Met with al at the office\n")

    ent = dream._resolve_entity("al")
    assert ent is not None
    paths = dream.collect_corpus(ent)
    rels = {str(p.relative_to(vault)) for p in paths}
    assert "raw/notes/mention.md" in rels
    assert "daily/2026-05-10.md" in rels
    assert "raw/notes/algo.md" not in rels, "whole-word match failed; 'algorithms' matched 'al'"


def test_collect_corpus_picks_up_compiled_from_and_author(vault: Path) -> None:
    """Frontmatter `author: alex` and `compiled_from:` paths must surface."""
    import dream

    _write_entity_page(vault, "people", "alex")
    body = (
        "---\nauthor: alex\ntitle: Voice note\n---\n\nDictated thought.\n"
    )
    _write_substrate(vault, "raw/voice/2026-05-10.md", body)
    ent = dream._resolve_entity("alex")
    assert ent is not None
    paths = dream.collect_corpus(ent)
    rels = {str(p.relative_to(vault)) for p in paths}
    assert "raw/voice/2026-05-10.md" in rels


def test_prompt_carries_existing_state_and_timeline(vault: Path) -> None:
    """The existing page (with State + Timeline) is embedded verbatim so the
    rewriter can preserve operator-touched lines."""
    import dream

    page = _write_entity_page(
        vault, "people", "bob",
        body=(
            "# Bob\n\n## State\n\n- **Role:** OPERATOR-EDITED\n\n"
            "## Action Items\n\n- [x] OPERATOR-CHECKED-ITEM\n\n"
            "## Open Threads\n\n## What they're building\n\nNarrative.\n\n"
            "## See also\n\n---\n\n## Timeline\n\n"
            "- **2026-04-01** | `raw/notes/seed.md` — Seed.\n"
        ),
    )
    _write_substrate(vault, "raw/notes/n.md", "bob said something new\n")

    ent = dream._resolve_entity("bob")
    assert ent is not None
    paths = dream.collect_corpus(ent)
    prompt, _ = dream._build_prompt(ent, paths, max_turns=20)
    assert "OPERATOR-EDITED" in prompt
    assert "OPERATOR-CHECKED-ITEM" in prompt


# ── 6. Cost estimator ──────────────────────────────────────────────


def test_estimate_cost_monotone() -> None:
    import dream
    small = dream.estimate_cost_usd(10_000)
    big = dream.estimate_cost_usd(500_000)
    assert big > small
    # Sanity: 500K-char prompt is non-trivial.
    assert big >= 1.0, f"500K-char estimate seems too low: ${big}"


# ── 7. Agent-task spec parses & defaults make sense ─────────────────


def test_dream_cycle_agent_spec_parses() -> None:
    """prompts/agents/dream-cycle.md must parse via core.agent_spec.parse_spec."""
    from core.agent_spec import parse_spec
    from core.paths import AGENT_SPECS_DIR

    spec = parse_spec(AGENT_SPECS_DIR / "dream-cycle.md")
    assert spec.id == "dream-cycle"
    assert "Edit" in spec.allowed_tools
    assert "Write" in spec.allowed_tools
    assert spec.button is not None
    assert spec.button.shell_command_id == "agent-dream-cycle"
