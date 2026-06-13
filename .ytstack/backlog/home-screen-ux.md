# Home-screen UX — the `wiki` "Actionable" list is flat + incomplete

Operator feedback 2026-06-13 (verbatim intent, not quoted): "I don't always know
what I'm supposed to do" looking at the `wiki` home screen, and "not every feature
that has todos seems to register an entry here."

Both observations are correct. The home screen (`menu.py` rendering
`menu_context.build_suggestions()`) has two structural flaws:

## Lever 1 — trigger gap — ✅ SHIPPED 2026-06-13 (commit `5427c87`)

The maintenance queues (dream/lint/curiosity/digest) piled up because piggybacks
only fired from `flush.py` after 18:00, and the operator lives in
`wiki update && wiki compile` during the day. Fixed: `wiki compile` now drains
due piggybacks at run-end (`scheduling.piggybacks_on_compile`, hour-gate
bypassed, cooldown-gated, abort-skipped). The queues now self-drain inside the
operator's loop, so the screen quiets on its own over the following compiles.
See DECISIONS 2026-06-13.

## Lever 2 — the "Actionable" list mixes 4 intent-classes as one flat list

Everything reads as "I should be doing this," but the items are really:
- **Core loop** — `compile` (the one thing only the operator drives).
- **Auto-maintenance, possibly behind** — dream / lint / email-curiosity. Now
  self-draining via lever 1; surfacing their raw backlog counts as "todos" still
  creates false obligation. Frame as *status* ("149 queued, draining
  automatically"), not an imperative.
- **One-time setup** — `gmail-personal` OAuth not bootstrapped.
- **Optional review** — folder-scans, approved suggestions.

Proposal: regroup `build_suggestions()` output into labelled sections — e.g.
"Do" / "Running automatically" / "Optional review" — so cognitive load drops and
the operator can see at a glance what actually needs *them*. Keep priority
ordering within each group. Pure presentation change in `menu.py` +
`menu_context.py`; no behaviour change.

## Lever 3 — probe coverage is a hand-maintained subset, not a registry

`menu_context.py` has ~8 hand-written `probe_*` functions (inbox, compile-changed,
folder-curiosity, email-curiosity, suggestions-approved, dream-overdue,
flush-missing, lint-stale). There is no mechanism that forces "every feature with
pending work registers a suggestion," so adding a feature leaves it silently
absent from the home screen.

Surfaces with real pending work that currently have NO probe:
- per-collector inboxes (voice / pictures / screenshots — only the generic
  `inbox` file-count exists)
- **folder-index staleness** — watched folders changed since last `wiki index`;
  the freshness of the M027 feature is itself invisible
- `extract_takes` backlog, `wiki dedup` candidates, `wiki dream web-research`
  opportunities, study/operator-reports overdue
- OAuth bootstrap for non-gmail accounts (only gmail is wired into a probe)

Proposal: a uniform probe registry (each feature contributes a
`(probe_fn, priority, label, cmd)` via a decorator or a Collector/Producer-style
SPEC) so coverage can't silently drift. Note: a future "due maintenance" probe
can read `core.piggybacks.due_tasks` cheaply (that module has no SDK import) —
the lever-1 extraction already made this possible.

## Sequencing

Lever 2 is a contained presentation refactor (highest felt-relief per LOC).
Lever 3 is a small architectural change (registry) — do it when adding the next
probe so it pays for itself. Neither is urgent now that lever 1 self-drains the
worst pile-ups.
