# Architecture scaling — how `knowledge/` survives 2-3 years of substrate growth

A meta-backlog entry. **Not** a single deliverable — it's the sequence of architectural levers we pull as `knowledge/` grows, with the trigger thresholds for each.

The honest thesis: Karpathy's flat-list + LLM-retrieval scales further than people assume, **but only if the index stops being one 5K-line file**. Numeric re-weighting is the lever you build when you have not taken lifecycle-tiering seriously. Order matters.

## The scaling math

- lxw substrate-rate today: ~30-50 new files/week (gmeet + jamie + voice + email + screenshots + YouTube + sessions + calendar).
- compile produces ~1-3 `knowledge/`-updates per substrate-file (mix of creates + appends).
- → **~50-150 `knowledge/`-writes per week** → **5-15K articles in 2-3 years**.
- `knowledge/index.md` is already at the "don't load the full index" threshold today; at 5K rows it is no longer a usable catalog for an agent's working memory.

The retrieval problem and the index problem decouple at scale:

- **Retrieval quality**: Opus 4.7 1M-context can retrieve from 5K articles **if it knows where to look**. Not the bottleneck.
- **Index navigation**: A flat 5K-row catalog itself becomes unloadable. This is the actual bottleneck — and it arrives first.

## The four levers (cheap → expensive, in build order)

### Lever 1 — Subtype-axis split (already a backlog item)

See `.ytstack/backlog/subtype-axis.md`. Split `concepts/` into ~6 meaningful subfolders so the graph view + on-disk layout encode topic structure. No tiering, no scoring. Quality-of-life improvement that buys ~6 months of headroom on visual navigation.

**Trigger:** already overdue — `concepts/` is the largest single folder.

### Lever 2 — MOC-First retrieval (the largest single lever)

The natural entry-point at 5K articles is not `index.md` but: "read the 5 domain MOCs, pick the right one, read **its** linklist." `index.md` collapses from per-article catalog to MOC-of-MOCs (~50 lines, mostly static).

**Caveat — current state:** MOCs in lxw are **fully operator-curated**. The compile prompt knows `type: moc` and writes to `knowledge/MOCs/` if asked, but does **not** actively maintain MOC linklists during normal compile runs. The 5 lxw domain MOCs (`llm-wiki / fleet / openclaw / claude-code / yesterday`) are hand-written and grow stale unless the operator touches them. See memory entry `project_domain_mocs.md` — "not codified into engine command."

So Lever 2 is really two sub-deliverables:

1. **MOC auto-maintenance**: compile-prompt extension — when an article gains/loses a domain-relevant tag, the relevant MOC's linklist gets updated in the same pass. Probably a dedicated `update_moc` operation in `compile_targets[]`, parallel to `append`/`replace`.
2. **MOC-first retrieval contract**: agent-facing convention that `wiki query <topic>` consults MOCs before raw index. `AGENTS.md` documents the contract.

Without auto-maintenance, MOCs are a manual ritual that decays — and Lever 2 cannot carry the navigation load. **This is the bottleneck blocker for the whole scaling plan.**

**Trigger:** when `knowledge/index.md` exceeds ~1500 rows, or operator first reports "I can't find the article on X anymore."

**Lift estimate:** ~3-4 days. ~1 day compile-prompt extension, ~1 day MOC-write idempotency, ~1 day backfill pass to populate MOCs from existing `knowledge/`, ~0.5 day AGENTS.md + `wiki query` plumbing.

### Lever 3 — Lifecycle tiering (active / archive)

Cutoff-based, no numeric scoring:

```
if mtime < 6 months AND last_source_hit < 3 months:
  → knowledge/ (hot)
else:
  → knowledge/_archive/ (cold)
```

Index splits into `index.md` (active) + `index-archive.md` (cold, only read on demand). Dream-Cycle can re-activate archived articles when synthesis surfaces them. Lint-pass and graph-view stay in hot tier only by default.

**Why mtime-based not score-based:** if an article hasn't been touched in 6 months and no new source references it, it **is** cold — that's the signal, not a derived score. Cheaper to compute, no telemetry needed, no threshold-tuning.

