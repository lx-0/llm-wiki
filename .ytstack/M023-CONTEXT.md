---
milestone: M023
project: llm-wiki
created: 2026-05-19T11:42:36Z
size: M
---

# M023 -- Context

## Goal

All Apple Health data merges into the existing per-day health substrate (`raw/notes/health/`), extending the timeline beyond Oura's 90-day backfill window with weight, steps, workouts, sleep, HR, and other metrics streamed from a 214 MB `Export.xml` drop.

## Exit criteria

- Per-day health files in `raw/notes/health/` contain merged HealthKit fields (weight, steps, workouts, sleep/HR where HealthKit covers a day Oura does not).

## Size

M — see `M023-ROADMAP.md` for slice breakdown.

## Source pitch

`.ytstack/backlog/shipped/health-collector.md` — "Phase 2 — Apple Health quarterly XML". Phase 1 (Oura) shipped 2026-05-15 (`AD-HOC-health-phase-1-SUMMARY.md`).

## Substrate already on disk (lxw, 2026-05-19)

- `~/Library/Mobile Documents/com~apple~CloudDocs/inbox/health-export/Export.xml` — **214 MB**, primary parse target.
- `…/inbox/health-export/export_cda.xml` — 83 MB, CDA-format clinical record. Out of scope for v0 (different schema).
- `…/inbox/health-export/workout-routes/` — GPX per workout. Out of scope for v0 (route geometry, no daily metric).
- `…/inbox/healthkit/2026-05-17*.json` — 4 small files from an iOS-Shortcut test (Phase-3 path). Out of scope; separate substrate option, do not touch.

## Decisions locked in discuss phase

- 2026-05-19: target the **full HealthKit timeline**, not just the gap before Oura's 90-day window — the export covers years and feeds long-tail history (weight back to first Renpho sync, workouts back to first iPhone, etc.).
- 2026-05-19: drop-folder pattern stays (not file-CLI-only) — operator does quarterly exports and forgets which folder; folder-watch with hash-dedup is the user-experience the pitch promised.
- 2026-05-19: `export_cda.xml` and `workout-routes/` are deferred to a follow-up — scope guard.
- 2026-05-19: merge authority on overlap days: **Oura wins for sleep / HRV / readiness / activity scores**; HealthKit fills weight (Renpho), steps (when no Oura ring data), and adds workouts as a new field Oura doesn't carry.

## Open questions

- Where exactly does the inbox live? Pitch said vault-relative (`<vault>/inbox/health-exports/`). Operator's file is at `~/iCloud/inbox/health-export/` (singular, outside vault). Decide during slice S01 — likely a new config key `personal.accounts.<id>.health.healthkit.inbox_dir` defaulting to the iCloud path.
- Watermark / dedup strategy: hash the XML once and short-circuit, or per-record dedup keyed on (type, sourceName, startDate)? Per-record is safer if operator re-exports with overlap; hash is faster. Decide during slice S01.
- Field set for v0: weight, steps, workouts, sleep, HR — do we also pull mindfulness, dietary water, blood oxygen, environmental audio? Decide during slice S01 (probably "yes, anything that maps to a one-line YAML field; skip series-only types").
