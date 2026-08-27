# Audit: study_run_due piggyback wiring on lxw

The `study_run_due` piggyback is **enabled on the lxw vault**
(`piggybacks.study_run_due.enabled: true`, `cooldown_hours: 6`,
`max_per_run: null`) but the engine default is `enabled: false`. So
lxw is the first install actually running the piggyback in
production.

## What needs verifying

1. **Does it actually fire?** Inspect
   `<lxw>/.wiki/state/piggyback-state.json` for a `study-run-due`
   `last_run:` timestamp. If absent: the piggyback is registered but
   `_build_piggyback_tasks` may not pick it up because of a missing
   wiring step (the `PIGGYBACK_TASKS` static dict in `flush.py` lists
   the command template; verify the entry exists for `study_run_due`).
2. **Does its `is_due(now)` honour the manifest's `schedule:`
   field?** `manifest.yaml` says `schedule: daily`; the piggyback runs
   `study.py piggyback`, which is supposed to walk every study + skip
   the ones whose `schedule:` says "not due yet". Confirm by checking
   `state.json` of `longitudinal-baseline` — `last_run_at` should
   tick forward roughly daily.
3. **Race with the operator running `wiki study run` manually.** The
   per-study `fcntl.flock` on `state/study-<id>.lock` should serialise
   them. Verify the lock file exists in `state/` and that two
   concurrent fires don't both grab it.
4. **`max_per_run: null` semantics.** Most piggyback configs pin
   `max_per_run` to an int. Null may be a missing-key fallthrough or
   an explicit "no cap" sentinel; check `_build_piggyback_tasks` reads
   it correctly. If it's None-handled by accident, the piggyback
   could under-fire silently.

## How to audit

```bash
# 1. Piggyback fired recently?
cat ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/lxw/.wiki/state/piggyback-state.json | jq '."study-run-due"'

# 2. Study state ticks daily?
cat ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/lxw/reports/studies/longitudinal-baseline/state.json | jq '.last_run_at, .run_count'

# 3. Runs dir has one entry per day since 2026-05-17?
ls ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/lxw/reports/studies/longitudinal-baseline/runs/ | sort

# 4. Logs surface anything?
grep -i "study_run_due\|study-run-due\|study\.py piggyback" \
  ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/lxw/.wiki/logs/flush.log | tail -20
```

If all four checks pass → the piggyback works as designed, no action
needed. If any fail → investigate before the 2026-05-24 week-1 review
(otherwise the review reads stale data because the daily cadence
silently broke).

## Size

XS — 30 minutes. Audit only; if everything works the deliverable is
"verified, no fix needed". Open the matching PR with fix only if
something's broken.

## Ripens when

Now. The piggyback has had ~2 days to fire since manifest creation
(2026-05-17). By 2026-05-19 there should be ≥2 daily runs in the
runs/ dir from the piggyback alone (independent of operator manual
runs). If there are zero piggyback-attributable runs by then, the
wiring is broken and needs a fix before week-1 review.

## Status

**BACKLOGGED** — 2026-05-17. Run between 2026-05-19 and 2026-05-23 so
the week-1 review (2026-05-24) has clean data.
