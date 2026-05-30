# Orphan-check is neutered by materialized `## Backlinks` footers

**Surfaced:** 2026-05-30 (during the O(N²) lint-orphan performance fix).
**Status:** deferred — latent correctness bug, NOT a regression from the perf fix.

## The bug

`lint.check_orphan_pages` decides "orphan" from `count_inbound_links` /
`build_inbound_count_map`, both of which read **full** article content via
`extract_wikilinks` — including the sentinel-managed `## Backlinks` footer that
`features.materialize_backlinks` (default ON) writes into every article.

So if article A links to B, B's auto-generated footer contains `[[A]]`. That
footer link is counted as a real B→A edge → A gets a "free" inbound from every
article it links out to. Net effect: any article participating in *any* link
relationship looks non-orphan. The orphan check is effectively dead while
backlink footers exist.

## Why it wasn't fixed in the perf pass

The 2026-05-30 fix was scoped as **behaviour-preserving** (golden-diff identical
to the old `count_inbound_links`). Excluding footer links *changes* which pages
are flagged (surfaces more orphans), so it's out of scope for a perf fix and was
flagged instead of silently bundled.

## Fix direction

`core.backlinks.build_backlinks_index` already resolves outgoing links while
**excluding** the `BACKLINKS_BEGIN/END` region (via `outgoing_canonical_slugs`).
Point `check_orphan_pages` at a footer-aware inbound map (either reuse
`build_backlinks_index` directly, or have `build_inbound_count_map` take a
`strip_backlinks_region` flag). Then:

- decide expected behaviour: should the in-`index.md` membership still count? (it
  does today, unchanged).
- re-baseline: this will surface a batch of genuine orphans that footers were
  masking — review them before turning the stricter check loose in the
  dashboard, or they'll flood the lint panel.
- the parity oracle (`count_inbound_links`) would then diverge by design; either
  update the oracle to also strip footers, or retire it.

## Verification when done

Golden-diff against a *footer-stripped* reference, plus an eyeball of the newly
surfaced orphans on the real vault (expect a jump from ~0 to a real number).
