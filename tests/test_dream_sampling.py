"""Tests for M016 dream-cycle sampled-activation + conflict-aware corpus.

Covers the 4-tier corpus assembly that replaced M014's flat "load every
mentioning file" approach:

  Tier 1 — always-include (operator-authored + recent + daily digests + entity page)
  Tier 2 — weighted probabilistic sample of older substrate
  Tier 3 — conflict-aware reshape (prompt-side mandate)
  Tier 4 — daily/<date>.md digests (M001 — already shipped)

Plus the activation-tracking mechanism: `last_dreamed_at:` write-back into
substrate frontmatter so files cycle through Tier-2 sampling over time.

Bounded-cost guarantee: corpus stays ≤~700 KB even when the substrate pool
runs to hundreds of files. We exercise that via a deliberately-large
substrate population and assert the rendered block stays under the cap.
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest
import yaml


# ── Fixtures (mirror test_dream_cycle.py shape) ─────────────────────


def _write_entity_page(vault: Path, kind: str, slug: str, *, body: str | None = None) -> Path:
    dir_ = vault / "knowledge" / kind
    dir_.mkdir(parents=True, exist_ok=True)
    fm = [
        "---",
        f'title: "{slug.title()}"',
        f"type: {kind.rstrip('s')}",
        "---",
    ]
    page = dir_ / f"{slug}.md"
    page.write_text("\n".join(fm) + "\n\n" + (body or f"# {slug}\n\n## State\n\n## Timeline\n"), encoding="utf-8")
    return page


def _write_substrate(
    vault: Path,
    rel: str,
    body: str,
    *,
    mtime: float | None = None,
    frontmatter: dict | None = None,
) -> Path:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if frontmatter:
        fm_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
        text = f"---\n{fm_text}---\n{body}"
    else:
        text = body
    path.write_text(text, encoding="utf-8")
    if mtime is not None:
        import os
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Temp vault with the standard tree, monkey-patched into dream module."""
    for sub in (
        "knowledge/people", "knowledge/projects", "knowledge/areas",
        "knowledge/concepts",
        "raw/transcripts/jamie", "raw/transcripts/gmeet",
        "raw/notes/email", "raw/notes/calendar", "raw/notes/screenshots",
        "raw/notes/longform", "raw/memories",
        "daily",
    ):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    (tmp_path / "knowledge" / "index.md").write_text(
        "# Knowledge\n\n| Article | Summary | Compiled From | Updated |\n|---|---|---|---|\n",
        encoding="utf-8",
    )
    (tmp_path / "knowledge" / "log.md").write_text("# Log\n", encoding="utf-8")

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
    monkeypatch.setattr(
        dream, "_ENTITY_KINDS",
        {
            "people":   (tmp_path / "knowledge" / "people",   "person"),
            "projects": (tmp_path / "knowledge" / "projects", "project"),
            "areas":    (tmp_path / "knowledge" / "areas",    "area"),
        },
    )
    yield tmp_path


# ── Tier 1 mechanics ────────────────────────────────────────────────


def test_tier1_includes_most_recent_n_substrate(vault: Path) -> None:
    """`dream_tier1_recent_count` files appear in Tier 1 regardless of age-decay."""
    import dream

    _write_entity_page(vault, "people", "alex")
    now = time.time()
    # 30 substrate files at descending mtime — newest first
    for i in range(30):
        _write_substrate(
            vault, f"raw/notes/longform/n{i:02d}.md",
            f"# Note {i}\n\nalex did something interesting.\n",
            mtime=now - i * 86400,
        )

    ent = dream._resolve_entity("alex")
    assert ent is not None
    bd = dream.collect_corpus_tiered(
        ent, tier1_recent_count=10, tier1_digest_days=0, tier2_sample_count=0,
        rng_seed=42,
    )

    assert len(bd.tier1_recent) == 10
    # Recents are newest-first
    recent_names = [p.name for p in bd.tier1_recent]
    assert recent_names == [f"n{i:02d}.md" for i in range(10)]


