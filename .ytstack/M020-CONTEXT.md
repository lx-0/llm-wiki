---
milestone: M020
title: Backlinks footer
size: S
status: done
date: 2026-05-17
pitch: OFFICE-HOURS-backlinks-footer.md
---

# M020 — Backlinks footer

## Goal

Every `knowledge/<article>.md` carries a sentinel-managed `## Backlinks` footer listing its incoming wikilinks. The footer is materialized by a corpus-wide pass at the end of `wiki compile`, idempotent, and opt-out via `features.materialize_backlinks`.

## Exit criteria

1. `scripts/core/backlinks.py` exposes `build_backlinks_index(knowledge_dir) -> dict[str, list[str]]` and `write_backlinks_footer(article_path, incoming_slugs) -> bool`.
2. `compile.py` runs `run_backlinks_pass(KNOWLEDGE_DIR)` after the per-source loop, gated by `CONFIG.features.materialize_backlinks` (default `True`).
3. Sentinel pair `<!-- backlinks:begin -->` / `<!-- backlinks:end -->` is the contract. Pre/post-sentinel content survives across runs.
4. Idempotent: second compile-pass on an unchanged corpus produces zero file mutations.
5. Migration `migrate_config_keys.py` injects `features.materialize_backlinks: true` into operator configs that lack it.
6. `skills/use-llm-wiki/SKILL.md` Read-tier section documents the footer.
7. Tests: extractor, footer-writer, corpus-pass orchestrator. All green.
8. Live-vault probe: pass produces sensible footers on a sample article from the lxw vault (read-only mirror); no operator-prose loss.

## Out of scope

- Axis-aware `wiki search` / `wiki recent` (deferred — `.ytstack/backlog/search-tools.md`).
- Anchor-aware backlinks (`[[slug#heading]]` collapses to `slug` for this milestone).
- `## Related Concepts` derivative block (future axis on same hook).

## Pre-existing primitives

- `scripts/core/utils.py:134 extract_wikilinks(content) -> list[str]` (basic, doesn't handle pipe-alias or anchors — extend or wrap).
- `scripts/core/paths.py KNOWLEDGE_DIR`.
- Sentinel-region precedent in `scripts/collectors/calendar_collector.py:130` (`_split_operator_prose`).

## Risks

- **Compile fan-out**: every compile run touches every article that gained an incoming link. Bounded by O(corpus) reads + writes (~1239 files today). Idempotency guard ensures no churn when no links change. Acceptable.
- **`wiki correct apply` interaction**: agentic vault-wide rename pass uses `Write/Edit` on `knowledge/` files. Empirically grepped `scripts/facts/correct.py`, `scripts/facts/correct_apply.py`, and `prompts/correct_apply*` 2026-05-17 — **zero** references to backlinks or the sentinel. Outcome: if the agent rewrites a file wholesale, the footer may be stripped; next `wiki compile` regenerates it idempotently. Footer is recoverable, not load-bearing data. Acceptable failure mode.
