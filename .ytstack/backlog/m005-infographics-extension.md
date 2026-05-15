# M005 infographics extension — deferred

`docs/concept.md` (text) and `docs/architecture.excalidraw` / `docs/overview.excalidraw` / `docs/vault-tour.excalidraw` (diagrams) coverage of M005 status — split between done and deferred.

## Done in the M005 wrapup doc-gap pass (2026-05-15)

- `docs/concept.md:94` data-flow diagram — collector list updated (gmeet + voice + health added)
- `docs/concept.md` Personal tasks section — added between Optimization suggestions and Design rationale
- `AGENTS.md` knowledge/ folder description — extended with two-layer shape note + lint enforcement + extraction reference
- `README.md` — collector count bumped 9→10, health added to list, new Personal-task-layer feature bullet
- `docs/overview.excalidraw` — already updated by a parallel session before the wrapup (13 substrate scanners, health in the substrate list, PNG re-rendered)
- `docs/architecture.excalidraw` — already updated by a parallel session before the wrapup (Health collector node added next to Voice/Jamie/Gmeet cluster, PNG re-rendered)

## Deferred (this backlog entry)

1. **`docs/architecture.excalidraw`** — no node visualises the M005 personal-task layer (two-layer pages in `knowledge/people/` + `knowledge/projects/`, Action Items / Open Threads, dashboard pane, Inbox MOC). The diagram has plenty of substrate-collector callouts but the knowledge-side surface is undertold. Add a callout block describing:
   - State + Timeline page anatomy for entity types
   - Obsidian-Tasks-plugin syntax flowing from compile → entity page → dashboard
   - The lifecycle (carry-forward / resolution-demotion / manual-`[x]`)
2. **`docs/vault-tour.excalidraw`** — currently shows `knowledge/projects/` as a flat folder; should annotate that entity pages use the two-layer shape (`## State` + `## Action Items` + `## Open Threads` + `---` + `## Timeline`).

## Why deferred

Excalidraw extension requires coordinate work (where to place the node, how to size, what to connect). Per `feedback_excalidraw_3-pass_render-verify-adapt`, each edit needs the render-verify-adapt loop on the resulting PNG. Doing this safely in a doc-gap-closure pass is more risk than benefit — better to plan as its own small slice with a fresh look at the canvas.

## Lift estimate

- 1 callout-block add to architecture.excalidraw + render + verify: 0.5 day
- 1 annotation to vault-tour.excalidraw + render + verify: 0.25 day
- Total: ~1 day end-to-end

## Ripens when

- Operator hits a "the diagram doesn't show the task layer" moment when explaining the wiki to someone
- A small slice gets free room (M006-S## fixer-upper)
- An LLM-wiki demo/screenshot needs the task layer visible

## Status

Backlog. Not blocking M005 closure or M006 selection.