def test_tier1_includes_daily_digests(vault: Path) -> None:
    """Last M daily/<date>.md files appear in Tier 1 regardless of slug mention."""
    import dream

    _write_entity_page(vault, "people", "alex")
    # 10 digest files; only N most-recent should land in Tier 1
    today = datetime.now(timezone.utc).date()
    for i in range(10):
        d = today - timedelta(days=i)
        _write_substrate(
            vault, f"daily/{d.isoformat()}.md",
            f"# {d.isoformat()}\n\nGeneric digest content (no slug mention).\n",
        )

    ent = dream._resolve_entity("alex")
    assert ent is not None
    bd = dream.collect_corpus_tiered(
        ent, tier1_recent_count=0, tier1_digest_days=5, tier2_sample_count=0,
        rng_seed=42,
    )
    assert len(bd.tier1_digests) == 5
    # Newest-first
    expected = [(today - timedelta(days=i)).isoformat() + ".md" for i in range(5)]
    assert [p.name for p in bd.tier1_digests] == expected


def test_tier1_includes_operator_authored_content(vault: Path) -> None:
    """Files with `author: <slug>` in knowledge/ are hard-included regardless of recency."""
    import dream

    _write_entity_page(vault, "people", "alex")
    # Operator-authored concept (no mention of slug in body, just frontmatter)
    _write_substrate(
        vault, "knowledge/concepts/personal-music-taste.md",
        "# Music\n\nThoughts on bands.\n",
        frontmatter={"title": "Music Taste", "author": "alex", "compile_role": "source-and-final"},
    )
    # Non-authored concept that mentions slug — should NOT appear as authored
    _write_substrate(
        vault, "knowledge/concepts/some-topic.md",
        "Topic page authored by the compile agent. alex mentioned here.\n",
        frontmatter={"title": "Some Topic"},
    )

    ent = dream._resolve_entity("alex")
    assert ent is not None
    bd = dream.collect_corpus_tiered(ent, tier2_sample_count=0, rng_seed=42)

    authored_names = [p.name for p in bd.tier1_authored]
    assert "personal-music-taste.md" in authored_names
    assert "some-topic.md" not in authored_names


def test_tier1_excludes_entity_page_from_corpus_paths(vault: Path) -> None:
    """Entity page itself is rendered as `current_page`, not in the corpus block."""
    import dream

    page = _write_entity_page(vault, "people", "alex")
    _write_substrate(vault, "raw/notes/email/n.md", "alex sent a thing\n")

    ent = dream._resolve_entity("alex")
    assert ent is not None
    bd = dream.collect_corpus_tiered(ent, rng_seed=42)
    assert page.resolve() not in [p.resolve() for p in bd.all_paths]


# ── Tier 2 mechanics (weighted sampling) ───────────────────────────


def test_tier2_samples_K_files_from_older_pool(vault: Path) -> None:
    """K-element sample drawn from the pool of substrate older than Tier 1."""
    import dream

    _write_entity_page(vault, "people", "alex")
    now = time.time()
    # 50 files older than Tier 1
    for i in range(50):
        _write_substrate(
            vault, f"raw/notes/email/old{i:02d}.md",
            f"alex was mentioned here, message {i}\n",
            mtime=now - (100 + i) * 86400,
        )
    # 5 recent files for Tier 1
    for i in range(5):
        _write_substrate(
            vault, f"raw/notes/email/new{i:02d}.md",
            f"alex recent {i}\n",
            mtime=now - i * 86400,
        )

    ent = dream._resolve_entity("alex")
    assert ent is not None
    bd = dream.collect_corpus_tiered(
        ent, tier1_recent_count=5, tier1_digest_days=0, tier2_sample_count=20,
        rng_seed=42,
    )
    assert len(bd.tier1_recent) == 5
    assert len(bd.tier2_sampled) == 20
    assert bd.tier2_pool_size == 50
    # No overlap between tiers
    t1 = {p.resolve() for p in bd.tier1_recent}
    t2 = {p.resolve() for p in bd.tier2_sampled}
    assert not (t1 & t2)


