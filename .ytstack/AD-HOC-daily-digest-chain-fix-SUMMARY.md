# Ad-hoc: daily-digest chain repair (path bug · email β · last_run→state) — SUMMARY

**Status: shipped + live-verified in lxw 2026-05-23.** Commits `d268b8a`, `bad03a9`, `e32d466`, `75b4f71`, `119d4c9`, `31dff3a`. All on `origin/main` except `31dff3a` (README doc, local at wrapup).

**Trigger:** operator question — "`wiki compile` zeigt jedes Mal 34 skipped entries, was passiert mit denen?". Tracing the `email-delta` skips surfaced a cascade: (1) email subject-level intake reached no synthesis surface; (2) the `daily-digest` that should consume it had been silently dead for 8 days; (3) deploying the fix exposed that the agent runner dirties the vault checkout.

## Three fixes (causally chained)

### B — daily-digest path bug (`d268b8a`)
`daily_digest_runner.py:73` resolved the wiki CLI at `WIKI_DIR.parent / "wiki"` (vault root) instead of `WIKI_DIR / "wiki"` (`.wiki/`). Wrong since file creation (`9ef34b6`); `is_file()` failed → `return 2`. `flush.py` spawns piggybacks detached (stdout/stderr→DEVNULL) and records `status:"spawned"` on `Popen` success, so the failure was invisible for 8 days — the 2026-05-15 digests came from a one-time manual backfill. Fix: `WIKI_DIR.parent` → `WIKI_DIR` (matches `menu.py:69`, `core/health.py:352`+`:668`).

### A — email subject-level signal in `daily/email.md` (β) (`e32d466` + test-fix `75b4f71`)
The per-account rollup carried only count + a dangling wikilink to the never-compiled delta. Now `_email_rollup_block` appends top-N senders by volume + a sample of recent subjects (deterministic in the collector). `prompts/agents/daily-digest.md` Email section: "single line" → extract correspondents + themes. Knobs `limits.daily_email_top_senders` (5) / `daily_email_sample_subjects` (12), `0` disables; config.py + config.example.yaml + migrate_config_keys.py same commit. Concept-aligned: stays in `daily/`-aggregation, no per-item compile, bodies stay curiosity-on-request.

### last_run → state/ (`119d4c9`)
`agent_task.py:_update_last_run` wrote `last_run:<ts>` into the git-tracked `prompts/agents/<id>.md` on every run, dirtying the vault `.wiki/` checkout and aborting the next `wiki update`. Fix: `_record_last_run` → `state/agent-runs.json` (gitignored); `AgentSpec.last_run` field + `_coerce_last_run` removed; `last_run:` dropped from the 3 prompts that carried it; display reads from state.

## Live test in lxw (deployed vault)
- **8 daily-digest runs → `daily-digest.md` stayed CLEAN** (recurrence closed); `agent-runs.json` gitignored.
- `wiki collect email --incremental` → enriched rollup (`Top senders: billing@yesterday-ai.de (1)` · `Recent subjects: Subscription renewal reminder…`); digest lifted "subscription renewal from `billing@yesterday-ai.de`" — correspondent + theme, not "1 new".
- Digest gap `05-16…05-23` fully backfilled (8 files).

## Docs
PROCESS.md (§2 daily rollup, §13 agent-tasks, Email-Collector section), KNOWLEDGE.md (wiki-CLI-path + silent-piggyback gotchas + runtime-state-never-tracked lesson), README (email mirror no longer "one-liner"), config.example.yaml + migration. DECISIONS: 2 entries (2026-05-23). No architecture diagram (no structural change — bugfix / content-enrichment / internal storage move; steady-state-portrait rule).

## Open / follow-ups
- `31dff3a` (README doc) unpushed at wrapup.
- 4 **pre-existing** `test_dream_sampling.py` time-dependent failures (`last_dreamed_at` date math, `assert 6.62 < 6.0`) — NOT from this arc; investigate separately.
- The `state/` move also pre-empts the same dirtying for `dream-cycle` + `summarize-day` (the other two prompts that had `last_run`).
