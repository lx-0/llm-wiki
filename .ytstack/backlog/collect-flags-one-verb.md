# `wiki collect <name>` carries the direct-CLI flags (M034 candidate)

**Status:** candidate for M034 (dispatcher / surface diet). Recorded 2026-10-14 (M033-S02-T06).

**Today:** four collectors keep flags only their direct CLI offers — `scan_screenshots`
(`--all`, `--limit N`, `--backfill DAYS`, `--backfill-thumbnails`, `--retrofit-batch-reports`),
`scan_browser` (`--source firefox|chrome|all`), `scan_tabs` (`--backup-dir`), `scan_youtube`
(`--url` / `--inbox` / `--tier` / `--out`). Since the per-module bootstraps went (M033-S02-T04)
those CLIs run through top-level entry scripts: `wiki ingest-youtube` for youtube, and by path
for the other three (`uv run --project .wiki python .wiki/scripts/scan_screenshots.py …`), while
the Registry run is `wiki collect <name>`. Two shapes per collector; `docs/PROCESS.md` carries
both.

**Proposal:** `wiki collect <name> [-- <flags>]` passes the extra arguments to the collector
module's `main(argv)` (today each `main()` reads `sys.argv`; four signatures gain the
parameter), so the operator has one verb, the three by-path entry scripts go, and the docs lose
their second shape. Alternative with less surface: move the flags into `Collector.run(**options)`
and drop the direct `main()`s — S03-sized (seams), not a docs change.

**Cost / benefit:** ~30 lines in `collectors/cli.py` + four signatures + tests; removes three
files and eight documented lines. Decide inside M034 together with the rest of the surface.
