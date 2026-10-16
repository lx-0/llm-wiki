---
milestone: M034
slice: S06
task: T03
project: llm-wiki
closed: 2026-10-16T06:05:00+02:00
verification: passed
---

# M034-S06-T03 -- Summary

## Commits

- `f24ee59` -- M034-S06-T03: the collector registry is a lazy name → module table — importing the package imports no collector (0.07 → 0.014 s), get_collector(name) imports only its module, all_collectors() keeps the table order; --list still imports every collector for the desktop's configured, exit criterion 6 amended with the measurement

The task was planned in `e882f14`, T02's summary commit.

## Outcome

The collector registry is a table, `collectors.MODULES` (SPEC name → module, in reporting
order).
- **The package import** imports no collector: 0.014 s, from 0.07 s.
- **`get_collector(name)`** imports that collector's module alone; its `@register` runs then.
- **`all_collectors()`** imports them all in table order (0.066 s for 14). It sits behind
  `wiki collect --list` and piggyback discovery.
- **A module that registers a different name** than its table row raises.

`tests/test_collector_registry.py` holds this in a child interpreter: nothing loaded on
package import, only `collectors.scan_tabs` for `get_collector('tabs')`, nothing for an
unknown name. It also checks a table row for every `@register` module, and the order.

## Deviations from plan

- **Exit criterion 6 is amended, not met to the letter.** "`wiki collect --list` imports no
  collector module" would need each collector's `is_configured()` moved into a light layer,
  because the desktop reads `configured` from `collect --list --json`. That is two homes for
  one judgment across 14 modules, for ~50 ms. Measured first, the premise (0.25 s per
  verb) had become 0.07 s, and 0.067 s of that was `collectors.base` + `core.config`. The
  decision and the measurement are in DECISIONS and M034-CONTEXT.
- **The backlog item is marked shipped for collectors.** `preprocessors/` and `producers/`
  keep the eager shape.

## Follow-ups

- **T04:** `wiki collect <name> -- <flags>` passes flags to `main(argv)` for screenshots,
  browser, tabs and youtube.
  - The three by-path entry scripts go; their reason (runpy's double import) is gone with
    the table.
  - PROCESS.md's 11 bare `uv run --project .wiki` lines become `wiki` commands, including
    `wiki refresh-dashboards [--dry-run]`.

## Verification

Commands:
- `uv run --frozen pytest tests/test_collector_registry.py -q`: RED first (5 failed while the
  package imported every collector), then 5 passed.
- `uv run --frozen pytest -q -p no:cacheprovider`: 2668 passed, 1 skipped. That includes
  every collector test, `collect --list --json`'s seam, and the payload goldens.
- `bash /tmp/ci-gates.sh`: clean, after it caught the new test's formatting before the push.
- CI on `f24ee59`: both runs green (`ci` 38841838083, `secrets-scan` 38841838061).
