---
milestone: M033
slice: S01
task: T04
project: llm-wiki
closed: 2026-10-14T21:50:00+02:00
verification: passed
---

# M033-S01-T04 -- Summary

## Commits

Committed together with this summary under the `M033-S01-T04:` ref — `git log --grep '^M033-S01-T04'`.

## Outcome

`uv run ruff check scripts hooks tests` prints `All checks passed!` and `ruff format --check`
is clean (380 files), with the full suite green (2030 passed / 1 skipped) and the behaviour
oracle's goldens untouched. The 244-finding residue went three ways. Pass A applied ruff's
own unsafe-but-mechanical fixes for 23 codes under a scoped `--select` (110 fixes: unused
unpacked names underscored, `try/except/pass` → `contextlib.suppress`, nested `with` merged,
`list(x)[0]` → `next(iter(x))`, `zip(…, strict=False)` explicit, ternaries, `yield from`,
PEP 695 generics, `capture_output=True`, …), each hunk read. Pass B is the hand work: 23
`subprocess.run(..., check=False)` made explicit (the engine inspects return codes
everywhere; the keyword now says so), E741 `l` renamed, eight rebound loop variables renamed
(`raw_line` → `line`), seven unused locals removed, two `raise … from exc`, two late-bound
closures bound (`frontmatter.update_fields`, the screenshots retrofit — called in the same
iteration, so no live defect, but now immune), two collapsible ifs collapsed, two test names
lowercased, `ZoneInfo` and `Path` un-aliased. Config: `N806` joined the ignore list
(function-local constants named like constants on purpose) and `RUF012` is ignored under
`tests/**` (fakes declare class-level fixture data). Nine `# noqa` with a reason on the line:
SIM115 ×4 (a lock-file handle whose lifetime is the lock), N801 ×3 (`errors.swallow` mirrors
`contextlib.suppress`; test fakes named after config attributes), N818 ×2 (an escape and a
sentinel are not errors), PLW0603 (warn-once flag), N803 (`N` = sample size).

## Deviations from plan

- **Pass A changed behaviour once, and the suite caught it:** SIM118 rewrote
  `for key in mbox.keys()` to `for key in mbox` in the Thunderbird reader — but
  `mailbox.Mailbox` iterates *messages*, `.keys()` iterates keys, so every lookup failed and
  three adapter tests went red. Restored with `# noqa: SIM118` and the reason; the other
  unsafe rewrites were reviewed for the same duck-typing trap (`.get`, `.items()`,
  `next(iter())`) and hold.
- **Two real defects fixed as defects:** `tests/test_sdk_helpers.py` had two "tests" whose
  body was a bare comparison — they never asserted anything (B015); they assert now. The
  rest of B/F findings were leftovers, not bugs.
- `PLW1510` was listed as autofixable in the plan; ruff 0.16 offers no fix for it, so the
  23 `check=False` were hand edits.
- One follow-on from pass A: ruff inserted `import contextlib` after `menu.py`'s
  console-setup bootstrap (E402); moved into the top import block by hand.
- No RED test: config + mechanical edits; the gates were the suite, the oracle and ruff
  after each pass.

## Follow-ups

- T05 wires ruff into pre-commit and CI so the policy stays green; E402 per-file ignores
  retire with S02's bootstrap removal.
- KNOWLEDGE (same commit): the SIM118 / `mailbox` trap as the canonical example of why
  "unsafe" fixes are reviewed per hunk against a type the rule assumes.

## Verification

Command: `uv run ruff check scripts hooks tests && uv run ruff format --check scripts hooks
tests && uv run pytest -q` — passed: `All checks passed!`, `380 files already formatted`,
**2030 passed, 1 skipped**. Every remaining `# noqa` names a code (RUF100 is enabled and
silent). 87 files changed, +239 / −232.