**Trigger:** when `knowledge/` (excluding `_archive/`) exceeds ~2000 articles.

**Lift estimate:** ~1-2 days. Add `_archive/` to skip-list for compile/lint/graph, add nightly tier-move script (mtime + git-log proxy).

### Lever 4 — Recursive Dream-Cycle (hierarchical compaction)

Extends `.ytstack/backlog/dream-cycle.md`. Today Dream-Cycle is single-level (weekly synthesis). Recursive variant: weekly → monthly → quarterly → annual. Old raw `daily/` + `raw/notes/` archived once their monthly synthesis lands. Old weekly-synthesis articles archived once their quarterly synthesis lands. Detail compacts upward; the most recent N weeks stay verbatim.

This is the file-system analogue of biological memory consolidation — not parameter-tuning, just hierarchical summarization of the substrate-tree.

**Trigger:** after Lever 3 has been in place ~3-6 months and tier-move volume becomes annoying.

**Lift estimate:** ~2 days extension on top of Dream-Cycle.

### Lever 5 — Numeric weighting + recall-telemetry

The field-consensus 2026 pattern (SCM, FadeMem LML/SML, MaRS Priority-Decay, Letta tiered, OpenClaw 3-phase Dreaming). Per-article `confidence`, `access_count`, `last_accessed`, decay-on-no-recall, reinforcement-on-recall. Requires Obsidian-plugin telemetry or `wiki query` log-mining — neither exists today.

**Likely never needed** if Levers 1-4 land. The honest test: when Lever 4 is in place for ~6 months, is there still a class of articles that "should be archived but isn't" or "should be hot but is being missed"? If yes → Lever 5. If no → don't build it.

**Trigger:** explicit operator pain that the lifecycle-tier-cutoff misses semantic importance.

## What this means for current backlog

| Backlog item | Lever | Status |
|---|---|---|
| `subtype-axis.md` | 1 | exists, no trigger yet |
| **MOC auto-maintenance** (new) | 2 | **not yet a backlog file** — this entry is the rationale |
| **Lifecycle tiering** (new) | 3 | not yet a backlog file |
| `dream-cycle.md` | 4 (single-level) | exists |
| **Recursive dream-cycle** | 4 (hierarchical) | not yet broken out, extension of above |
| Numeric weighting / sleep-consolidation | 5 | maybe never; deferred until Lever 1-4 prove insufficient |

The MOC auto-maintenance work in particular deserves its own backlog file once trigger threshold is reached — at that point split this entry into `moc-auto-maintenance.md` + `lifecycle-tiering.md` + `recursive-dream-cycle.md`.

## The decision this codifies

**Don't preemptively re-engineer for scale.** Don't add numeric weighting because the field talks about it. The flat list works today, will work for the next 12-18 months, and the right architectural moves are tiering + MOC-as-index, not Letta-style memory-store retrofitting.

But: **MOCs do not currently scale because they are 100% manually maintained**. Without auto-maintenance, the largest single scaling lever is unavailable. That gap is the real blocker — recognize it as such instead of papering over with weighting schemes.

## Field-research sources (2026-05-16)

- Awesome AI Memory — `github.com/IAAR-Shanghai/Awesome-AI-Memory`
- SCM (Sleep-Consolidated Memory) — `emergentmind.com/papers/2604.20943`
- Learning to Forget (sleep-inspired consolidation) — `arxiv.org/html/2603.14517v1`
- Language Models Need Sleep — `openreview.net/forum?id=iiZy6xyVVE`
- OpenClaw Dreaming Guide 2026 — 3-phase Light/REM/Deep sleep
- State of AI Agent Memory 2026 (mem0)
- Mem0 vs Letta vs MemGPT 2026 (tokenmix)
- Karpathy LLM Wiki gist + community implementations

## Status

Backlog meta-entry. Not a deliverable. Reference from any future "knowledge/ is getting too big" discussion to anchor the decision-order. Sibling to `gbrain-comparison.md` and `karpathy-comparison.md` in framing (architectural-direction notes, not single-task plans).