def test_compute_sampling_score_components(vault: Path) -> None:
    """Score = importance × recency_decay × dreams_since × noise."""
    import dream

    now = time.time()
    # Same-content file in two locations; different importance weights
    high = _write_substrate(vault, "raw/memories/m.md", "alex memory\n", mtime=now)
    low = _write_substrate(vault, "raw/notes/screenshots/s.md", "alex screenshot\n", mtime=now)

    rng = random.Random(42)
    s_high = dream._compute_sampling_score(high, vault_root=vault, rng=rng, now=now)
    rng = random.Random(42)
    s_low = dream._compute_sampling_score(low, vault_root=vault, rng=rng, now=now)

    # With identical noise (same seed), importance ratio drives the result.
    # raw/memories/ = 3.0, raw/notes/screenshots/ = 0.8
    assert s_high > s_low
    ratio = s_high / s_low
    assert 3.5 < ratio < 4.0, f"importance ratio off: 3.0/0.8 = 3.75, got {ratio}"


def test_recency_decay_monotone(vault: Path) -> None:
    import dream
    now = time.time()
    fresh = dream._recency_decay(now, now=now)
    old = dream._recency_decay(now - 365 * 86400, now=now)
    very_old = dream._recency_decay(now - 1000 * 86400, now=now)
    assert fresh == 1.0
    assert 0.0 < very_old < old < fresh
    # 90-day half-life check
    half = dream._recency_decay(now - 90 * 86400, now=now)
    assert 0.49 < half < 0.51


def test_importance_lookup(vault: Path) -> None:
    import dream
    assert dream._importance_for("raw/memories/m.md") == 3.0
    assert dream._importance_for("raw/transcripts/jamie/foo.md") == 2.0
    assert dream._importance_for("raw/transcripts/gmeet/bar.md") == 2.0
    assert dream._importance_for("raw/notes/longform/baz.md") == 1.5
    assert dream._importance_for("raw/notes/email/x.md") == 1.0
    assert dream._importance_for("raw/notes/screenshots/y.md") == 0.8
    assert dream._importance_for("raw/notes/other/z.md") == 1.0
    assert dream._importance_for("raw/random/q.md") == 1.0


def test_never_dreamed_file_dominates_score(vault: Path) -> None:
    """A file with no last_dreamed_at: gets the sentinel; beats stamped files."""
    import dream
    now = time.time()
    fresh = _write_substrate(vault, "raw/notes/email/fresh.md", "alex\n", mtime=now)
    # Stamped file: dreamed today
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stamped = _write_substrate(
        vault, "raw/notes/email/stamped.md", "alex\n", mtime=now,
        frontmatter={"last_dreamed_at": today},
    )

    rng = random.Random(42)
    s_fresh = dream._compute_sampling_score(fresh, vault_root=vault, rng=rng, now=now)
    rng = random.Random(42)
    s_stamped = dream._compute_sampling_score(stamped, vault_root=vault, rng=rng, now=now)
    assert s_fresh > s_stamped * 100  # huge ratio — sentinel is 1e6


# ── last_dreamed_at write-back ─────────────────────────────────────


def test_write_last_dreamed_at_creates_frontmatter(vault: Path) -> None:
    """File without frontmatter gets one synthesized at the top."""
    import dream
    p = _write_substrate(vault, "raw/notes/email/no-fm.md", "Body only — no frontmatter.\n")
    when = datetime(2026, 5, 17, tzinfo=timezone.utc)
    assert dream._write_last_dreamed_at(p, when=when) is True
    text = p.read_text()
    assert text.startswith("---\n")
    fm_end = text.find("\n---\n", 4)
    assert fm_end != -1
    fm = yaml.safe_load(text[4:fm_end])
    assert fm["last_dreamed_at"] == "2026-05-17"


