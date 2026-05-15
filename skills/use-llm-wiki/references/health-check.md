# Vault health check — full flow

Read-only snapshot of an LLM-wiki vault's pipeline + knowledge state. No
mutations, no fixes. The operator decides what to act on.

## Fast path

Run the bundled renderer from the vault root:

```sh
uv run --project .wiki python .wiki/scripts/health.py --vault .
```

Surface the script's stdout verbatim, then add **one** sentence of plain-language
diagnosis at the bottom (e.g. "Healthy ingestion, sparse graph, run nearly
done."). Don't paraphrase the dashboard — it's already formatted.

If the script fails (missing engine, ANSI-unsafe terminal, broken state file),
fall through to the manual flow below.

## What the dashboard answers

1. **What's in the wiki?** — counts per knowledge subdir and raw-source backlog
2. **Is the pipeline running?** — last flush, last compile, piggyback cadence, error patterns
3. **Is the graph dense enough?** — concept-to-connection ratio vs. reference range
4. **Where's the friction?** — orphans, stale state, silent failures

## Standard layout assumption

```text
<vault>/
├── knowledge/{concepts,connections,projects,people,qa}/
├── raw/{memories,articles,notes,…}/
├── daily/
├── inbox/, Clippings/  (optional)
└── .wiki/
    ├── scripts/
    ├── reports/ or <vault>/reports/
    ├── state/, logs/, sessions/   (location varies; check both)
    └── config.yaml
```

Missing optional directory → treat as zero, never error.

## Manual fallback flow (if `health.py` is unavailable)

### Step 1 — knowledge inventory

Count files per knowledge subdir:

```text
concepts: <N>
connections: <N>
projects: <N>
people: <N>
qa: <N>
```

### Step 2 — raw-source inventory

Count markdown sources under `raw/`, `daily/`, plus optional `inbox/`,
`Clippings/`. Report per folder + total.

### Step 3 — compile backlog

Read `.wiki/scripts/state/state.json` (or `.wiki/state/state.json` — check both).
Count `len(state["ingested"])`. Compute:

```text
backlog = total_markdown_sources - ingested_count
```

Report `ingested / total / backlog` and `state["total_cost"]`.

### Step 4 — pipeline cadence

- **Latest daily note** (`ls -t daily/ | head -1`) and gaps in the last 14 days
- **Last flush** — read `.wiki/scripts/state/last-flush.json`
- **Latest piggyback runs** — `piggyback-state.json`, list each task with `last_run` + `status`
- **Latest review report** — newest file in `reports/` or `.wiki/reports/`
- **Compile gate** — current hour vs. `COMPILE_AFTER_HOUR`; flag if gated

### Step 5 — graph density

Ratio: `connections / concepts`. Reference working-system range **0.04–0.07**
(15–25 inline links per concept).

- ratio > 0.20 → too dense, flag
- ratio < 0.04 → too sparse, point at `.ytstack/backlog/connection-quality.md`

Bonus: `grep -L "\[\[" knowledge/concepts/*.md` to count link-less concepts.
If >5% of concepts have zero wikilinks → compile prompt is producing isolated
atoms (Mode E).

### Step 6 — silent-failure scan

Tail last 50 lines of `.wiki/scripts/logs/flush.log`. Grep for `ERROR`,
`WARNING`, `failed`, `traceback`. Surface anything from the last 48 hours.

### Step 7 — output

Markdown report matching the steps. Tables where naturally tabular. One
sentence of diagnosis at the end. End with a single optional next-action offer,
or nothing if everything is green.

## Rules

- **Read-only.** Never write state files, never trigger compile, never run a piggyback.
- **Live data, not memory.** Always read current state files; never argue from
  cached numbers from earlier in the session.
- **Path resilience.** State/logs/sessions/reports are mid-migration — check
  both old (`scripts/state/`, `<vault>/reports/`) and new (`.wiki/state/`,
  `.wiki/reports/`) locations.
- **Don't interpret thresholds as bugs.** Surface the number, name the failure
  mode, point at the backlog item that owns the fix. Don't propose code changes.
- **Tight.** >40 lines of report = bug. Tables beat paragraphs.

## Example output (graphical)

```text
╔════════════════════════════════════════════════════════════╗
║  WIKI HEALTH  ·  2026-05-02 13:34                          ║
╚════════════════════════════════════════════════════════════╝

╭─ KNOWLEDGE ────────────────────────────────── 400 articles  ╮
│ concepts     ████████████████████████   314                │
│ connections  ████░░░░░░░░░░░░░░░░░░░░    48                │
│ projects     ██░░░░░░░░░░░░░░░░░░░░░░    29                │
│ people       █░░░░░░░░░░░░░░░░░░░░░░░     9                │
╰────────────────────────────────────────────────────────────╯

╭─ RAW SOURCES ─────────────────────────────────── 441 total  ╮
│ memories     ████████████████████████   386  87.5%         │
│ notes        ██░░░░░░░░░░░░░░░░░░░░░░    33   7.5%         │
│ daily        █░░░░░░░░░░░░░░░░░░░░░░░    19   4.3%         │
╰────────────────────────────────────────────────────────────╯

╭─ COMPILE BACKLOG ───────────────────────────────────────────╮
│ ingested  ███████░░░░░░░░░░░░░░░░░░░  26.3%   116/441      │
│ backlog: 325 files open · cost $5.52 cumulative            │
╰────────────────────────────────────────────────────────────╯

╭─ GRAPH DENSITY ─────────────────────────────────────────────╮
│ links/concept  █████░░░░░░░░░░░░░   7.5  target 15-25      │
│ orphans        ✓ 0 concepts without [[wikilinks]]          │
│ c:cn ratio      6.5 : 1  (314c / 48cn)                     │
╰────────────────────────────────────────────────────────────╯

╭─ PIPELINE CADENCE ──────────────────────────────────────────╮
│ compile gate     ● gated (hour=13<18)                      │
│ latest daily     2026-05-02.md                             │
│ latest review    wiki-review-2026-05-02.md                 │
│ daily activity   █████████▁████  (last 14d)                │
╰────────────────────────────────────────────────────────────╯
```

In a TTY the bars are colored (green=healthy, yellow=warn, red=problem,
cyan=neutral progress, gray=empty). ANSI is auto-stripped on non-TTY output.
