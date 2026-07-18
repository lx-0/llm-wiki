"""Tests for the M014 dream-cycle entity-page re-synthesis pipeline.

Covered:

1. Prompt-render contract — `prompts/dream_entity.md` substitutes all
   declared placeholders without raising PromptError.
2. Size-cap enforcement — when the rendered prompt exceeds the per-entity
   char cap, `dream_entity()` returns kind="prompt_too_large" and DOES NOT
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
    monkeypatch.setattr(dream, "LOG_FILE", tmp_path / "knowledge" / "log.md")
    monkeypatch.setattr(dream, "_SUBSTRATE_ROOTS", (tmp_path / "raw", tmp_path / "daily"))
    # Isolate the dream side-state files so tests never touch the real STATE_DIR.
    monkeypatch.setattr(dream, "_DREAM_ACTIVATION_FILE", tmp_path / "state" / "dream-activation.json")
    monkeypatch.setattr(dream, "_DREAM_INSUFFICIENT_FILE", tmp_path / "state" / "dream-insufficient-corpus.json")
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

    _write_entity_page(vault, "people", "demo")
    _write_substrate(vault, "raw/notes/n1.md", "Note mentioning demo with details.\n")

    ent = dream._resolve_entity("demo")
    assert ent is not None

    breakdown = dream.collect_corpus_tiered(ent)
    assert len(breakdown.all_paths) == 1
    prompt, _ = dream._build_prompt(ent, breakdown.all_paths, max_turns=20, breakdown=breakdown)
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
        output_language_instruction="",
    )
    # The shape rules:
    assert "State block lives above the `---` separator" in body or "State block above" in body
    assert "Timeline" in body and "append-only" in body
    # Cost discipline / generic-reject rule visible:
    assert "BANNED" in body or "generic" in body.lower()
    # Frontmatter housekeeping for cooldown stamp:
    assert "last_synthesized_at" in body


# ── 2. Cost-cap enforcement ──────────────────────────────────────────


def test_size_cap_rejects_sdk_call(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When the prompt exceeds the size cap, dream_entity must NOT call the SDK."""
    import dream

    _write_entity_page(vault, "people", "alex")
    _write_substrate(vault, "raw/notes/n.md", "alex appears here.\n")

    sdk_called = {"n": 0}

    async def _fake_query(*args, **kwargs):
        sdk_called["n"] += 1
        if False:  # make it an async iterator with no yields
            yield

    monkeypatch.setattr(dream, "query", _fake_query)

    ent = dream._resolve_entity("alex")
    assert ent is not None
    # max_prompt_chars=1 → any real prompt exceeds it → gated pre-SDK.
    result = asyncio.run(dream.dream_entity(ent, max_prompt_chars=1))

    assert result.kind == "prompt_too_large", f"expected prompt_too_large, got {result.kind!r}"
    assert result.actual_cost_usd == 0.0
    assert sdk_called["n"] == 0, "SDK was invoked despite size-cap rejection — silent burn!"
    assert "PROMPT_TOO_LARGE" in result.sdk_result_text


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
        return dream.DreamOutcome(
            entity=entity, corpus_count=1, corpus_chars=100,
            actual_cost_usd=0.01,
            input_tokens=10, output_tokens=10, sdk_result_text="ok",
            kind=None, elapsed_s=0.0,
        )

    monkeypatch.setattr(dream, "dream_entity", _fake_dream_entity)

    results = asyncio.run(dream.dream_all_entities(cooldown_days=7, dry_run=False))
    assert "stale" in invocations
    assert "fresh" not in invocations, "cooldown gate failed — fresh entity was invoked"
    assert len(results) == 1


