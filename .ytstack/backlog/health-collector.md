# Health collector — Oura + Apple HealthKit (Renpho et al.) as substrate

**Priority:** P2 — operator explicitly opted in (2026-05-15). Daily biometric substrate is high-density and correlates with attention/output substrates already in the wiki (LLM-transcripts, daily/, GitHub-activity). Currently zero coverage.

**Origin:** 2026-05-15 substrate-landscape conversation. Operator wears an Oura ring (sleep + HRV + readiness + activity) and weighs in on a Renpho scale that syncs to Apple Health (weight + body composition).

## The gap it fills

The wiki has zero physiological context. "Why was March a slow output month?" or "Did the new sleep schedule actually help?" are unanswerable today. Health data lets `entity-pages-state-timeline` correlate work patterns with biometrics, and gives compile.py a numeric backbone alongside prose substrate.

Not a daily journal — a once-per-day rollup is enough. The wiki doesn't need HRV-per-5-minutes; it needs nightly summary metrics keyed by date.

## Source landscape

| Source | Format | Access |
|---|---|---|
| Oura Ring | REST API `cloud.ouraring.com/v2` | Live, Bearer PAT (free at `cloud.ouraring.com/personal-access-tokens`). Daily sleep / readiness / activity / heart-rate / HRV endpoints. Cleanest source. |
| Apple HealthKit (Renpho weight, iPhone steps, Apple Watch) | XML in ZIP export, or 3rd-party auto-export | No macOS API. iOS-only. See HealthKit bridges below. |
| Renpho direct | App-only — no public API | Reachable only **through** HealthKit. Operator already enabled Renpho → Health sync. |

## HealthKit landing options (the hard part)

Apple Health has no Mac-side API. Three viable bridges:

1. **iOS Shortcut + iCloud drop.** Nightly Personal Automation writes JSON to `<vault>/inbox/health/<date>.json`. Pro: native, free. Con: Shortcut auth fragile on some iOS versions.
2. **Health Auto Export app** (paid, ~$5). 3rd-party app pushes Health metrics to iCloud / Dropbox / REST on a schedule. Pro: reliable. Con: paid, 3rd-party dep.
3. **Manual quarterly XML export.** Operator hits Health → profile → Export All, drops `export.zip` into `<vault>/inbox/health-exports/`. Collector parses `export.xml` (multi-MB, stable schema). Pro: native, free, complete history. Con: manual, infrequent.

Phase 1 = Oura-only (clean API). Phase 2 = option 3 (manual quarterly). Options 1+2 deferred.

## Substrate boundary

Telemetry — numeric state over time. Lands in `raw/notes/health/<year>/<date>.md`:

```yaml
---
title: "Health — 2026-05-15"
type: health-rollup
date: 2026-05-15
sources: [oura, healthkit]
weight_kg: 78.4
sleep_hours: 7.2
sleep_score: 84
readiness_score: 79
hrv_overnight: 52
steps: 8412
resting_hr: 54
sensitivity: high
---
```

Numeric fields in frontmatter so query/lint can grep without prose parsing. compile.py doesn't distill per-day files — it pulls weekly rollups into operator entity-page state.

## Phasing

**Phase 1 — Oura only.** PAT in Infisical, daily pull `/v2/usercollection/daily_sleep`, `/daily_readiness`, `/daily_activity`. Watermark on `day` (ISO). One md per day. Lift: 0.5 day.

**Phase 2 — Apple Health quarterly XML.** Operator drops `export.zip` into inbox. Collector unpacks, iter-parses `export.xml`, extracts weight + steps + sleep records for missing dates, merges with Oura on matching dates (Oura wins for sleep; HealthKit fills weight from Renpho). Lift: 1.5 days.

**Phase 3 — Health Auto Export app** (optional). Only if quarterly cadence proves insufficient.

## Anti-slop heuristics

- Days with no data from either source — skip (no empty files).
- Suspicious metrics (HRV=0, sleep=0h, steps>100000) — flag `data_quality: suspect`, keep but don't distill.

## Multi-tenant shape

`personal.accounts.<id>.health` with `kind: health-multi-source`, sub-fields for `oura` (PAT-from-Infisical) and `healthkit` (inbox_dir). Multi-account is real — operator may want partner's data on a shared wiki later, or separate work/personal sets.

## Open questions

- **Privacy.** Biometric data more sensitive than prose. `sensitivity: high` frontmatter; AGENTS.md schema documents. Future share-vault feature filters.
- **Trend extraction.** "Trended down on HRV for 6 nights" — weekly digest pass, not per-day collector.
- **Backfill window.** Oura PAT allows arbitrary ranges. First run: backfill 90 days, configurable via `oura_backfill_days`.
- **Renpho-without-HealthKit.** If operator turns off the sync, weight goes dark silently. Lint `check_health_flat` flags identical weight >7 days.
- **Time-zone.** Oura's `day` = night ending on that date; HealthKit weight = wall-clock event. Oura's `day` is authoritative on merge.

## Touchpoints

- `scripts/collectors/health.py` — orchestrator. Multi-source: pull Oura, merge HealthKit drop-folder, write per-day file.
- `scripts/adapters/health/oura.py` — REST client.
- `scripts/adapters/health/healthkit_xml.py` — stdlib `xml.etree.ElementTree.iterparse` for multi-MB XML without OOM.
- `state/health-state.json` — per-source `last_day`.
- `prompts/compile_health_weekly.md` — Phase 2+ weekly digest.

## Lift estimate

- Phase 1 (Oura only): **0.5 day** — cheapest "new substrate" win in the backlog.
- Phase 2 (HealthKit XML merge): **1.5 days**.

## Risks

1. HealthKit XML schema drift — test parser against actual export.
2. Oura rate limits (5000/day free) — paginate-aware bulk backfill.
3. Renpho sync silently stops — `check_health_flat` lint rule.
4. Time-zone mismatch on merge — Oura `day` authoritative.

## Ripens when

- Operator notices a sleep-vs-output correlation worth tracking explicitly.
- OR `entity-pages-state-timeline.md` lands (operator entity-page wants "physical state" pane).
- OR Phase 1 (0.5 day) is cheap enough to do regardless.

## Status

Backlog, concept-stage. Substrate is already producing daily — only the pull-into-wiki step missing. Phase 1 is the lowest-effort high-yield collector in the current backlog.

## Cross-references

- Multi-tenant policy: `feedback_account_adapters_multi_tenant`.
- Reference: `scripts/collectors/jamie.py`, `scripts/collectors/gmeet.py`.
- Adjacent: `entity-pages-state-timeline.md`.
