# Ad-hoc: daily/ als per-source rollup + per-day digest

**Status:** ad-hoc execution, multi-phase. Not slotted into M005 (closed) or M006 (deferred — substrate-extension-cluster pitch unstarted). Operator approved direct implementation on 2026-05-15.

**Source of pitch:** conversation 2026-05-15 — operator: "daily darf weiterhin ein 'append-only' capture bleiben aber dann pro intake source getrennt (eine file) PLUS eine weitere summary pro tag die nicht so uebertrieben lang ist und das wichtigste des tages aus allen bereichen zeigt."

## Why ad-hoc again

- M005 is done, no active milestone. Starting M006 would normally route through office-hours → plan-milestone → slice. Operator explicitly skipped that path.
- The pattern is proven: Health Phase 1 shipped via `AD-HOC-health-phase-1-PLAN.md` and the operator considers it the working model for "large enough to need a plan, small enough to skip the milestone wrapper."
- Multi-phase scope (~3-5d total) means this plan acts as the cross-session bridge — phases can be picked up across compacts without re-pitching.

## Target structure

```
daily/
├── 2026-05-14.md              ← per-day digest (~200-500 words, distilled by Claude SDK)
└── 2026-05-14/                ← per-source append-only captures
    ├── sessions.md            ← Claude Code sessions (was the old daily/<date>.md content)
    ├── health.md              ← Oura: sleep_hours / readiness / HRV / steps (one block per run)
    ├── meetings.md            ← gmeet + jamie cross-link entries (one line per meeting)
    ├── voice.md               ← voice intake (one line per voice-note as it lands)
    └── email.md               ← email delta-summary (one block per delta-run)
```

## Decisions locked

| Decision | Choice | Rationale |
|---|---|---|
| Per-source vs all-in-one daily file | per-source subfolder (`daily/<date>/<source>.md`) | One writer per file → no write-contention. Operator's exact request. |
| Append-only semantics | yes, per-source files are append-only OR section-replace (some are streaming, some are one-shot-per-run) | health = one-shot-per-run replace; voice = append per intake; sessions = append per session-end |
| Root digest format | one curated md file at `daily/<date>.md` | Operator's "wichtigstes aus allen Bereichen". Replaces the over-long session-only daily |
| Digest generator | Claude Agent SDK (existing compile-stage) | Per `feedback_no_silent_provider_fallback` — compile = Claude SDK only, never Ollama. New `prompts/compile_daily_digest.md`. |
| Digest length cap | ~200-500 words operator-tunable | Operator complained current dailies are "uebertrieben lang" — explicit length budget in prompt |
| Digest trigger | end-of-day or on-demand via `wiki daily-digest [date]` | Not every collector-run regenerates the digest; that's wasteful + churns the file. Cron / piggyback for "yesterday's digest" the morning after. |
| Migration of existing daily/<date>.md | one-shot script `wiki migrate-daily`; existing content → `daily/<date>/sessions.md` | Operator runs once per vault. Idempotent (skip if `<date>/` subfolder already exists). |
| `daily/` is still mostly Layer-2 (capture) | yes for the subfolder; root digest IS Layer-3 (distillation) | Layer split is honest: subfolder = raw captures (per-source append-only), root = compiled artefact. AGENTS.md schema clarifies. |

## Phases

**Phase 1 — Foundation (this conversation).**
1. `scripts/core/daily_capture.py` — helper module with `append(date, source, content)`, `replace_section(date, source, content)`, `ensure_subfolder(date)`. fcntl-locked on the (date, source) tuple.
2. `tests/test_daily_capture.py` — TDD: append-creates-file, replace-overwrites, lock-prevents-concurrent-corruption, idempotent-folder-creation.
3. Migration script `scripts/migrate_daily_to_rollup.py` (one-shot, idempotent) — for each `daily/YYYY-MM-DD.md` in operator's vault: copy to `daily/YYYY-MM-DD/sessions.md`, leave original in place during transition phase (cleanup later, after digest pass is verified).

Phase 1 acceptance:
- `uv run pytest tests/test_daily_capture.py` green.
- Manual migration run on lxw vault produces `daily/<date>/sessions.md` for every existing daily, originals untouched.
- No collector / hook / compile.py changes yet — pure infrastructure.

