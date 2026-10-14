---
milestone: M033
slice: S03
task: T06
project: llm-wiki
closed: 2026-10-15T01:25:00+02:00
verification: passed
---

# M033-S03-T06 -- Summary

## Commits

`cc7bfec` — the fold (helpers, eleven sites, the pins and guards, three test fixes).
Planning commit `62dd055`. This summary, the slice-plan flip and STATE follow under the
same ref (`git log --grep '^M033-S03-T06'`).

## Outcome

One timed rollup line, one ellipsis, one swallowed append. The premise was re-measured
first: the shared helpers the task line asks for already existed — `collectors/base.scan_inbox`
/ `archive_to_zone` / `append_rollup` are the M022 two-zone harness, and the three
`_scan_inbox` were one-line suffix bindings over it (now inlined: `scan_inbox(inbox,
ACCEPTED_SUFFIXES)` at the call sites). What the three `_append_daily_rollup` still copied
was the *skeleton* of a timed line — `date_iso` + `HH:MM` from `captured_at`, the first
line of the text, the 80-char cut — and by mechanism the copies were more than three: the
`[:77].rstrip() + "…"` rule had five homes (voice, capture, pictures, the daily-rollup
backfill, `core/capture_index._capture_gist`), and the swallowed `daily_capture.append`
was hand-typed again in `jamie`, `gmeet`, `health` (×2), `email_collector` and — unguarded —
in `wispr` (`append_with_source`), the idiom `append_rollup` exists for.

Now: `core.utils.ellipsize(text, limit=80)` is the cut's one home;
`daily_capture.rollup_line(captured_at, text, *, prefix, suffix, empty) -> (date_iso,
line)` builds `- **HH:MM** · ` + prefix + first line + suffix, and lives with the rollup
substrate (where `append` / `append_with_source` / the sentinel blocks live). The three
collectors keep a three-line shape owner each (voice: provenance via `source_ref`;
captures: the id in front, the link behind; pictures: the archive name behind,
`(no description)` when empty); every collector rollup — the three, jamie, gmeet, health,
email, wispr — goes through `base.append_rollup`. Parity on fixtures (`/tmp/t06-parity.py`,
before on `62dd055` / after on `cc7bfec`): the three rollup files are byte-identical,
including the `sources:` frontmatter of `voice.md` and the 77-char cuts.

Recorded differences (none on the fixtures): a multi-line picture scene description now
contributes its first line (the whole string, newlines included, used to land in a
one-liner — a broken list item); gmeet's `_meeting_title` and email's rollup block are built
outside the guard, like the other collectors' lines (the guard covers the append); a wispr
rollup failure no longer aborts the run — it is logged and the meeting is marked, the
harness contract. `templates/` carries no rollup shape — nothing to resync.

Guards (`tests/test_rollup_line.py`): under `scripts/collectors/` a `daily_capture.append(`
/ `append_with_source(` call lives only in `base.py` (six offenders at HEAD, measured with
`git grep` before the fold); `[:77]` lives only in `core/utils.py` (five at HEAD). Plus
`ellipsize` / `rollup_line` unit tests and the three byte-exact shape pins.

## Deviations from plan

- wispr was a sixth hand-typed append the plan's grep missed (`append_with_source(` does
  not match `append\(`); folded, with the behaviour change above recorded.
- The email fake-reader tests passed only because their CONFIG stub had no `limits` and the
  rollup raised inside the swallowed try — the rollup never ran in those tests. The stub
  gained the two knobs; the rollup now actually lands in the test sink.
- The guards' RED was observed as the predicate on HEAD via `git grep` (the test module
  could not import before the helpers existed, so the guard functions never ran RED on their
  own); the test asserts the same predicate.
- The voice audio test and the wispr fixture addressed symbols the fold removed
  (`voice._scan_inbox`, `wispr.daily_capture`) — repointed to the seam.

## Follow-ups

- `backfill_daily_rollup._voice_lines` still emits the pre-2026-06-13 voice shape with the
  in-body link (pinned by `tests/test_frontmatter_parity.py`); aligning the backfill with
  the live collector is a behaviour change for a later arc.
- The remaining per-collector line grammars (health bits, meetings `- **jamie** · …`) are
  distinct by design — not copies.

## Verification

Plan command 1 → targeted set `94 passed`; `uv run pytest -q` → **2116 passed, 1 skipped**
(+10: the new file); `ruff check` → `All checks passed!`; `ruff format --check scripts hooks
tests` → clean (two of the task's files formatted by explicit path). Plan command 2 (the
grep) → empty. Plan command 3 → `PARITY IDENTICAL`. CI: `62dd055` green; `cc7bfec`
recorded in STATE.