def test_sweep_respects_per_run_token_cap(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cumulative real tokens >= per_run_max_tokens stops the sweep."""
    import dream

    # Three stale entities, all eligible.
    for slug in ("a", "b", "c"):
        _write_entity_page(vault, "people", slug, last_synthesized_at="2026-01-01")
    _write_substrate(vault, "raw/notes/all.md", "a, b, c all mentioned.\n")

    async def _fake_dream_entity(entity, **kwargs):
        return dream.DreamOutcome(
            entity=entity, corpus_count=1, corpus_chars=100,
            actual_cost_usd=0.0,
            input_tokens=10, output_tokens=10, sdk_result_text="ok",
            kind=None, elapsed_s=0.0,
        )

    monkeypatch.setattr(dream, "dream_entity", _fake_dream_entity)

    # cap = 30 tok: entity1 -> cumulative 20 (<30, ok), entity2 -> 40 (>=30)
    # gates BEFORE the third. Result: 2 ran (20 tok/entity).
    results = asyncio.run(dream.dream_all_entities(per_run_max_tokens=30, cooldown_days=7))
    assert len(results) == 2, f"expected 2 entities under per-run token cap, got {len(results)}"


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
    paths = dream.collect_corpus_tiered(ent).all_paths
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
    paths = dream.collect_corpus_tiered(ent).all_paths
    rels = {str(p.relative_to(vault)) for p in paths}
    assert "raw/voice/2026-05-10.md" in rels


def test_prompt_carries_existing_state_and_timeline(vault: Path) -> None:
    """The existing page (with State + Timeline) is embedded verbatim so the
    rewriter can preserve operator-touched lines."""
    import dream

    _write_entity_page(
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
    breakdown = dream.collect_corpus_tiered(ent)
    prompt, _ = dream._build_prompt(ent, breakdown.all_paths, max_turns=20, breakdown=breakdown)
    assert "OPERATOR-EDITED" in prompt
    assert "OPERATOR-CHECKED-ITEM" in prompt





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


# ── A/B/C: 2026-05-31 dream-diagnostics fixes ────────────────────────


def _make_fake_query(monkeypatch, *, usage, cost, result_text="done"):
    """Install a fake SDK query yielding one AssistantMessage + ResultMessage
    carrying the given usage dict + cost. Returns a call-counter dict."""
    import dream
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

    calls = {"n": 0}

    async def _fake_query(*args, **kwargs):
        calls["n"] += 1
        yield AssistantMessage(content=[TextBlock(text=result_text)], model="m", usage=usage)
        yield ResultMessage(
            subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
            num_turns=1, session_id="s", total_cost_usd=cost, usage=usage,
            result=result_text,
        )

    monkeypatch.setattr(dream, "query", _fake_query)
    return calls


def test_low_token_warning_does_not_fire_on_cached_call(
    vault: Path, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """A: a healthy cached call reports a tiny uncached input_tokens but huge
    cache tokens + real cost. The low-token warning must NOT false-fire, and
    the reported input must be the cache-inclusive total."""
    import logging
    import dream

    _write_entity_page(vault, "people", "cached")
    _write_substrate(vault, "raw/notes/n.md", "cached appears here in substrate.\n")

    usage = {
        "input_tokens": 12,
        "cache_creation_input_tokens": 40000,
        "cache_read_input_tokens": 0,
        "output_tokens": 90,
    }
    _make_fake_query(monkeypatch, usage=usage, cost=0.79)

    ent = dream._resolve_entity("cached")
    assert ent is not None
    with caplog.at_level(logging.WARNING):
        result = asyncio.run(dream.dream_entity(ent))

    assert "SDK reported only" not in caplog.text, "false-positive low-token warning fired on a cached call"
    assert result.input_tokens == 40012, f"expected cache-inclusive total, got {result.input_tokens}"


def test_low_token_warning_still_fires_on_genuine_early_exit(
    vault: Path, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """A: a genuine early-exit reports near-zero TRUE input AND ~$0 cost —
    the diagnostic must keep its teeth."""
    import logging
    import dream

    _write_entity_page(vault, "people", "early")
    _write_substrate(vault, "raw/notes/n.md", "early appears here in substrate.\n")

    usage = {"input_tokens": 12, "cache_creation_input_tokens": 0,
             "cache_read_input_tokens": 0, "output_tokens": 3}
    _make_fake_query(monkeypatch, usage=usage, cost=0.0)

    ent = dream._resolve_entity("early")
    assert ent is not None
    with caplog.at_level(logging.WARNING):
        asyncio.run(dream.dream_entity(ent))

    assert "substrate-processing did not happen" in caplog.text


def test_skips_sdk_when_no_entity_specific_substrate(
    vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B: an entity whose only corpus is non-mentioning daily digests is a
    guaranteed no-op — dream_entity must skip the SDK call for $0."""
    import dream

    _write_entity_page(vault, "people", "lonely")
    # A recent daily digest that does NOT mention "lonely".
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _write_substrate(vault, f"daily/{today}.md", "# Daily\n\nUnrelated topics only.\n")

    calls = _make_fake_query(
        monkeypatch,
        usage={"input_tokens": 5, "output_tokens": 5},
        cost=0.0,
    )

    ent = dream._resolve_entity("lonely")
    assert ent is not None
    result = asyncio.run(dream.dream_entity(ent))

    assert result.kind == "no_entity_substrate", f"got {result.kind!r}"
    assert result.actual_cost_usd == 0.0
    assert calls["n"] == 0, "SDK invoked despite zero entity-specific substrate — wasted spend"


def test_does_not_skip_when_entity_substrate_present(
    vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B negative control: real mentioning substrate → SDK is invoked."""
    import dream

    _write_entity_page(vault, "people", "popular")
    _write_substrate(vault, "raw/notes/n.md", "popular shows up in this note.\n")

    calls = _make_fake_query(
        monkeypatch,
        usage={"input_tokens": 12, "cache_creation_input_tokens": 9000, "output_tokens": 50},
        cost=0.2,
    )

    ent = dream._resolve_entity("popular")
    assert ent is not None
    result = asyncio.run(dream.dream_entity(ent))

    assert result.kind is None, f"unexpected skip: {result.kind!r}"
    assert calls["n"] == 1


def test_build_prompt_within_budget_trims_to_fit(vault: Path) -> None:
    """C: an over-budget corpus is trimmed (lowest-value first) until it fits,
    instead of failing terminally with PROMPT_TOO_LARGE."""
    import dream

    _write_entity_page(vault, "people", "trim")
    # Several mentioning substrate files, each non-trivial.
    for i in range(6):
        _write_substrate(
            vault, f"raw/notes/n{i}.md",
            f"trim is discussed here, entry {i}. " + ("filler content. " * 80),
        )

    ent = dream._resolve_entity("trim")
    assert ent is not None
    breakdown = dream.collect_corpus_tiered(ent)

    # Full prompt size with everything in.
    full_prompt, full_chars = dream._build_prompt(
        ent, breakdown.all_paths, max_turns=20, breakdown=breakdown
    )
    assert full_chars > 0

    # Force a budget just under the full size → must drop at least one file.
    budget = full_chars - 500
    prompt, prompt_chars, trimmed, dropped = dream._build_prompt_within_budget(
        ent, breakdown, max_turns=20, max_chars=budget
    )
    assert dropped >= 1, "expected at least one file dropped to fit the budget"
    assert prompt_chars <= budget, f"trim did not reach budget: {prompt_chars} > {budget}"
    assert len(trimmed.all_paths) < len(breakdown.all_paths)


def test_build_prompt_within_budget_noop_when_under_cap(vault: Path) -> None:
    """C: a comfortably-fitting corpus is returned untrimmed."""
    import dream

    _write_entity_page(vault, "people", "small")
    _write_substrate(vault, "raw/notes/n.md", "small mention here.\n")

    ent = dream._resolve_entity("small")
    assert ent is not None
    breakdown = dream.collect_corpus_tiered(ent)
    prompt, prompt_chars, trimmed, dropped = dream._build_prompt_within_budget(
        ent, breakdown, max_turns=20, max_chars=10_000_000
    )
    assert dropped == 0
    assert trimmed is breakdown


def test_insufficient_corpus_noop_logs_at_info_not_warning(
    vault: Path, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """A designed INSUFFICIENT_CORPUS no-op must log at INFO, staying out of
    the errors-only triage stream (e.g. generic-noun slug false-positives)."""
    import logging
    import dream

    _write_entity_page(vault, "people", "kontakte")
    _write_substrate(vault, "raw/notes/n.md", "kontakte appears generically here.\n")
    _make_fake_query(
        monkeypatch,
        usage={"input_tokens": 12, "cache_creation_input_tokens": 80000, "output_tokens": 1800},
        cost=1.04,
        result_text="INSUFFICIENT_CORPUS: 0 specific claims could be cited from 8 sources",
    )

    ent = dream._resolve_entity("kontakte")
    assert ent is not None
    with caplog.at_level(logging.INFO):
        asyncio.run(dream.dream_entity(ent))

    noop_lines = [r for r in caplog.records if "finished without modifying" in r.getMessage()]
    assert noop_lines, "expected the no-op diagnostic line"
    warned = [r for r in noop_lines if r.levelno >= logging.WARNING]
    assert not warned, "INSUFFICIENT_CORPUS no-op must not hit WARNING/errors-log"


def test_unexplained_noop_still_warns(
    vault: Path, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """A byte-identical page with NO sentinel (possible silent write-failure)
    must keep its WARNING — that's the diagnostic this check exists for."""
    import logging
    import dream

    _write_entity_page(vault, "people", "silent")
    _write_substrate(vault, "raw/notes/n.md", "silent appears in this note.\n")
    _make_fake_query(
        monkeypatch,
        usage={"input_tokens": 12, "cache_creation_input_tokens": 9000, "output_tokens": 50},
        cost=0.2,
        result_text="I would update the State section with the new role, but ...",
    )

    ent = dream._resolve_entity("silent")
    assert ent is not None
    with caplog.at_level(logging.INFO):
        asyncio.run(dream.dream_entity(ent))

    warned = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and "finished without modifying" in r.getMessage()
    ]
    assert warned, "unexplained no-op should still warn (silent write-failure surface)"


# ── Insufficient-corpus backoff (2026-06-02) ─────────────────────────


def test_backoff_window_is_exponential_capped():
    import dream
    f = dream._insufficient_backoff_days
    assert f(0, base_days=7, max_days=30) == 0.0
    assert f(1, base_days=7, max_days=30) == 7.0
    assert f(2, base_days=7, max_days=30) == 14.0
    assert f(3, base_days=7, max_days=30) == 28.0
    assert f(4, base_days=7, max_days=30) == 30.0   # 56 capped to 30
    assert f(9, base_days=7, max_days=30) == 30.0


def test_insufficient_corpus_run_records_and_backs_off(
    vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An INSUFFICIENT_CORPUS run records backoff state; the next sweep skips
    the entity instead of re-spending."""
    import dream

    _write_entity_page(vault, "people", "kontakte")
    _write_substrate(vault, "raw/notes/n.md", "kontakte appears generically.\n")
    _make_fake_query(
        monkeypatch,
        usage={"input_tokens": 12, "cache_creation_input_tokens": 80000, "output_tokens": 1800},
        cost=1.04,
        result_text="INSUFFICIENT_CORPUS: 0 specific claims could be cited from 8 sources",
    )

    ent = dream._resolve_entity("kontakte")
    assert ent is not None
    result = asyncio.run(dream.dream_entity(ent))

    assert result.insufficient_corpus is True
    # State recorded → entity is now inside its backoff window.
    assert is_within_backoff(dream, ent)
    # And the sweep filter would skip it.
    assert dream.is_within_insufficient_backoff(ent) is True


def is_within_backoff(dream_mod, ent):
    state = dream_mod._load_insufficient_state()
    return ent.slug in state and state[ent.slug]["count"] == 1


# ── Web-research post-pass fires on the sweep path (issue #2 regression) ──


def test_web_research_fires_on_sweep_not_just_single_entity(
    vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The web-research post-pass must fire for entities synthesized by the
    SWEEP (the unattended piggyback path), not only the single-entity CLI
    branch. Regression guard: the invocation had drifted into the
    `wiki dream-entity` branch, leaving the only unattended path
    (dream_all_entities → dream_entity) dark despite the shipped design pinning
    it to the dream_entity() success seam."""
    import dream

    _write_entity_page(vault, "people", "swept", last_synthesized_at="2026-01-01")
    _write_substrate(vault, "raw/notes/n.md", "swept is mentioned in this note.\n")
    # Drive the REAL dream_entity (not a monkeypatched stub) via a fake SDK call
    # so the success seam is actually reached.
    _make_fake_query(
        monkeypatch,
        usage={"input_tokens": 12, "cache_creation_input_tokens": 9000, "output_tokens": 50},
        cost=0.2,
        result_text="updated",
    )

    fired: list[str] = []
    monkeypatch.setattr(dream, "_maybe_web_research", lambda ent: fired.append(ent.slug))

    asyncio.run(dream.dream_all_entities(cooldown_days=7))

    assert "swept" in fired, "web-research post-pass did not fire on the sweep path"


def test_successful_synthesis_clears_backoff(
    vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once a real synthesis lands, the backoff entry is cleared so the entity
    returns to normal cadence."""
    import dream

    page = _write_entity_page(vault, "people", "recovers")
    _write_substrate(vault, "raw/notes/n.md", "recovers is mentioned here.\n")

    # Seed a pre-existing backoff entry.
    dream._record_insufficient_corpus("recovers")
    assert dream.is_within_insufficient_backoff(dream._resolve_entity("recovers"))

    # A fake that actually writes the page → counts as a successful synthesis.
    import dream as _d
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

    async def _writing_query(*args, **kwargs):
        page.write_text(page.read_text(encoding="utf-8") + "\n- new line\n", encoding="utf-8")
        yield AssistantMessage(content=[TextBlock(text="updated")], model="m",
                               usage={"input_tokens": 12, "cache_creation_input_tokens": 9000, "output_tokens": 60})
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1,
                            is_error=False, num_turns=1, session_id="s",
                            total_cost_usd=0.3, usage={"input_tokens": 12, "cache_creation_input_tokens": 9000, "output_tokens": 60},
                            result="updated")
    monkeypatch.setattr(_d, "query", _writing_query)

    ent = dream._resolve_entity("recovers")
    result = asyncio.run(dream.dream_entity(ent))

    assert result.insufficient_corpus is False
    assert "recovers" not in dream._load_insufficient_state(), "backoff not cleared after synthesis"


def test_sweep_skips_backed_off_entity(
    vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """dream_all_entities must not select an entity inside its backoff window."""
    import dream

    _write_entity_page(vault, "people", "dormant")
    _write_substrate(vault, "raw/notes/n.md", "dormant is named here.\n")
    dream._record_insufficient_corpus("dormant")

    invoked: list[str] = []

    async def _fake_dream_entity(entity, **kwargs):
        invoked.append(entity.slug)
        return dream.DreamOutcome(
            entity=entity, corpus_count=0, corpus_chars=0, actual_cost_usd=0.0,
            input_tokens=0, output_tokens=0, sdk_result_text="", kind=None,
            elapsed_s=0.0,
        )

    monkeypatch.setattr(dream, "dream_entity", _fake_dream_entity)
    asyncio.run(dream.dream_all_entities(cooldown_days=0))

    assert "dormant" not in invoked, "backed-off entity was selected by the sweep"


# ── build_sweep_candidates: single source of truth for gate verdicts ──


def test_build_sweep_candidates_flags_cooldown_and_backoff(
    vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every entity carries every gate verdict — the shared row the sweep
    filters on and list_candidates renders. Backoff and cooldown are distinct
    axes and both surface."""
    import dream

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _write_entity_page(vault, "people", "fresh", last_synthesized_at=today)  # cooldown
    _write_entity_page(vault, "people", "dormant")                          # backoff
    _write_entity_page(vault, "people", "ready")                            # clean
    dream._record_insufficient_corpus("dormant")

    rows = {c.entity.slug: c for c in dream.build_sweep_candidates(cooldown_days=7)}

    assert rows["fresh"].cooldown_active is True
    assert rows["fresh"].backoff_active is False
    assert rows["dormant"].backoff_active is True
    assert rows["dormant"].cooldown_active is False
    assert rows["ready"].cooldown_active is False
    assert rows["ready"].backoff_active is False


def test_list_candidates_surfaces_backoff(
    vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The debug view exposes insufficient-corpus backoff, not just cooldown —
    the omission that made the sweep and list-candidates diverge."""
    import dream

    _write_entity_page(vault, "people", "dormant")
    dream._record_insufficient_corpus("dormant")

    rows = {r["slug"]: r for r in dream.list_candidates()}
    assert rows["dormant"]["backoff_active"] is True
    assert rows["dormant"]["cooldown_active"] is False
