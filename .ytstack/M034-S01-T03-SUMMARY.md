---
milestone: M034
slice: S01
task: T03
project: llm-wiki
closed: 2026-10-15T19:14:00+02:00
verification: passed
---

# M034-S01-T03 -- Summary

## Commits

- `89503ec` -- M034-S01-T03: decided — one hop keeps the handler child, and the llm_wiki rename is dropped (DECISIONS 2026-10-15, two entries; M034-CONTEXT questions 1 and 2 closed)
- `7b63c7c` -- M034-S01-T03: planned — decide open questions 1 and 2 in DECISIONS (one hop: the bootstrap execs the venv's Python into cli.py and the handlers stay python -m children; the llm_wiki rename dropped), each with the evidence counted in the code, and measure the before tree on the scratch vault with the real uv for a dispatched command (collect --list) and a bash wrapper (doctor --quick --json)

## Outcome

DECISIONS has two new 2026-10-15 entries, and M034-CONTEXT lists questions 1 and 2 as locked
decisions.
- **One hop.** The bootstrap execs the venv's Python straight into `cli.py`, with `uv run`
  only when there is no venv yet or `uv.lock` is newer than its last sync. The handlers stay
  `python -m` children.
- **The `llm_wiki` rename is dropped.**

The before number T04 is judged against was measured on the scratch vault (`7b63c7c`, real
`uv` 0.8.13). A poller read `ps` until the command exited:

```
$ collect --list  (exit 0)
  [6249 <- 6248] uv run --quiet --project /tmp/lxw-scratch/.wiki python /tmp/lxw-scratch/.wiki/scripts/cli.py collect --list
    [6256 <- 6249] /tmp/lxw-scratch/.wiki/.venv/bin/python3 /tmp/lxw-scratch/.wiki/scripts/cli.py collect --list
      [6258 <- 6256] /tmp/lxw-scratch/.wiki/.venv/bin/python3 -m collectors.cli --list
  processes seen: 3, most alive at once: 3
$ doctor --quick --json  (exit 0)
  [3530 <- 3529] bash /tmp/lxw-scratch/.wiki/wiki doctor --quick --json
    [3537 <- 3530] uv run --quiet --project /tmp/lxw-scratch/.wiki python /tmp/lxw-scratch/.wiki/scripts/doctor.py --quick --json
      [3538 <- 3537] /tmp/lxw-scratch/.wiki/.venv/bin/python3 /tmp/lxw-scratch/.wiki/scripts/doctor.py --quick --json
  processes seen: 3, most alive at once: 3
```

Timings, n = 15, warm cache. The machine was noisy, so the two series differ:

| | series 1 | series 2 |
| --- | --- | --- |
| `uv run --project <.wiki> python -c pass` | 82 ms | 94 ms |
| `uv run --no-sync …` | — | 79 ms |
| venv python `-c pass` | 25 ms | 32 ms |
| `wiki collect --list` end to end | 343 ms (277–558) | — |

## Deviations from plan

- **The poller needed one fix.** macOS `ps` prints `(python3.12)` when it cannot read a
  process's arguments, which happens while the process exits. The first version took that for
  an `exec` and printed a false second command. It now ignores the parenthesised form once a
  real command line is known.
- **`wiki links` was tried as a longer read-only command.** It runs in ~0.18 s on the
  scratch vault and gives the same three-process tree. `collect --list` stays the recorded
  case.
- **The measurement surfaced a requirement for T04.** `uv run` syncs the venv whenever
  `uv.lock` changed (`--no-sync` is the opt-out), so a pull outside `wiki update` is healed
  on the next call today. A plain exec of the venv's python would lose that. The T04 line in
  the slice plan now requires the hop to fall back to `uv run` when the lock is newer than
  the venv's last sync.
- **The rename touch-set was re-measured.** It is 335 Python files plus 24 others, where
  M034-CONTEXT had estimated ~400.

## Follow-ups

- **T04:**
  - the bootstrap hop with the lock-freshness fallback;
  - a test that `wiki` calls no `uv` while the venv is current, in the oracle's style: a
    recording `uv` shim, seen to fail on today's bash;
  - the tree after, measured with the same poller (`/tmp/m034_proctree.py`; its logic is
    described above, and it is a scratch tool, not committed).
- **T05** routes the bash wrappers (`doctor`, `menu`, `status`, `version`, dream routing)
  through the dispatcher. `doctor` today keeps bash as its parent, because it calls `uv run`
  without an `exec`.

## Verification

All checks passed:
- `grep -n '^## 2026-10-15: One hop\|^## 2026-10-15: The `llm_wiki`' .ytstack/DECISIONS.md`
  finds both entries (lines 2256 and 2315 at the time).
- `python3 /tmp/m034_proctree.py /tmp/lxw-scratch/.wiki/wiki collect --list` prints the tree
  above.
- M034-CONTEXT's open questions keep 3 and 4 open, with 1 and 2 marked decided.
- `git diff --stat` touched `.ytstack/` only.
