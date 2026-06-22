---
name: llm-wiki Desktop App
one-liner: A desktop app for llm-wiki's technical and non-technical users that makes the whole wiki usable without the CLI and shows its health at a glance.
status: PROCEED 2026-06-22 (CEO-review done; framework decided = Electron; wedge-first build; plan-eng-review next)
captured: 2026-06-13
related: [[screenpipe-intake]], [[listener-lifecycle]], [[interactive-cli]], M003 Obsidian dashboard
---

## CEO review 2026-06-22 — PROCEED (mode: SCOPE REDUCTION)

Un-parked because **starting/stopping screenpipe on the fly became urgent**.

- **Premise:** still valid, *strengthened*. The listener-toggle wedge now has
  its own operational pull, independent of the broader GUI vision.
- **Framework:** **DECIDED by operator — Electron, no alternative.** The original
  park-blocker (Electron vs Tauri vs lightweight menubar) is resolved by operator
  call: Obsidian itself is Electron (stack-affinity, proven non-technical
  desktop), and a lighter path was explicitly rejected. Tauri / xbar / rumps are
  closed. Not re-litigated.
- **Scope decision (SCOPE REDUCTION):** the first shippable Electron slice is the
  **listener toggle + read-only health/status window** — NOT the full wiki GUI.
  Capture / query / compile / control surface is the expansion after the MVP
  shell proves out. The cathedral is real but is built nave-first.
- **Honest consequence:** "Electron-only" means the urgent toggle now waits on
  standing up the Electron MVP (slower than the lightweight path that was
  rejected). Mitigation: keep the MVP *tiny* (toggle + status, no write paths) so
  it ships in days; the interim `~/.screenpipe/sp` + watchdog keep the
  operational need covered until it lands.
- **Still open (for plan-eng-review, NOT a blocker to proceed):** how the Electron
  shell drives the existing `wiki` CLI / Python core (IPC / spawn / local HTTP),
  packaging + signing + auto-update, and whether it's its own repo (likely yes).
- **Next:** `plan-eng-review` (concept mode) to lock the Electron↔engine data flow,
  then `init-project` (own repo).

# Office Hours — llm-wiki Desktop App

## How this surfaced

Came out of office-hours on the *screenpipe collector*. The forcing questions
(infra routing: Q2 status-quo, Q4 wedge) surfaced a realer, more pressing
problem than the collector: **the wiki is inaccessible to non-technical
keyusers.** The screenpipe work (listener toggle, health visibility) turned out
to be one concrete instance of a much larger need.

## Demand reality (validated)

- **Named user, real non-use:** ~50 % of keyusers (Sid) don't use the wiki at
  all because the `wiki` CLI is too complex for non-technical users. CLI-tool
  acceptance among non-technical users is structurally low — this is an
  accessibility problem, and accessibility is a first-class product property,
  not a nice-to-have. Not "would be nice" — a keyuser is *not engaging* today.
- **Technical user pain too:** the operator (Alex) wants an always-on,
  at-a-glance overview of wiki state — is everything running, where is it
  stuck, what was captured last. The CLI only answers on demand (`wiki status`);
  there is no ambient health surface.
- **Concrete cost incident:** a Friday-morning meeting wasn't recorded because
  screenpipe's System-Audio stream was a (sleep/wake) zombie and *nothing
  visible flagged it*. A status surface would have caught it pre-meeting.

## Future-fit (Q6) — why this is existential, not cosmetic

Operator's framing, and it's a real mechanism (not a rising-tide argument):
**user acceptance is the justification for continued product development.** If
the wiki stays CLI-only, non-technical keyusers never adopt it → adoption stays
at ~1 technical user → there is no case to keep investing in the engine. Good
UX / accessibility is therefore the gate on the product's own survival: it
converts the engine from "Alex's personal tool" into "the team's wiki," which is
the only version that justifies further engine work. Accessibility makes the
product *more* essential over time, not less.