def test_write_last_dreamed_at_preserves_existing_fm(vault: Path) -> None:
    import dream
    p = _write_substrate(
        vault, "raw/notes/email/with-fm.md", "Body here.\n",
        frontmatter={"title": "x", "author": "alex"},
    )
    when = datetime(2026, 5, 17, tzinfo=timezone.utc)
    dream._write_last_dreamed_at(p, when=when)
    fm, body = dream._parse_frontmatter(p.read_text())
    assert fm["title"] == "x"
    assert fm["author"] == "alex"
    assert fm["last_dreamed_at"] == "2026-05-17"
    assert "Body here." in body


def test_write_last_dreamed_at_idempotent_same_day(vault: Path) -> None:
    """Re-stamping with the same date is a no-op (don't churn mtime)."""
    import dream
    p = _write_substrate(
        vault, "raw/notes/email/x.md", "Body.\n",
        frontmatter={"last_dreamed_at": "2026-05-17"},
    )
    when = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
    assert dream._write_last_dreamed_at(p, when=when) is False  # no-op


def test_dreams_since_last_seen_reads_stamp(vault: Path) -> None:
    import dream
    now = datetime.now(timezone.utc)
    five_days_ago = (now - timedelta(days=5)).strftime("%Y-%m-%d")
    p = _write_substrate(
        vault, "raw/notes/email/x.md", "Body.\n",
        frontmatter={"last_dreamed_at": five_days_ago},
    )
    days = dream._dreams_since_last_seen_days(p, now=now)
    # strftime("%Y-%m-%d") truncates to midnight, so the gap can be anywhere in
    # [5.0, 6.0) depending on time-of-day at test runtime.
    assert 5.0 <= days < 6.0

    unstamped = _write_substrate(vault, "raw/notes/email/y.md", "Body.\n")
    days_un = dream._dreams_since_last_seen_days(unstamped, now=now)
    assert days_un >= 1e5  # sentinel


# ── Conflict-aware reshape (Tier 3 — prompt mandate present) ────────


def test_prompt_carries_conflict_aware_reshape_mandate() -> None:
    """Prompt must contain the explicit RE-EVALUATE / supersede mandate."""
    from core.prompts import render
    body = render(
        "dream_entity",
        entity_slug="x", entity_title="X", entity_type="person",
        entity_page="knowledge/people/x.md",
        current_page="(none)",
        corpus_block="(empty)", corpus_count=0, corpus_chars=0,
        owner_block="", facts_md="",
        max_turns=20, today="2026-05-17",
        now="2026-05-17T00:00:00Z",
        entity_link="knowledge/people/x",
    )
    # Tier 3 keywords MUST be present (mandate is in dream_entity.md Step 2):
    assert "Conflict-aware reshape" in body
    assert "RE-EVALUATE" in body
    assert "superseded" in body
    # Tier 1/2 distinction surfaced to the model:
    assert "Tier 1" in body
    assert "Tier 2" in body


# ── Bounded-cost guarantee (the M016 fix) ───────────────────────────