**Phase 2 — Wire collectors + session-hook (next session).**
- session-end hook: write target `daily/<date>.md` → `daily/<date>/sessions.md` (append per session).
- health-collector: at end of run, `daily_capture.replace_section(today, 'health', formatted_block)`.
- voice-collector: per intake, `daily_capture.append(intake_date, 'voice', '- ' + slug + ' · ' + first_words)`.
- gmeet + jamie: per meeting, `daily_capture.append(meeting_date, 'meetings', '- [<source>] ' + title + ' → ' + raw_path)`.
- email-collector: per delta-run, `daily_capture.replace_section(today, 'email', delta_summary)`.

Phase 2 acceptance:
- Each collector writes into its own `daily/<date>/<source>.md` file when run.
- Session-hook still writes session captures, now to subfolder file.

**Phase 3 — Daily digest pass (next or third session).**
- New `prompts/compile_daily_digest.md` — input: all `daily/<date>/*.md` files for one date; output: ≤500-word digest in `daily/<date>.md`.
- `wiki daily-digest [date]` CLI subcommand.
- Piggyback: `daily_digest_yesterday` (runs morning after, regenerates yesterday's digest).

Phase 3 acceptance:
- `wiki daily-digest 2026-05-14` produces a sensible digest from the subfolder.
- Length stays under 500 words across 10+ sample dates.

**Phase 4 — Polish (last session or backlog).**
- Lint check `check_daily_consistency`: subfolder exists ↔ root digest exists.
- AGENTS.md schema update — daily/ description rewritten for the new shape.
- README + concept.md + setup-* docs updated.
- Old root `daily/<date>.md` files cleanup (after Phase 3 proves the new ones are sufficient).
- excalidraw diagrams updated.

## Files (Phase 1 only)

In-scope this conversation:
- `scripts/core/daily_capture.py` (new)
- `tests/test_daily_capture.py` (new)
- `scripts/migrate_daily_to_rollup.py` (new — operator-invoked, not auto)

Phase 2+ files explicitly NOT touched in Phase 1:
- `scripts/collectors/health.py`, `scripts/collectors/voice.py`, `scripts/collectors/jamie.py`, `scripts/collectors/gmeet.py`, `scripts/collectors/email_collector.py`
- session-end hook scripts
- `prompts/compile_main.md`, new `prompts/compile_daily_digest.md`
- `scripts/lint.py`
- `AGENTS.md`, `README.md`, `docs/PROCESS.md`
- `templates/AGENTS.example.md`

## Verification (Phase 1)

```bash
uv run pytest tests/test_daily_capture.py -v
uv run python scripts/migrate_daily_to_rollup.py --vault "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/lxw" --dry-run
```

Real migration is operator-invoked, not auto-run from this plan.

## Risks

1. **Migration data-loss.** Copy not move on first pass — originals preserved. Idempotent so re-run is safe.
2. **Token-budget exhaustion** in this conversation — Phase 1 is scoped to fit. Phases 2-4 picked up after `/compact` using the resume prompt from this plan.
3. **Collector / hook coordination** across phases — until Phase 2 ships, new dailies still land in old `daily/<date>.md`. The migration script + the eventual hook-switch must be designed to handle the dual-state window.
4. **Digest quality** unproven until Phase 3 — operator's "wichtigstes aus allen Bereichen" is a real prompt-design problem.

## Resume prompt (post-/compact)

```
Letzte Session: daily/ als per-source rollup wird implementiert.
Plan-Doc: .ytstack/AD-HOC-daily-as-rollup-PLAN.md
Phase 1 (foundation: daily_capture helper + tests + migration script):
  [check git log fuer Status — wahrscheinlich committed als feat(daily): ...]
Naechstes: Phase 2 (collectors + session-hook wiring).
```

## Cross-references

- Precedent: `.ytstack/AD-HOC-health-phase-1-PLAN.md` (ad-hoc out-of-milestone pattern that worked)
- DECISIONS: 2026-05-15 "Health collector Phase 1" entry for the ad-hoc-arc-as-mini-milestone framing
- Memory: `feedback_no_silent_provider_fallback` (digest = Claude SDK only)
