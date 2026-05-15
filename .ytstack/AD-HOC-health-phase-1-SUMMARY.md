# Ad-hoc: Health collector Phase 1 — Oura only — SUMMARY

**Status: shipped 2026-05-15.** Three commits, full 90-day backfill running against the operator's lxw vault.

**Plan:** `.ytstack/AD-HOC-health-phase-1-PLAN.md`.

## Commits

| SHA | What |
|---|---|
| `c7aaef1` | docs(adhoc): plan-doc — locked scope + decisions before any code |
| `1fd1044` | feat(collectors): Health Phase 1 — Oura Ring daily biometrics (7 files, 866 LOC, 15 adapter tests) |
| `241ad4a` | docs(env): Oura PAT slot in `.env.example` template |
| `9a7f585` | fix(health): pull sleep metrics from `/sleep`, not `/daily_sleep` (live-probe-driven schema correction) |

## What landed

- New collector `scripts/collectors/health.py`, registered, account-loop, incremental-watermarked.
- New adapter `scripts/adapters/health/oura.py` — 4 endpoint pulls (daily_sleep, daily_readiness, daily_activity, sleep), pure parsers, retry/auth/pagination.
- `Limits.oura_request_timeout_s` (30s), `Limits.oura_max_backfill_days` (90) in `scripts/core/config.py`.
- `config.example.yaml`: commented-out `health.oura` block under the account-examples section.
- `templates/.claude/.env.example`: Oura section documenting `OURA_<ACCOUNT>_PAT` pattern.
- Tests: 20 adapter unit tests (TDD RED → GREEN, then schema-correction RED → GREEN).
- Live in production at `<lxw>/.wiki/config.yaml` with the `default` account holding the operator's Oura PAT.

## Live verification

Final field-coverage after the `9a7f585` fix, against the operator's real 90-day window:

| Field | Coverage | Source endpoint |
|---|---|---|
| `sleep_score` | 75/90 (83.3%) | `/daily_sleep` |
| `readiness_score` | 75/90 (83.3%) | `/daily_readiness` |
| `sleep_hours` | 77/90 (85.6%) | `/sleep` (longest session per day) |
| `hrv_overnight` | 77/90 (85.6%) | `/sleep` (`average_hrv`) |
| `resting_hr` | 77/90 (85.6%) | `/sleep` (`lowest_heart_rate` w/ fallback to `average_heart_rate`) |
| `steps` | 90/90 (100.0%) | `/daily_activity` |

Distribution makes physiological sense:
- **75 full-data days** — ring worn, sleep session recorded, scores computed.
- **13 steps-only days** — ring not worn but phone tracked steps.
- **2 metrics-no-scores days** — sleep session recorded after Oura's daily score computation window; expected edge case.

## What I'd do differently

- **Probe-first on undocumented schemas.** I trusted the public Oura docs (and my training-set memory of them) without verifying. The first commit shipped with a parser that returned 0% on three fields. A 30-second `curl` against the live endpoint before TDD-ing the parser would have caught this — and the second commit `9a7f585` is exactly that workflow. Lesson logged to `.ytstack/KNOWLEDGE.md`.
- **The TDD-RED phase doesn't catch fixture-truth-mismatch.** The original 15 tests all passed because my fixtures encoded the *wrong* shape; the parser matched the fixtures perfectly while diverging from reality. RED proves the test fails before implementation; it doesn't prove the test exercises the real shape. Live-probe-first is the missing complement.

## Out-of-scope (deferred — backlog)

- **Phase 2 — HealthKit XML drop-folder** for Renpho weight + iPhone steps (operator can backfill quarterly). See `.ytstack/backlog/health-collector.md` Phase 2.
- **Phase 3 — Health Auto Export integration** if quarterly cadence proves insufficient.
- **Weekly trend digest prompt** (`prompts/compile_health_weekly.md`).
- **`wiki health-auth` bootstrap CLI** — defer until a 2nd operator onboards.
- **Engine `.wiki/` sync to vault.** lxw has the fixed adapter via direct `cp`; long-term it should come via `wiki update` once the engine repo is pushed.

## Cross-references

- Plan doc: `.ytstack/AD-HOC-health-phase-1-PLAN.md`
- Backlog (long-form pitch): `.ytstack/backlog/health-collector.md`
- KNOWLEDGE.md: "Live-probe-first for undocumented API schemas"
- Memory: `feedback_live_probe_before_parser` (to be added)
