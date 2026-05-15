# Ad-hoc: Health collector Phase 1 — Oura only

**Status:** ad-hoc execution. Not slotted into M005 (current milestone, parallel-session-owned) or M006 (deferred until M005 closes). Operator explicitly approved bypass on 2026-05-15.

**Source of plan:** `.ytstack/backlog/health-collector.md` Phase 1 section (`Oura only`, 0.5d). This file is the de-facto T##-PLAN equivalent for the ad-hoc arc.

## Why ad-hoc

- Parallel session is mid-M005-S05-T04, owns `STATE.md current_milestone`.
- Formally starting M006 in this session would flip `current_milestone` and clash with the parallel session's slice planning.
- Health Phase 1 is small enough (~0.5d, single API, established collector pattern) that the milestone-wrapper overhead would dwarf the work.
- Operator picked "ad-hoc, bypass ytstack-Flow" when offered the three pathways.

## Scope (locked)

In-scope:
- `scripts/collectors/health.py` — new collector, orchestrator pattern from `scripts/collectors/jamie.py` / `scripts/collectors/gmeet.py`.
- `scripts/adapters/health/__init__.py` + `scripts/adapters/health/oura.py` — Oura REST client. Bearer PAT auth. Three daily endpoints: `/v2/usercollection/daily_sleep`, `/daily_readiness`, `/daily_activity`.
- `HealthConfig` dataclass in `scripts/core/config.py`, nested under `personal.accounts.<id>.health` per multi-tenant policy (`feedback_account_adapters_multi_tenant`).
- `config.example.yaml` example block.
- `scripts/collectors/__init__.py` registry wiring.
- State file `state/health-state.json` (auto-created on first run, watermark = `last_day` per account ISO date).
- Tests for the Oura adapter response-parse + watermark advance (TDD where it warrants).

Out-of-scope (Phase 2+, NOT this arc):
- HealthKit XML drop-folder ingest.
- Apple Health / Renpho integration.
- Heart-rate / HRV per-5-min granularity (only daily summary values).
- Weekly digest prompt.
- `wiki health-auth` bootstrap CLI — operator can paste the PAT directly into Infisical or env; bootstrap deferred.

## Files

- `scripts/collectors/health.py` (new)
- `scripts/adapters/health/__init__.py` (new)
- `scripts/adapters/health/oura.py` (new)
- `scripts/collectors/__init__.py` (edit — add `from . import health`)
- `scripts/core/config.py` (edit — add `HealthConfig`, wire into `Personal.accounts[].health`)
- `config.example.yaml` (edit — add commented example block for `personal.accounts.<id>.health`)
- `tests/test_oura_adapter.py` (new) — unit tests for Oura response parse + auth header + watermark advance

Explicitly NOT touched in this arc:
- Anything under `scripts/links/`, `wiki` CLI lateral-link wiring, `LateralLinks` config — those are the parallel session's M005-S05-T04 territory.

## Decisions locked at planning time

| Decision | Choice | Rationale |
|---|---|---|
| Auth | Bearer PAT from env / Infisical ref (`OURA_PAT_<account_id>` or via secret_ref field) | Free, no OAuth, no rotation needed; pattern matches existing Infisical conventions |
| Backfill window | 90 days on first run, configurable via `oura_backfill_days` | Backlog file default; Oura serves arbitrary historical ranges |
| Multi-tenant | From day one — `personal.accounts.<id>.health.oura` with `kind: oura-pat` | Policy: never ship a flat block (`feedback_account_adapters_multi_tenant`) |
| Output shape | One md per date per account in `raw/notes/health/<year>/<date>--<account-id>.md` | Per-account file suffix matches gmeet sibling-scan convention; year subdirs from day 1 |
| Endpoints | daily_sleep + daily_readiness + daily_activity | Three calls per day per account; aggregate into single frontmatter |
| Frontmatter shape | `weight_kg / sleep_hours / sleep_score / readiness_score / hrv_overnight / steps / resting_hr / sensitivity: high` | Phase 1: weight_kg stays empty (HealthKit Phase 2); all Oura fields populate from daily_* endpoints |
| State | `state/health-state.json` with `{accounts: {<id>: {oura: {last_day: "YYYY-MM-DD"}}}}` | Watermark-on-success rule applies (`feedback_watermark_on_failure_fix` precedent) |
| Skip empty days | If all three Oura endpoints return empty for a day → don't write the file | Anti-slop heuristic from backlog file |
| Piggyback | `piggyback_default=True, piggyback_cooldown_hours=24` | Daily data, no need to poll more often |

## Verification

```bash
# Smoke-test the adapter unit tests
cd .wiki && uv run pytest tests/test_oura_adapter.py -v

# Dry-run the collector against a real Oura PAT (operator provides)
cd .wiki && uv run python -m scripts.collectors.health --dry-run --account default

# Real run against test vault (writes to raw/notes/health/<year>/)
cd .wiki && uv run wiki collect health --account default

# Verify file shape
ls raw/notes/health/2026/
head -25 raw/notes/health/2026/2026-05-14--default.md
```

## Acceptance

- Adapter unit tests pass.
- `wiki collect health --account default` against a real Oura PAT produces ≥1 daily file with all Oura frontmatter fields populated (HealthKit fields empty in Phase 1).
- Watermark advances on success, stays put on failure.
- Re-running same window is idempotent (no duplicate files; existing files skipped or replaced based on `mtime` comparison).
- `wiki lint` passes on a sample of generated files.

## Out-of-scope follow-ups (backlog-only, do NOT do)

- HealthKit XML drop-folder ingest — backlog file Phase 2.
- Weekly trend digest — backlog file's `prompts/compile_health_weekly.md` deferred.
- `wiki health-auth` CLI — defer until 2nd operator onboards.
- Migration of legacy flat `personal.health` block — never existed; first-account-named-default per `feedback_default_account_id_reserved`.

## Post-execution

Write a brief `AD-HOC-health-phase-1-SUMMARY.md` next to this file when done. If this arc grows or generalizes into M006, formalize via plan-milestone later — this ad-hoc-PLAN.md is the bridge.
