---
name: vault-health-check
version: 1.0.0
description: |
  Snapshot the operational state of an LLM-wiki vault: knowledge counts, raw-source
  inventory, compile backlog, last review/lint cadence, piggyback task health,
  recent flush-log activity. Diagnoses whether sparseness is data-foundation or
  linking-strategy by computing the link-density ratio against a reference range.
  Read-only; produces a markdown status report, never mutates state.
  Use when: user says "wiki status", "vault status", "wie geht's der wiki",
  "compile backlog", "is the pipeline healthy", "health check".
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

# Vault Health Check

Read-only snapshot of an LLM-wiki vault's pipeline + knowledge state. The output
is a single tight status report — what's there, what's pending, what looks off.
No mutations, no fixes. The user decides what to act on.

## Overview

A wiki built on this engine accumulates state across many surfaces — concept files,
raw source folders, compile state JSON, piggyback timers, flush logs, lint reports.
After a few weeks the operator wants a single command that surfaces the load-bearing
numbers and flags drift. This skill is that command.

It answers four questions:

1. **What's in the wiki?** — counts of compiled articles per type and raw-source backlog
2. **Is the pipeline running?** — last flush, last compile, piggyback cadence, error patterns in logs
3. **Is the graph dense enough?** — concept-to-connection ratio compared against the working-system reference range
4. **Where's the friction?** — orphaned files, stale state, silent failures

## Configuration

This skill assumes the standard layout:

```text
<vault>/
├── knowledge/{concepts,connections,projects,people,qa}/
├── raw/{memories,articles,notes,…}/
├── daily/
├── inbox/, Clippings/  (optional source-adjacent folders)
└── .wiki/
    ├── scripts/                      ← engine code
    ├── reports/ or <vault>/reports/  ← review-wiki, lint output
    ├── state/, logs/, sessions/      ← runtime artefacts (location varies; check both)
    └── config.yaml
```

If a directory is absent, treat it as zero — never error on a missing optional folder.

## Health-Check Flow

### Step 1 — knowledge inventory

Count files per knowledge subdirectory. Report:

```text
concepts: <N>
connections: <N>
projects: <N>
people: <N>
qa: <N>
```

### Step 2 — raw-source inventory

Count markdown sources per folder under `raw/`, plus `daily/`, plus optional
adjacent folders (`inbox/`, `Clippings/`). Report each folder's count, plus a
total markdown source count for backlog math.

### Step 3 — compile backlog

Read `.wiki/scripts/state/state.json` (or wherever `state/` lives — check both
`.wiki/scripts/state/` and `.wiki/state/`). Count `len(state["ingested"])`.
Compute:

```text
backlog = total_markdown_sources - ingested_count
```

Report `ingested / total / backlog`. Read `state["total_cost"]` and report
cumulative compile cost.

### Step 4 — pipeline cadence

Surface:

- **Latest daily note** (`ls -t daily/` head 1) and gaps (any missing days in
  the last 14)
- **Last flush** — read `.wiki/scripts/state/last-flush.json` (or new path),
  format the timestamp
- **Latest piggyback runs** — read `piggyback-state.json`, list each task with
  `last_run` + `status`
- **Latest review report** — newest file in `reports/` or `.wiki/reports/`,
  with the date
- **Compile gate** — current hour vs. `COMPILE_AFTER_HOUR` from config; flag if
  compile is gated right now (`hour < gate`)

### Step 5 — graph density diagnostic

Compute concept-to-connection ratio: `concepts / connections`. Compare against
the **working-system reference range of 0.04–0.07** (i.e. **15–25 inline links
per concept**, equivalent to 0.04–0.07 connection-articles per concept if using
the typed-folder split).

Reference: `.ytstack/backlog/connection-quality.md` synthesises this from the
wider Karpathy/Cole/Matuschak literature.

If the ratio is significantly above 0.20 (i.e. fewer than 5 concepts per
connection article — too dense), or significantly below 0.04 (i.e. more than 25
concepts per connection article — too sparse), call it out. The common case is
sparse: cite the failure modes (Mode B — prompt timidity; Mode C — append-only
drift) and point at the connection-quality backlog item rather than re-deriving.

Bonus diagnostic: run `grep -L "\[\[" knowledge/concepts/*.md` to count concept
files with **zero** wikilinks in their body. If >5 % of concepts are link-less,
the compile prompt is producing isolated atoms — Mode E.

### Step 6 — silent-failure scan

Tail the last 50 lines of `.wiki/scripts/logs/flush.log` (or new path). Grep for
`ERROR`, `WARNING`, `failed`, `traceback`. Surface anything from the **last 48
hours**. Examples to watch for:

- `SessionEnd hook ... failed` — usually a uv/.venv mismatch, mostly harmless
  but flag once
- `Claude extraction failed` — flush retries; if persistent, point at retry-failed-flushes
- piggyback `spawning ... .py` followed by no completion log → silent crash
  (compare timestamp to expected output file)

### Step 7 — output

Markdown report with sections matching the steps. Tables where data is
naturally tabular (counts, piggyback cadence). One sentence of plain-language
diagnosis at the end ("pipeline healthy, drained backlog, graph still sparse —
see connection-quality backlog item"). End with a single optional offer: a
specific next action the operator could take, or nothing if everything is
green.

## Rules

- **Read-only.** Never write to state files, never trigger compile, never run a
  piggyback. The skill reports; the operator decides.
- **Live data, not memory.** Always read the current state files; never rely
  on cached numbers from earlier in a session or from an auto-memory entry —
  state changes constantly while the pipeline runs.
- **Path resilience.** The engine layout is mid-evolution: `state/`, `logs/`,
  `sessions/`, `reports/` are migrating. Check both old (`scripts/state/`,
  `<vault>/reports/`) and new (`.wiki/state/`, `.wiki/reports/`) locations and
  use whichever exists.
- **Don't interpret thresholds as bugs.** A sparse graph is not a bug — it's a
  diagnostic. Surface the number, name the failure mode, point at the backlog
  item that owns the fix. Do not propose code changes from this skill.
- **Be tight.** A health-check report longer than ~40 lines is a bug. Tables
  beat paragraphs. The operator is glancing, not reading.

## Example output shape

```markdown
## Wiki status (2026-05-02)

**Knowledge:**
- 279 concepts · 47 connections · 27 projects · 9 people · 0 qa

**Raw sources:** 386 memories · 8 notes · 3 articles · 1 inbox · 1 Clipping · 19 daily

**Compile backlog:** 116 / 441 ingested → **325 open** (74%). Cumulative cost: $5.52.

**Pipeline:**
| Signal | Stand |
|---|---|
| Latest daily | 2026-05-02 |
| Last flush | 2026-05-02 10:12 |
| Last review | 2026-04-23 (9d ago, weekly cadence — overdue) |
| Last compile gate | hour=12 < 18, currently gated |
| Piggyback last run | 2026-05-01 21:58 (review-wiki spawned but no fresh report → silent failure) |

**Graph density:** ratio 5.94 (concepts/connections) — sparse, working systems
land at ~22. See `.ytstack/backlog/connection-quality.md` for the diagnosis +
5-action roadmap.

**Silent failures last 48h:** 1× (review-wiki spawn 2026-05-01 left no report).

Healthy data ingestion, sparse graph, one silent piggyback to investigate.
```
