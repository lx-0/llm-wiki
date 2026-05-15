# `templates/AGENTS.example.md` scanner-table resync

**Priority:** P3 — informational, not load-bearing for compile pass (compile.py reads `raw/` directly, not via this table). But the table is the operator-orientation surface AND lands in every new vault's `AGENTS.md` via `wiki seed`, so freshly-installed instances start with a stale picture of the engine.

**Origin:** 2026-05-15 Health Phase 1 doc-coverage audit. Stale-table gap surfaced when looking for "where should Health be mentioned in vault-AGENTS?"

## The gap

`templates/AGENTS.example.md` § 5 "Scan (Local Data Sources → `raw/notes/`)" table currently lists 4 scripts with old `scan-*.py` names:

- `scan-email.py` → now `collectors/email_collector.py` (Registry)
- `scan-calendar.py` → now `collectors/scan_calendar.py` (Registry, migrated 2026-05-14)
- `scan-browser.py` → now `collectors/scan_browser.py` (Registry, migrated 2026-05-14)
- `scan-screenshots.py` → now `collectors/scan_screenshots.py` (Registry, migrated 2026-05-14)

**Missing entirely:** `jamie`, `gmeet`, `voice`, `youtube`, `tabs`, `health` — six registry collectors with zero coverage.

Same staleness exists in any vault that installed before the Phase-2-Collector-Migration cutover; lxw's `AGENTS.md` also carries it.

## Why it's currently P3 not higher

- compile.py reads `raw/`-files from disk regardless of what AGENTS.md says — the table is operator-orientation, not prompt-context for the substrate-discovery loop.
- A 2026-05-15 patch (Health Phase 1 doc audit) added a one-row Health entry + a note pointing to `docs/PROCESS.md` § Scanner-Tabelle as the authoritative current list, so freshly-installed vaults at least see the redirect.
- The "right" full resync needs to decide: keep this table at all, OR replace it with a Registry-walk pointer? (`grep '@register' scripts/collectors/*.py` would auto-generate the canonical list.)

## What "done" looks like

Pick one:

**Option A — full hand-rewrite.** Replace all 4 rows with current 10 Registry-discovered collectors, matching the column-shape of `docs/PROCESS.md` § Scanner-Tabelle. Lift: ~30 min.

**Option B — generator + drop the inline table.** Replace § 5 with a one-paragraph pointer:
> Run `wiki collect --list` for the current Registry of substrate-collectors. Each ships its own `raw/<subfolder>/` writer, multi-tenant config under `personal.accounts.<id>.<collector>` where applicable, and an optional piggyback cooldown. The Registry is the source of truth — this AGENTS.md doesn't repeat it because it drifts.

Plus a `wiki collect --list` snapshot block that the operator can regenerate via `wiki seed --force`. Lift: ~1h including the generator.

Recommend **B** — single-source-of-truth principle, prevents this exact incident from recurring.

## Out of scope for this backlog entry

- Other stale sections of `templates/AGENTS.example.md`. There may be more — full audit would be a separate arc.
- lxw's own AGENTS.md migration. Operator decides whether to `wiki update` + re-`seed` or hand-edit.

## Ripens when

- Operator does next vault-onboarding and the stale orientation table costs explanation time.
- OR a future collector ships and the same gap surfaces in audit (currently happens every new collector).
- OR `wiki seed --force` semantics get revisited (memory `feedback_obsidian_config_via_template` is the precedent for template-vs-vault drift).

## Status

Backlog. Health Phase 1 doc audit (2026-05-15) added the Health row + the redirect note; the broader resync of jamie/gmeet/voice/youtube/tabs remains open.