def test_corpus_stays_bounded_on_large_substrate_pool(vault: Path) -> None:
    """500 mentioning files → corpus block stays under ~700 KB (M016 fix)."""
    import dream

    _write_entity_page(vault, "people", "alex")
    now = time.time()
    # Big substrate body — 20 KB per file — to push the M014 flat-collect
    # over the cliff. M016 must truncate per-file AND sample, so the total
    # corpus stays bounded.
    big_body = "alex mentioned here. " * 1500  # ~30 KB per file
    for i in range(500):
        sub = "raw/notes/email" if i % 2 == 0 else "raw/notes/longform"
        _write_substrate(
            vault, f"{sub}/n{i:04d}.md", big_body,
            mtime=now - i * 3600,
        )

    ent = dream._resolve_entity("alex")
    assert ent is not None
    bd = dream.collect_corpus_tiered(ent, rng_seed=42)

    # Tier limits at defaults: 20 recent + 50 sampled = 70 files MAX
    assert len(bd.tier1_recent) == 20
    assert len(bd.tier2_sampled) == 50
    assert bd.tier2_pool_size == 480  # 500 total - 20 in Tier 1

    block = dream.render_corpus_block_tiered(bd, vault_root=vault)
    # 70 files × 8 KB truncation + per-file header overhead ≈ ≤700 KB
    assert len(block) < 700_000, f"corpus block too big: {len(block)} bytes"

    # Sanity: a flat collect (M014 path) would have rendered 500 × 8 KB =
    # 4 MB. Verify the M014 shim still works for back-compat though.
    legacy = dream.collect_corpus(ent, vault_root=vault)
    # legacy returns the tiered all_paths — still bounded by construction
    assert len(legacy) <= 70


# ── end-to-end: stamp write-back actually happens after a (faked) dream ─


def test_dream_entity_stamps_last_dreamed_at_after_sdk(
    vault: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful dream must write last_dreamed_at: to every corpus file."""
    import asyncio
    import dream
    from claude_agent_sdk import ResultMessage

    _write_entity_page(vault, "people", "alex")
    p1 = _write_substrate(vault, "raw/notes/email/a.md", "alex was here.\n")
    p2 = _write_substrate(vault, "raw/notes/email/b.md", "alex too.\n")

    # Fake SDK: yield a ResultMessage with non-zero cost so the post-success
    # stamp path runs.
    class _UsageMsg:
        usage = {"input_tokens": 100, "output_tokens": 50}

    async def _fake_query(*args, **kwargs):
        yield _UsageMsg()
        rm = ResultMessage(
            subtype="success",
            duration_ms=100,
            duration_api_ms=100,
            is_error=False,
            num_turns=1,
            session_id="x",
            total_cost_usd=0.01,
            result="ok",
        )
        yield rm

    monkeypatch.setattr(dream, "query", _fake_query)

    ent = dream._resolve_entity("alex")
    assert ent is not None
    res = asyncio.run(dream.dream_entity(ent, max_prompt_chars=0))
    assert res.skipped is None, f"unexpected skip: {res.skipped} ({res.sdk_result_text!r})"

    # Both substrate files were stamped
    fm1, _ = dream._parse_frontmatter(p1.read_text())
    fm2, _ = dream._parse_frontmatter(p2.read_text())
    assert fm1.get("last_dreamed_at"), f"p1 not stamped: {fm1}"
    assert fm2.get("last_dreamed_at"), f"p2 not stamped: {fm2}"


def test_dream_entity_skips_stamp_on_daily_digest(
    vault: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """daily/<date>.md is NOT stamped (mtime would churn on every dream)."""
    import asyncio
    import dream
    from claude_agent_sdk import ResultMessage

    _write_entity_page(vault, "people", "alex")
    today = datetime.now(timezone.utc).date().isoformat()
    digest = _write_substrate(vault, f"daily/{today}.md", "alex appeared today.\n")

    class _UsageMsg:
        usage = {"input_tokens": 10, "output_tokens": 10}

    async def _fake_query(*args, **kwargs):
        yield _UsageMsg()
        yield ResultMessage(
            subtype="success", duration_ms=10, duration_api_ms=10,
            is_error=False, num_turns=1, session_id="x",
            total_cost_usd=0.01, result="ok",
        )

    monkeypatch.setattr(dream, "query", _fake_query)
    ent = dream._resolve_entity("alex")
    assert ent is not None
    asyncio.run(dream.dream_entity(ent, max_prompt_chars=0))

    fm, _ = dream._parse_frontmatter(digest.read_text())
    assert "last_dreamed_at" not in fm, "daily digest must not be stamped"
