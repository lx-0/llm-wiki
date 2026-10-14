# Daily-rollup backfill still emits the legacy voice line (surfaced in M033-S03-T06)

**Status:** candidate; a behaviour change of a one-shot script, decide when the backfill is
next run on an operator vault. Recorded 2026-10-15 (M033-S03-T06).

**Today:** `scripts/backfill_daily_rollup.py::_voice_lines` builds
`- **HH:MM** · <first line> → [[voice-<stem>]]` — the pre-2026-06-13 voice shape with the
in-body wikilink. The live collector (`collectors/voice.py`) dropped that link on
2026-06-13 and records provenance in the rollup file's `sources:` frontmatter instead
(`daily_capture.append_with_source`); `backfill_voice_source_frontmatter.py` migrates
files the old shape produced. So a fresh backfill followed by the voice-source backfill
converges, but the first script writes a shape the second one has to undo.
`tests/test_frontmatter_parity.py` pins the current backfill line.

**Proposal:** the backfill builds its voice line through `daily_capture.rollup_line`
(T06's seam) and writes it with the `sources:` provenance — but `_append_if_absent` writes
into an arbitrary `--vault` root without `daily_capture` (whose `DAILY_DIR` is the engine's
vault), so the fold needs `append_with_source` to take a root, or the backfill to run
inside the vault's engine. Byte-for-byte parity against a vault that already has the
migrated shape is the acceptance test.
