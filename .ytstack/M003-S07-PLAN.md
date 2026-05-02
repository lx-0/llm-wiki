---
milestone: M003
slice: S07
project: llm-wiki
created: 2026-05-02T22:00:00Z
status: planned
task_count: 4
completed_tasks: 0
---

# M003-S07 — Slice Plan

**Goal:** Stop the dashboard cache files (`_dashboard-stats.md`, future `_dashboard-lint.md`) from showing zeros after they have already been populated. Two structural bugs surface together: `wiki seed --force` clobbers live caches with placeholder templates, and `flush.py:refresh_dashboard_stats()` swallows stderr so silent crashes are invisible.

**Trigger:** lxw vault Engine-status block showed all-zeros at 21:43 despite 470 articles + 303 pending compiles + active flushes. Cache file was bytegenau identisch mit `templates/_dashboard-stats.md`. Manual `dashboard_stats.py --dry-run` produced correct numbers — so the script works, the cache just got clobbered.

**Out of scope:** Charts (S01-T07), MOCs (S04), history-driven time-series (S05), Bases (S06). No changes to `dashboard_stats.py` or `dashboard_lint.py` (S02) themselves — both producer scripts are correct; only their callers and the seed flow change.

## Architectural decisions baked in

- **Cache files are producer-only.** `_dashboard-stats.md`, `_dashboard-lint.md` are never seedable artifacts. They're outputs of `dashboard_stats.py` / `dashboard_lint.py`. The producer scripts are responsible for the entire file lifecycle (creation, refresh, format). Removing them from `seed_vault_templates` is the structural fix; placeholder-content guards would be a workaround.
- **First-boot: cache writes itself.** Empty vault on first install → first `wiki flush` writes the cache fresh (no rendering until then is fine; Dashboard transclude shows empty embed, not stale data). For impatient operators, `wiki seed` can additionally trigger a one-shot `dashboard_stats.py` run (S02-T03 already plans this for `wiki seed`/`wiki lint`).
- **Silent failures end here.** Both `flush.py:refresh_dashboard_stats()` and the shell wrapper `wiki:_refresh_dashboard_stats()` currently route stderr to DEVNULL and ignore exit codes. New rule: cache-refresh failures log a warning to `flush.log` (engine-side) or print to stderr (shell-side), exit code is checked.
- **No new health-check command yet.** A future `wiki status` that warns on stale cache (generated_at < last_flush) is good UX, but out of scope here — once silent failures are gone, staleness should not happen.

## Tasks

- [ ] T01 — `lib/seed.sh`: remove `_dashboard-stats.md` from `seed_vault_templates`. Lines 129-134 (the `_seed_file` call for `_dashboard-stats.md`) get deleted. Same treatment pre-emptively for `_dashboard-lint.md` if S02 has already merged it as a seedable; otherwise add a comment near the top of `seed_vault_templates` explaining why cache files (`_dashboard-*.md`) are not seeded. Update `wiki:429` help text to drop "_dashboard-stats.md" from the "Seeds missing files" list. Done when (a) `grep -n _dashboard-stats lib/seed.sh` returns 0 hits, (b) `wiki seed --force` against a vault with a populated `_dashboard-stats.md` leaves the cache untouched (verify mtime + content hash before/after).

- [ ] T02 — `scripts/flush.py:refresh_dashboard_stats()` (lines 272-286): replace `stderr=subprocess.DEVNULL` with `stderr=subprocess.PIPE`, capture the result, and on non-zero exit log `log.warning("dashboard_stats refresh failed (exit=%d): %s", result.returncode, result.stderr.decode()[:500])`. Same for `stdout` if non-empty (debug level). `check=False` stays — refresh failures must never block the flush itself. Done when intentionally breaking `dashboard_stats.py` (e.g. `raise RuntimeError` at top of `main()`) and running `wiki flush` produces a visible WARNING line in `.wiki/logs/flush.log` with the actual error.

- [ ] T03 — `wiki` shell wrapper, `_refresh_dashboard_stats()` at line 248-250: change `2>/dev/null || true` to capture stderr to a tempfile, check exit code, on non-zero `warn "dashboard stats refresh failed: $(cat $tmp)"`. The function still must not abort the parent `cmd_compile` / `cmd_flush` / `cmd_lint` / `cmd_correct` flow (best-effort). Done when same intentional-break test as T02 but invoked via `wiki lint` (which calls _refresh_dashboard_stats from line 320) prints a yellow warning to stderr.

- [ ] T04 — Verification fixture + manual smoke. Add `tests/test_dashboard_stats_cache.py`:
  - Fixture: copy `scripts/`, `templates/`, `lib/` into temp `wiki_root` + create temp vault with 1 raw file, 1 daily file, 1 knowledge article.
  - Test 1: Run `dashboard_stats.py` against fixture, assert cache has non-zero counts in frontmatter.
  - Test 2: With cache populated, invoke `seed_vault_templates "$target" "$wiki_dir" 1` (force=1), assert cache content + frontmatter unchanged afterwards.
  - Test 3: Monkey-patch `dashboard_stats.py` to raise on import, run `flush.py` end-to-end against fixture, assert `flush.log` contains `WARNING.*dashboard_stats refresh failed`.
  - Manual smoke on lxw vault: `wiki seed --force`, then check `_dashboard-stats.md` still has the live counts from earlier in this session (303/1/2351/$7.25/470/19), no placeholder text. Done when `uv run pytest tests/ -k dashboard_stats_cache -q` passes and the manual smoke note is appended below.

## Done when

All 4 tasks marked `[x]` and verified via `ytstack:summarize-task`. Side-effect: M003 exit criterion #2 ("Engine-status callout shows live counts") becomes durable across `wiki seed --force` and silent script crashes — currently it works only on the happy path.

## Notes

(Add observations during slice execution. Findings about how often the cache had silently been stale will be valuable for the README / docs/PROCESS.md.)
