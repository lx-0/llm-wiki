---
milestone: M003
slice: S05
project: llm-wiki
created: 2026-05-03T00:35:00Z
status: planned
task_count: 3
completed_tasks: 0
---

# M003-S05 — Slice Plan

**Goal:** Append-only event history at `.wiki/state/history.jsonl` (one line per compile + flush event), plus 3 time-series Chart.js graphs on Dashboard reading from it: cumulative articles, cumulative LLM cost, and compile throughput per day.

**Out of scope:** Bases browser (S06), MOC layer (done in S04), retroactive backfill of history from existing state.json (history starts when this slice ships).

## Architectural decisions baked in

- **JSONL not JSON.** Append-only file, atomic line writes, no rewrite of existing data, no race-condition between concurrent compile + flush. One line = one event.
- **Two event types: `compile` + `flush`.** Each line: `{ts, type, articles_total, cost_delta, cost_total, ...}`. Charts derive cumulative + delta views from the event stream.
- **No new plugins.** Obsidian-tracker would be the "proper" tool but the S01-T07 chart pattern already uses Chart.js inside DataviewJS. Same pattern for P2 charts: `app.vault.adapter.read("/.wiki/state/history.jsonl")` → JSON.parse per line → Chart.js render. Keeps the "single chart-tech" rule.
- **Defensive read.** Missing/empty/malformed history.jsonl renders an empty chart with "No history yet — run `wiki compile` to populate" placeholder. Never crashes Dashboard.
- **Schema is forward-only.** New event fields can be added; charts ignore unknown fields. Old events (without new field) get sensible defaults.

## Tasks

- [ ] T01 — `scripts/utils.py` gains `append_history(event_type: str, **fields)` that writes one JSON line to `STATE_DIR / "history.jsonl"` with auto-injected `ts: now_iso()` and `type: event_type`. Wire `scripts/compile.py` to call `append_history("compile", articles_total=N, cost_delta=X, cost_total=Y)` after each successful compile. Wire `scripts/flush.py` to call `append_history("flush", session_id=S, daily_file=D)` after `_record_flush`. Add `tests/test_history.py` with 4 tests: append creates file, append appends not overwrites, malformed-line tolerance (read function skips bad lines), event ordering preserved. Done when `uv run pytest tests/test_history.py -v` is green and a real `wiki compile` adds an event line.

- [ ] T02 — `templates/dashboard.md` gains `## 📈 History` section between MOCs and Run with 3 Chart.js graphs in a single dataviewjs block (mirror of the S01-T07 pattern):
  - **Cumulative articles** over time (line chart, x=date, y=articles_total from compile events)
  - **Cumulative LLM cost** over time (line chart, x=date, y=cost_total from compile events)
  - **Compile throughput** per day (bar chart, x=date, y=count of compile events that day)
  All three read `app.vault.adapter.read("/.wiki/state/history.jsonl")`. Theme-aware colors via Obsidian CSS vars (same helper from S01-T07). Done when grep shows the section + 3 chart canvases; manual smoke confirms charts render with data after a few real compiles.

- [ ] T03 — `docs/PROCESS.md` gains `### History-Layer + P2-Charts` subsection inside §12 (after MOC-Layer): event schema, where data lives, how charts read it, how to extend with new event types. Append T03-T05 manual-smoke note to S05-PLAN. Run full pytest suite. Close S05 in roadmap. Done when grep `history.jsonl` in PROCESS.md returns 1+ hits, suite green, ROADMAP shows S05 [x].

## Done when

All 3 tasks marked `[x]`. M003 exit criteria #6 (`state.history.jsonl` append-only) and #7 (3 P2 charts) satisfied.

## Notes

(Fill during execution.)

## Notes (T03, 2026-05-03)

- 70 pytest tests green (4 new in test_history.py from T01).
- Live smoke deferred until lxw `wiki update` lands the new utils.py + compile.py + flush.py changes; first real `wiki compile` after that creates `.wiki/state/history.jsonl` and the Dashboard "📈 History" section starts populating.
- One subtle decision baked in: `cost_delta` is computed against `cost_at_start` snapshot at compile-main entry, NOT against the previous history event. This avoids needing to read history.jsonl during a compile run (cheap + race-free) and matches the "compile-pass-as-unit-of-work" mental model — one event per main() invocation that did real work.
- `compiled_count > 0` guard means dry-runs and no-op compiles don't generate noise events. Pure observability decision; no semantic impact.
