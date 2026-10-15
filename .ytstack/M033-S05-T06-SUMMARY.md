---
milestone: M033
slice: S05
task: T06
project: llm-wiki
closed: 2026-10-15T17:53:26+02:00
verification: passed_with_caveats
---

# M033-S05-T06 -- Summary

## Commits

- `1406950` -- M033-S05-T06: backlog reconciled against the code — 80 items re-derived by eight read-only agents, every superseded / stale-premise / premise-shifting verdict refuted by a ninth before filing; 3 moved to rejected/, 77 in the working set (40 open, 37 partial), PRIORITY.md re-cut with an empty coverage check
- `ee690a0` -- M033-S05-T06 (fix): optimize_claude_md stages inside the engine's state and its agent may edit only the staged copy; release 0.7.3
- `59e7335` -- M033-S05-T06 (docs): config.md's IMAP secret row said Gmail needs an App Password for the suggestions' IMAP actions too
- `28fa312` -- M033-S05-T06 (docs): four stale descriptions the backlog audit found, each checked against the code
- `76a0d66` -- M033-S05-T06: release 0.7.2 — CHANGELOG for the two fixes since 0.7.1
- `afd1b79` -- M033-S05-T06 (fix): the reports' clinical substrate reads voice where it lands
- `5474da8` -- M033-S05-T06 (fix): every suggestion file is seen — the agent also writes `.md` (and `.yml`)
- `03fcfb3` -- M033-S05-T06 (fix): calendar rollups are rewritten only from a complete listing; release 0.7.1
- `d916518` -- M033-S05-T06 (fix): the piggyback runner arms its SIGTERM/SIGINT handler before it records `running`
- `79eb961` -- M033-S05-T06 (fix): screenshot sidecars stamp the vision model that ran
- `7c128cb` -- M033-S05-T06 (fix): the curiosity review walk refuses without a terminal instead of crashing
- `2c183db` -- M033-S05-T06 (fix): the by-path doc guard matches a command wrapped across lines
- `12d3dc3` -- M033-S05-T06 (fix): the suggestion pass writes only into raw/suggestions/
- `194c16c` -- M033-S05-T06: planned — milestone close

## Outcome

The backlog's 80 working-set files were re-derived from the code by eight read-only agents.
One refuter agent then attacked every superseded / stale-premise verdict, plus the four
verdicts that shifted an item's premise. It corrected four of them:

- `subtype-axis`: stale premise → superseded;
- `cleanup-followups`: partial → superseded;
- `dashboard-upcoming-events`: partial → open;
- `obsidian-plugin`: its residue.

Nothing had shipped silently. `karpathy-comparison`, `subtype-axis` and `cleanup-followups`
moved to `backlog/rejected/`, and their references in sibling items were repointed. 77 files
remain: 40 open, 37 partial. `PRIORITY.md` is re-cut into Hot / Big rocks / Medium / Low /
the rejected three, with the refuted reasons. The `comm` coverage check prints nothing.
`deslop-arc.md` §6 carries M034's measured starting point: bash 2,679 lines, README 378, the
help table and the menu catalogue still two tables, ty 146 outside `core/`.

The audit turned up defects that no backlog item named. Each was fixed with a test watched
failing first, and released as 0.7.1–0.7.3:

- **Calendar rollups.** The incremental listing rewrote each touched date from its changed
  events alone (one live date 6 → 1). Now every run lists the whole window and rewrites a
  date only from a complete listing. Also fixed: cancelled events, duplicate event ids across
  calendars, the half-read edge date, the cap, and one-account runs. The renderer split into
  `collectors/calendar_render.py`.
- **Suggestion pass.** It wrote anywhere in the vault over third-party mail; it now goes
  through the harness with `WriteScope(raw/suggestions/)`. Real run on scratch: the
  in-scope write landed and the injected instruction was ignored.
- **Invisible suggestions.** Seven `.md` suggestions with nine pending actions were never
  shown; they are now.
- **Reports substrate.** The globs never matched voice; voice is repointed. Sessions are
  measured out at ~434K tokens / 14 days.
- **Desktop Review row.** It crashed on `termios.error`; it now refuses cleanly (exit 2).
- **Screenshot sidecars.** They named `gemma4:e4b` while `qwen2.5vl:7b` ran.
- **Piggyback runner.** A signal arriving in the race window left `status: running` behind.
- **`optimize_claude_md`.** It staged into a folder no vault has and ran with unscoped edits.
- **Doc guard.** Two gaps (wrapped lines, nested packages).
- **Stale docs.** Seven doc / docstring descriptions (the AGENTS HARD rule's mechanism among
  them).

## Deviations from plan

- **Scope grew by the nine fixes and three releases** (0.7.1–0.7.3). The global
  boy-scout rule fixes defects found in scope instead of listing them. Four fixes went out
  without a release entry, which the repo's rule requires, and 0.7.1 caught them up.
- **Status lines stay in PRIORITY.md.** The items' own one-line status at the top was not
  rewritten; PRIORITY.md carries the current state. The exception is
  `architecture-scaling-2028.md`, whose Lever 1 text would have been wrong.
- **One refuter, not two.** It also checked the premise-shifting PARTIAL verdicts, not only
  superseded / stale.
- **The calendar fix had no live end-to-end run.** No calendar token exists outside the live
  vault, which is read-only for engine work. The proof is eight API-faithful run tests plus
  the vault history (vault commit 2869a316). The first live run after `wiki update` is the
  real check.

## Follow-ups

- **Operator, after `wiki update`:**
  - check `raw/notes/calendar/` once the next calendar run has gone through (the dates in the
    window come back whole);
  - for older dates, set `since:` and run one full `wiki collect calendar`;
  - screenpipe capture has stopped again (`db.sqlite` last written 2026-09-24, only the
    watchdog LaunchAgent loaded).
- **Backlog (all filed in PRIORITY.md):**
  - Hot: flush orphan sweep + archive drain, curiosity dedup, recursive session summary
    (trigger fired), hook-path secret redaction (`llm-transcripts-collector`), preflight
    guards incl. the reports runner (ASRS-v1.1 ~835K tokens), orphan check, the index-md
    prompt lines;
  - merge `commit-article-manifest` into `compile-agent-no-filesystem-write`.
- **M034:** next per `deslop-arc.md` §6.

## Verification

Commands:

1. The `comm` coverage check: passed, prints nothing (77 files, 77 listed).
2. `grep -c '^- \[x\] S0' .ytstack/M033-ROADMAP.md`: the roadmap half of the check. It closes
   with the `reassess-roadmap` run that follows this summary and is checked there.

Every code fix ran the full gates at its commit: suite green (2273 passed at the last),
ruff / format / ty clean, CI green on every push through `ee690a0`. Caveat: the calendar fix
is proven by tests and the vault history, not by a live Google run.
