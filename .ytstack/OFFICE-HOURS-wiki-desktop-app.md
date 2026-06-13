---
name: llm-wiki Desktop App
one-liner: A desktop app for llm-wiki's technical and non-technical users that makes the whole wiki usable without the CLI and shows its health at a glance.
status: PARKED 2026-06-13 (office-hours done; blocked on open architecture questions before plan-ceo-review)
captured: 2026-06-13
related: [[screenpipe-intake]], [[listener-lifecycle]], [[interactive-cli]], M003 Obsidian dashboard
---

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

## Architecture — NOT decided here (plan-eng-review owns this)

- **Framework:** operator proposes **Electron** (Obsidian itself is Electron →
  stack-affinity, proven for non-technical desktop). **Tauri** (Rust + system
  webview, lighter) must be compared, properly researched, not picked from the
  gut. No desktop-app precedent in this Python/CLI/Obsidian project either way —
  it is a genuine new surface (build toolchain, packaging, signing, auto-update,
  maintenance for a small team).
- **Reuse vs rebuild:** extend the existing Obsidian/M003 dashboard vs. a
  standalone app. Hinges on the "what forces Sid to the CLI" answer above.
- **Backend reuse:** whatever the shell, it should drive the existing `wiki`
  CLI / Python core, not reimplement pipeline logic. The CLI stays the engine;
  the app is a front-end.

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

**PARKED 2026-06-13 by operator** — open architecture questions remain (see
"Architecture" above: Electron vs Tauri, reuse Obsidian/M003 vs new app). Listed
in `backlog/PRIORITY.md` (🌱 Medium). Resume below once those are settled.

When unparked: `plan-ceo-review` (concept mode) to stress-test scope + ambition
before any scaffolding — this initiative is big and scope-control is the main risk. Then
optionally `plan-eng-review` (concept mode) for the Electron-vs-Tauri /
reuse-vs-rebuild call, then `init-project` (likely its own project, not an
llm-wiki milestone — the app is a separate codebase fronting the engine).
