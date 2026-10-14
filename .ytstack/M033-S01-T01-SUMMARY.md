---
milestone: M033
slice: S01
task: T01
project: llm-wiki
closed: 2026-10-14T19:40:00+02:00
verification: passed
---

# M033-S01-T01 -- Summary

## Commits

Committed together with this summary under the `M033-S01-T01:` ref — `git log --grep '^M033-S01-T01'`.

## Outcome

`tests/_oracle.py` builds one deterministic fixture vault (four knowledge articles across
types, `index.md`, one raw note and one daily digest newer than a fixed 2026-01-01 "last
compile", three curiosity requests, two inbox files, `.wiki/state|logs|reports|sessions`)
and points every consumer module at it — `menu_context`, `core.health` and `doctor`
constants, HOME / PATH / API-key env, the interpreter prefix, the git revision, TCP
connects (raise), the home-screen wall-clock budget. `tests/test_oracle_payloads.py` runs
the real entry points in-process — `menu_context.main()` (`wiki menu --json`),
`doctor.main()` with `--quick --json`, `cli.render_help()` — normalises what the clock or
the machine would change (digits inside strings → `N`, `last_compile_ago` → `<AGO>`, tmp
paths → `<VAULT>` / `<HOME>` / `<SCRATCH>`, the checkout → `<WIKI>`) and compares to
`tests/golden/oracle/{menu.json,doctor-quick.json,help.txt}`; a mismatch prints the unified
diff and the regeneration command, `--snapshot-update` (new `pytest_addoption` in
`conftest.py`) rewrites the goldens. Two more tests pin the method: the comparer reports a
one-word title change, and missing goldens fail the suite rather than skipping. The goldens
hold seven suggestions with their titles / verbs / argv, the five tools, sixteen quick
doctor checks (titles, verbs, fixes, dispatch args) and the full help catalogue.
`docs/PROCESS.md` §18 lists the oracle among the reliability audits.

## Deviations from plan

- The first full-suite run failed on the oracle itself — correctly: the doctor payload
  listed the `screenshots` piggyback in the full run and not in isolation. Cause: the
  screenshots collector freezes `Path.home() / "Screenshots"` at first import, so its
  `is_configured()` depends on the machine and on which test imported the module first.
  The oracle now imports the collectors package before patching HOME (so no module-level
  constant is born under the scratch home and outlives the test) and pins
  `SCREENSHOTS_DIR` explicitly.
- Pre-existing defect fixed on the way: `test_screenshots_is_piggyback_discovered` asserted
  discovery against the dev Mac's real `~/Screenshots` (green there, red anywhere else and
  red after any earlier test imported the module under another HOME). It now creates and
  patches its own directory. Verified in isolation, in both orders against the oracle, and
  in the full suite.
- `wiki status` stays outside the oracle (bash, M034); the task plan already said so.

## Follow-ups

- Engine quirk for S03 / S05: `scan_screenshots.SCREENSHOTS_DIR` and
  `scan_browser.CHROME_PROFILE` are import-time `Path.home()` constants; `is_configured()`
  should resolve the path at call time (then neither the oracle nor any test needs the
  import-before-patch dance).
- S01-T05 (CI) must keep this file green on Linux; nothing in the goldens is macOS-specific
  by construction, and the machine-dependent inputs are all pinned, so a red CI run here is
  a real finding.
- Any change to the piggyback registry or to an action / check title now shows up as a
  golden diff — regenerate in the same commit, as the test's hint says.

## Verification

Command: `uv run pytest tests/test_oracle_payloads.py -q` (RED: 5 failed, all "golden …
is missing"; after `--snapshot-update`: 5 passed; again without the flag: 5 passed) and
`uv run pytest -q` — passed: **2030 passed, 1 skipped** (2025 + 5). Order checks:
`test_oracle_payloads.py` then `test_screenshots_collector.py` 14 passed, and the reverse
14 passed. The goldens are byte-identical across four fresh runs.
