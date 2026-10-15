---
name: An overlay cannot carry a removed entry, and --force brings it back unannounced
description: The config overlay (template ⊕ .wiki/custom/<path>) only overrides. A key or array element the operator removed comes back from the template on `wiki seed <path> --force`, and seed's drift advice recommends exactly that `--force`. lxw's graph.json loses its removed color groups this way. Recommendation is a round-trip guard first, a deletion form later if needed.
type: defect
origin: M034-S04-T02 (live-data parity of the seed core)
created: 2026-10-16
---

# An overlay cannot carry a removed entry, and --force brings it back unannounced

## What the code does

A JSON config the engine owns and the operator tunes is derived as
`template ⊕ <vault>/.wiki/custom/<path>`:
- `_apply_overlay`, ported as `core.seed.apply_overlay`, merges element-wise, and an overlay
  `null` keeps the template's value;
- `_compute_overlay`, ported as `core.seed.compute_overlay`, captures the leaves that
  differ.

Neither can express a removal. A key the operator deleted, an array element they removed,
or a setting cleared to `null` all reappear from the template when the file is re-derived.

## Evidence (lxw, read-only, 2026-10-16)

The live `.obsidian/graph.json` has fewer `colorGroups` than the engine template. An overlay
extracted from it gives `template ⊕ overlay`, which differs from the live file in 45 template
leaf paths: the removed groups' `query` / `color.a` / `color.rgb`.

`wiki seed --check` reports the file as drifted, and seed's message advises
`wiki seed .obsidian/graph.json --force`. That command brings the removed groups back.

The other six overlay-managed files round-trip exactly:
- the files without changes: app, core-plugins, dataview, homepage;
- extended-graph, with 12 overrides;
- quickadd, with 73 overrides.

## Recommendation

1. **A round-trip guard, cheap and honest.** Before `--force` re-derives a file that has an
   overlay, compute `apply(template, compute(template, live))`. If it differs from the live
   file, refuse, or ask, and name what the overlay cannot carry: "3 removed array entries in
   colorGroups would come back". `--check` should say the same instead of advising `--force`.
2. **Only if real use needs it: a removal form.** That could be a tombstone value in the
   overlay, or a per-key "replace the whole array" rule for arrays like `colorGroups`. It
   changes the overlay format, so it is a design decision.

This is not part of the S04 port: T02–T04 port today's semantics. The guard fits after T04,
in Python.
