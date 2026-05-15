# Ad-hoc: daily/ as per-source rollup + per-day digest — SUMMARY

**Status: shipped 2026-05-15.** All four phases landed in one session.

**Plan:** `.ytstack/AD-HOC-daily-as-rollup-PLAN.md`.

## Commits

| SHA | Phase | What |
|---|---|---|
| `39263ab` | — | docs(adhoc): plan-doc with four phases + decision matrix + resume prompt |
| `4fd4d6c` | 1 | feat(daily): `core/daily_capture.py` + `tests/test_daily_capture.py` (16 tests) + `migrate_daily_to_rollup.py` |
| `0169422` | 2 | feat(daily): session-hook redirect + 5 collectors wired (health/voice/jamie/gmeet/email) |
| `9ef34b6` | 3 | feat(daily): `daily-digest` agent + `daily_digest_runner.py` + `daily_digest_yesterday` piggyback |
| `d3fd092` | 4 | feat(daily): `check_daily_consistency` lint + AGENTS schema + PROCESS doc |

## What shipped

**Subfolder layer** — `daily/<date>/<source>.md`, one writer per file:
- `sessions.md` — session-end hook (`flush_pipeline.append_to_daily` now writes to subfolder)
- `health.md` — Oura per-account aggregate one-liner
- `meetings.md` — gmeet + jamie meeting one-liners
- `voice.md` — voice intake one-liners
- `email.md` — email-delta one-liner per account

All five writers go through `core.daily_capture` (fcntl-flocked, source-validated against `KNOWN_SOURCES`).

**Digest layer** — `daily/<date>.md`, ~500-word distillation:
- Written by `daily-digest` agent (haiku model, capped turns)
- Triggered manually (`wiki agent daily-digest --var date=...`) or via `daily_digest_yesterday` piggyback (24h cooldown)
- Refuses to overwrite if root file has non-digest frontmatter (operator-edit protection)

**Migration** — `scripts/migrate_daily_to_rollup.py --vault <path>`:
- Copies (not moves) existing `daily/<date>.md` → `daily/<date>/sessions.md`
- Idempotent; conflict-detection on content divergence
- Operator runs once per vault; dry-run output verified against lxw (29 dailies found)

**Lint** — `check_daily_consistency`:
- `daily_missing_digest`: subfolder with captures but no root file
- `daily_legacy_flat`: root file without subfolder (pre-rollup state)
- `daily_unknown_source`: file under subfolder not in `KNOWN_SOURCES`
- Today's date skipped on first two (digest legitimately not run yet)

## Tests

290/290 pass. 16 new tests in `tests/test_daily_capture.py`:
- ensure_subfolder idempotency + ISO-date rejection
- append create/append/newline-handling/unknown-source-rejection/path-traversal-rejection/implicit-subfolder
- replace_section create/overwrite/source-independence
- KNOWN_SOURCES contract
- fcntl-flock smoke-test
- today_iso() matches date.today()

## Operator next steps

```bash
# 1. Migrate lxw's existing 29 dailies (dry-run output verified):
cd "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/lxw"
uv run python .wiki/scripts/migrate_daily_to_rollup.py --vault . --dry-run
uv run python .wiki/scripts/migrate_daily_to_rollup.py --vault .  # real

# 2. Generate today's first digest (after at least one collector run lands in
#    the new subfolder structure):
./wiki agent daily-digest --var date=2026-05-15

# 3. Verify lint surfaces remaining flat files:
./wiki lint --structural-only | grep daily_legacy_flat
```

## Open follow-ups

- **Cleanup of legacy flat `daily/<date>.md` files** is operator-paced. The lint check surfaces them; cleanup is "after digest has run on each, delete the legacy file." Could be automated with a script but currently manual.
- **Multi-account health aggregation** — current implementation appends a line per (account, day) which gives N lines for N accounts. Single-account vault (lxw) is fine; multi-account would benefit from a single replace-with-all-accounts pattern. Backlog candidate.
- **Digest prompt iteration** — first version hits ≤500 words but real-world quality unproven until operator dogfoods. Tune `prompts/agents/daily-digest.md` after first 3-5 actual runs.

## Cross-references

- Plan: `.ytstack/AD-HOC-daily-as-rollup-PLAN.md`
- Architecture: `AGENTS.md` § "daily/" + `templates/AGENTS.example.md` § "Layer 2: `daily/`"
- Operator-pitch source: 2026-05-15 conversation "daily darf weiterhin ein 'append-only' capture bleiben aber dann pro intake source getrennt"
- Memory: `feedback_no_silent_provider_fallback` (digest = Claude SDK only, enforced)
- Adjacent ad-hoc precedent: `.ytstack/AD-HOC-health-phase-1-{PLAN,SUMMARY}.md` (the multi-phase pattern that worked)
