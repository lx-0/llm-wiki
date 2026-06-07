---
milestone: M027
project: llm-wiki
created: 2026-06-07T12:21:47+0200
size: L
---

# M027 -- Context

## Goal

The wiki learns from the operator's watched local + NAS folders: a body-blind
index feeds curiosity requests that read selected files in-place (answer-only,
no raw copy), and the dream-cycle folds the derived facts into `knowledge/`
over time -- so "what do you know about my X" draws on real file troves, not
just the narrative layer.

Source pitch (validated + CEO-reviewed): `OFFICE-HOURS-watched-folder-curiosity.md`.

## Exit criteria

1. Metadata index is **unmasked** (filenames, folder structure, size/mtime/type)
   -- the agent sees all of it; no sanitization. Content is NEVER in the index.
2. **The human-approval walk is the content/cloud gate**: real file content is
   loaded + processed only after per-request operator accept in
   `curiosity/cli.py:_walk`; the walk card states "file X will be loaded and
   sent to <backend> to answer Y" (informed consent). (Optional `sensitivity:`
   tag on a resulting fact -- nice-to-have, not blocking.)
3. Answer-landing contract pinned + implemented (where the backend's distilled
   answer goes -- re-distill vs. direct-knowledge-write both fight existing
   contracts). Technical decision, not a PII gate.
4. `personal.watched_folders` (local + smb) lands via `config.py` +
   `config.example.yaml` + migration (same commit); periodic body-blind index
   written to `raw/index/<root>.md` for >=1 local and >=1 NAS root.
5. Producer emits `folder-deep-scan` with a verifiable file-exists anchor;
   `curiosity/cli.py:_dispatch` + new `curiosity/backends/folder.py` read named
   files in-place (out-of-sandbox for CloudStorage/NAS) and persist
   **answer-only** -- no raw body in the vault, verified on a real trove.
6. Dream/compile folds >=1 derived fact from a folder-scan into a `knowledge/`
   article, live on lxw; a "what do you know about my <trove-topic>" query
   returns a fact that came from the folder, not the narrative layer.
7. Staleness invalidation (carry source mtime) + failure/quarantine path
   (SMB timeout / file-gone) covered by tests.

## Size

L -- see `M027-ROADMAP.md` for slice breakdown. 6 slices. Earlier framing
required front-loading "three irreversible gates"; superseded 2026-06-07 (see
Decisions) -- the human-approval walk is the content gate, so S01 slimmed to
config + answer-landing and the index can be built freely.

## Decisions locked in discuss phase

- 2026-06-07: HOLD SCOPE, full breadth in one milestone (index +
  curiosity-folder-backend + dream synthesis + NAS + scheduler). Operator chose
  full breadth over the sequenced/local-first boundary; concern raised once at
  CEO mode-selection and overridden. (CEO review block in the pitch.)
- 2026-06-07: P2 contract -- indexed files are read transiently in-place,
  answer-only; **no raw body copy enters the vault**. The index + request
  artifacts are metadata under `raw/` (not bodies). This is the structural PII
  control for bodies.
- 2026-06-07: Split-provider, like email -- producer = Ollama (gap detection),
  backend = Claude SDK (content extraction). No cross-provider fallback.
- 2026-06-07 (SUPERSEDES the "3 gates" framing -- see DECISIONS 2026-06-07):
  **The human-approval walk is the content/cloud gate.** Metadata index is
  unmasked (the agent should see filenames/structure -- that's the triage
  signal); content is loaded + processed only after per-request operator accept
  in `_walk`. No upfront PII-sanitization gate. Filename-masking dropped;
  derived-facts policy demoted to an optional `sensitivity:` tag.
- 2026-06-07: **Backend provider is a swappable seam** -- Claude SDK now, a
  local LLM/agent is the long-term target (then content never leaves the
  machine). Design the backend behind a provider seam; not hard-coupled to
  Claude, not a silent fallback.

## Open questions

(Resolve before/during slicing; close as decisions land above.)

- **Q1 (blocking) Answer-landing target:** (a) curiosity-answer artifact
  re-distilled by compile (but compile distills *raw* sources -> double-distill
  risk), (b) agent writes derived fact directly to entity/fact page (collides
  with 3-layer agent-scope rule for `knowledge/` writes), (c) `daily/` rollup
  the dream-cycle folds in. Must be pinned before the backend is built.
- ~~**Q2 Filename-PII rule**~~ -- CLOSED 2026-06-07: dropped. Metadata index is
  unmasked; the human-approval walk gates content, not the index.
- **Q3 (non-blocking) Derived-facts sensitivity tag:** optional `sensitivity:`
  frontmatter on a persisted fact. Nice-to-have, not a gate (human approved the
  read). Decide during S05 if wanted.
- **Q9 Backend provider seam:** how to abstract the agentic read+answer so a
  local LLM/agent can replace Claude SDK later (config-selected provider; same
  request/answer contract). Shapes S04.
- **Q4 Index form + size caps:** one MD digest per root (single consumer);
  depth/top-N caps that stay prompt-injectable at 1000s of files. Minimum index
  = whatever lets the producer name a real file; richer views deferred.
- **Q5 Out-of-sandbox reader architecture:** TCC wall hits the backend read of
  CloudStorage/NAS (not just the index build). Confirm LaunchAgent reader emits
  answer artifacts the in-session loop consumes; plain-local can stay in-session.
- **Q6 Trigger / frequency:** weekly piggyback vs system-scheduler
  (`system-level-scheduler.md`); how the producer gets the index digest
  in-context during compile vs dream.
- **Q7 Cost control:** per-request confidence/index-triage gate (mirror email's
  `folder_confidence`); producer triages off a weak filename signal -> expect
  worse precision than email.
- **Q8 Producer file-selection granularity:** exact files vs subtree the backend
  narrows.

## Dependencies / reuse

- Reuse: dispatch seam (`curiosity/cli.py:_dispatch`), producer prompt-scaffold,
  email-backend `list_pending`/walk UX, compile/dream synthesis,
  `make_path_scope_hook`, `system-level-scheduler.md` (SMB/scheduler),
  `nas-ingest.md` (SMB mechanics).
- Adjacent backlog: `operator-financial-operational-fact-layer.md` (one consumer
  instance + sensitivity-policy seed), `nas-ingest.md`, `system-level-scheduler.md`,
  `curiosity-topic-as-search-query.md`, `curiosity-dashboard.md`.
- Constraint: `feedback_macos_tcc_cloudstorage` (CloudStorage/NAS unreadable from
  Claude-Code subprocess), config-knob migration rule, `feedback_no_silent_provider_fallback`.
