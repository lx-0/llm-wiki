---
milestone: M025
slice: S01
task: T02
project: llm-wiki
closed: 2026-05-23T17:40:00+0200
verification: passed
source: post-tool-use-bash-draft
---

# M025-S01-T02 -- Summary

## Commits so far

- `6debfbe` -- feat(M025-S01-T02): operator-expose capture substrate (piggybacks.capture knob + migration + docs) (2026-05-23T17:27:16Z)

## Outcome

The capture substrate is now operator-configurable end-to-end. `config.py`'s
`_default_piggybacks()` carries `"capture": PiggybackTask(cooldown_hours=1)` (no
`max_per_run` — folder-watch parity with voice), and the config migration
(`migrate_config_keys.py` KEY_ADDITIONS `piggybacks` block) writes
`piggybacks.capture: {enabled: true, cooldown_hours: 1}` into existing operator
vaults on next `wiki update` (HARD rule: config change ⇒ migration same commit).
`config.example.yaml` documents both `personal.capture_inbox` (the one-tap
quick-capture inbox) and the `piggybacks.capture` cadence block in the
voice/pictures prose style. The capture substrate is synced into both the seeded
template (`templates/AGENTS.example.md`) and the repo-root `AGENTS.md`:
`raw/captures/capture-<id>.md` in the substrate tree + `daily/<date>/captures.md`
in the per-source-writer list (now "six writers"). `personal.capture_inbox`
itself + the Registry registration shipped in T01; T02 added only the override
knob + docs.

## Deviations from plan

- **Plan file count held exactly (6).** Unlike T01 (which ballooned 4→7), no
  extra files were needed.
- **Corrected a wiring assumption during verification.** The T02 plan said
  `flush.py` "auto-discovers capture via the Registry." That is true but
  incomplete: `piggyback_collectors()` filters on
  `SPEC.piggyback_default AND is_configured()`, so in the engine repo (empty
  config) capture is correctly ABSENT from `PIGGYBACK_TASKS` — identical to
  voice/pictures, which were also absent. The first "real-wiring check" looked
  like a bug (capture missing) but was the empty-inbox gate. Re-verified with
  `personal.capture_inbox` set to a temp dir: capture then appears in
  `PIGGYBACK_TASKS` as `collectors/cli.py capture` (cooldown 1h) and the
  `enabled=False` override removes it. This is why the `piggybacks.capture`
  default entry + migration matter: they are the operator-overridable knob, not
  the discovery mechanism.

## Follow-ups

- **S01 follow-up (deferred, NOT a blocker):** `docs/setup-capture.md` operator
  setup recipe — mirror `docs/setup-voice.md` once the correction loop is
  operator-facing. Out of T02 scope (separate doc genre, not in the slice plan).
- **Next: S01-T03** — `state/capture_index.json` (`capture_id → {source_path,
  created, status: "open"}`), the bridge S02 (forward link) + S03 (supersede)
  both consume.
- Pre-existing, unrelated: 4 failures in `tests/test_dream_sampling.py`
  (time-drift `_write_last_dreamed_at`) — not in this task diff; flag for the
  dream-sampling arc owner.

## Verification

Command: `uv run --project .wiki pytest tests/test_migrate_config_keys.py tests/test_capture_collector.py -q`
-- passed (45 passed: round-trip change-count 63, idempotent, fully-current all
green). YAML parse + config-load sanity green. Real-wiring proof: capture in
`flush.PIGGYBACK_TASKS` when `capture_inbox` set, override `enabled=False`
honored. Committed `6debfbe`.