Stronger still: a single-user wiki isn't just *less used* — it's **qualitatively
worse**. One user = narrow substrate diversity, few persona axes, no cross-user
knowledge, no reconciliation. Multi-user is a **quality driver of the wiki
itself**, not just a reach metric. "Ein llm-wiki das nur von mir genutzt wird,
wird schwer ein wirklich gutes llm-wiki." The desktop app is the accessibility
enabler for the multi-user / company-wiki future — directly upstream of the
`company-brain-federation` concept (Alex ⊕ Sid → company wiki). Adoption and
quality are the same axis here.

## Status quo (Q2)

- Non-technical users: nothing — they don't use the wiki.
- Technical users: run individual `wiki` subcommands (33 of them) from memory;
  there is an interactive `top_menu()` but it only exposes 6 setup actions
  (see `interactive-cli.md`).
- An **Obsidian vault + the M003 dashboard** (8 plugins, charts, capture/run
  buttons) already exist as a partial non-technical surface. **Open question
  for plan-eng-review:** what specifically can't Sid do via Obsidian/M003 that
  forces the CLI? Determines reuse-vs-rebuild (extend Obsidian vs new shell).
  Operator's read: CLI acceptance is the blocker regardless; a dedicated app is
  warranted — but the reuse boundary must be drawn deliberately, not skipped.

## Narrowest wedge (Q4) — recommended

**A read-only health/status window first.** Smallest version that serves BOTH
audiences immediately, with zero write paths:
- Sid sees "is my stuff captured / is the pipeline alive."
- Alex sees "where is it stuck, what ran last, what's pending."
- Includes the listener status (screenpipe running? channels fresh?) — folding
  in the `listener-lifecycle` concern as a first feature.

Ships in days. The full capture / query / control / compile surface is the
expansion AFTER the read-only shell proves the desktop-app direction.

## Architecture

- **Framework: DECIDED — Electron** (operator call 2026-06-22, "no alternative").
  Rationale: Obsidian itself is Electron (stack-affinity, proven non-technical
  desktop). Tauri / lightweight-menubar paths considered and rejected. It is a
  genuine new surface for this Python/CLI/Obsidian project (build toolchain,
  packaging, signing, auto-update, maintenance) — accepted cost.
- **Backend reuse (for plan-eng-review):** the Electron shell drives the existing
  `wiki` CLI / Python core — it must NOT reimplement pipeline logic. Open: the
  bridge mechanism (child-process spawn of `wiki` vs a thin local HTTP/IPC daemon
  the Python core exposes). The CLI/engine stays the source of truth; the app is
  a front-end + a listener-lifecycle controller.
- **Reuse vs rebuild (for plan-eng-review):** the M003 Obsidian dashboard already
  covers some non-technical surface — decide which actions move into the Electron
  app vs stay in Obsidian, so the two don't drift. Not a blocker for the
  toggle+status MVP.

## Relationship to other threads

- **`screenpipe-intake.md`** — the collector stays separate and still
  unvalidated (data-collection mode). NOT folded into this app.
- **`listener-lifecycle.md`** — listener start/stop/status becomes a feature of
  this app's health surface; the hand-built `~/.screenpipe/sp` + watchdog stay
  disposable prototypes.
- **`interactive-cli.md`** — same underlying goal (make wiki actions
  discoverable); the desktop app is the GUI answer, the interactive CLI the
  terminal answer. Decide whether both, or the app supersedes.

## Next step

**UN-PARKED 2026-06-22; CEO-review PROCEED (above).** Framework decided
(Electron). MVP scope reduced to listener-toggle + read-only health window.

1. `plan-eng-review` (concept mode) — lock the Electron↔engine bridge
   (child-process `wiki` spawn vs local HTTP/IPC daemon), packaging/signing/
   auto-update, and the Obsidian/M003 reuse boundary. This is the real remaining
   technical work; it does NOT block the decision to proceed.
2. `init-project` — own repo, separate codebase fronting the engine (not an
   llm-wiki milestone).
