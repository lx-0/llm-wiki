---
name: Watched-Folder Curiosity
one-liner: "A folder-index + curiosity/dream intake for the operator's own wiki that progressively distills watched local and NAS file troves into knowledge — reading files in-place, persisting only derived answers, never raw copies."
status: DRAFT
mode: Builder (internal engine feature)
generated_by: office-hours
date: 2026-06-07
branch: main
---

# Design: Watched-Folder Curiosity

## CEO review 2026-06-07 — PROCEED · HOLD SCOPE (full breadth, one milestone)

Decision: build the **full system** (index + curiosity-folder-backend + dream
synthesis + NAS + scheduler) as a single milestone. Operator chose full breadth
over the sequenced/local-first boundary. Scope is accepted, not reduced.

HOLD-SCOPE rigor (bulletproofing — these become milestone exit-criteria, NOT
optional):

- **Build-order de-risks the irreversible surface.** Even at full breadth, the 3
  gates ship FIRST, before any broad `raw/index/` write or NAS read:
  1. Filename/path-PII sanitization rule (non-opt-in, every build).
  2. Derived-facts sensitivity policy (`sensitivity:` frontmatter).
  3. Answer-landing contract (re-distill vs. direct-knowledge-write both fight
     existing contracts — pin it before the backend exists).
- **Edge-case coverage required for "bulletproof":** re-index/staleness
  invalidation (carry source mtime), failure/quarantine on the in-place read
  (SMB timeout / file-gone), out-of-sandbox reader for CloudStorage/NAS (TCC
  wall hits the backend, not just the index), per-request cost/confidence gate.
- **Complexity is acknowledged, not cut:** XL milestone (new collector + new
  backend + producer extension + 2 request types + out-of-sandbox reader + SMB
  + scheduler). Tamed via slicing, not scope reduction. Expect 5-7 slices.

Concern was raised once at mode-selection and overridden by operator choice;
executing HOLD SCOPE faithfully from here. The slice plan must front-load the
gates regardless of breadth.

## Problem Statement

The wiki's knowledge of the operator is bounded by what the collectors ingest
(mail, calendar, gmeet, jamie, voice, health, pictures, screenshots, youtube,
browser-tabs). The operator's **local and remote (NAS) file troves** — the
single richest reservoir of who they are — are completely dark to the engine.
An agent answering "what do you know about my X" can only draw on the narrative/
relational layer; the hard material sitting in folders never enters the loop.
The agent doesn't know what it doesn't know, because it has no map of the
territory.

The operator's frame (verbatim): *"es geht darum, dass das wiki möglichst viel
über mich lernt und diese local und remote folder sind wahre schatzkästchen.
der agent weiss doch nicht, was er nicht weiss."* Finance was one example, not
the scope — this is a general capability over any watched trove.

## Demand Evidence

Proven, not hypothetical, and recent. On 2026-06-06 the operator filled out a
Sparkasse Selbstauskunft, **queried `lxw` first, and it contributed almost
nothing to the actual numbers** — every load-bearing value had to be re-derived
by a 3-parallel-agent raw-document sweep over `Private/Documents`,
`Work/Company`, postal-inbox photos + a depot CSV. The narrative layer was
present; the fact layer that lives in the folders was absent. Logged as
`.ytstack/backlog/operator-financial-operational-fact-layer.md`. That sweep is
the status-quo cost, and it recurs every time a folder-resident fact is needed.

This is the demand signal `search-tools.md` lacked when it was deferred
(2026-05-17) as "pre-emptive tooling, no proven pain." The pain is now on
record.

## Status Quo

- No engine path reads local/NAS folders. The operator does ad-hoc Finder/`ls`
  when they personally need something; an agent re-derives via a throwaway
  multi-agent extraction sweep. Nothing is cached, nothing compounds.
- The curiosity loop today is **email-only**: `producer.py` emits exactly
  `type: email-deep-scan`, `cli.py:_dispatch` wires exactly `email_backend`,
  everything else → "Unsupported request type, no backend wired." The
  dispatch seam is already type-based, so it is extensible by design.

## Target & Scope (general, not finance-scoped)

The full system, sliced — the operator explicitly wants all three parts, kept
general across any watched folder:

1. **Folder Index** — periodic (frequency TBD), config-defined local + remote
   folders, body-blind metadata map stored in the vault (`raw/index/…`).
2. **Curiosity folder-backend** — during compile/dream the producer emits
   `folder-deep-scan` requests that name specific files from the index; a
   backend reads those files **in-place, transiently, answer-only** and the
   next pass processes the distilled answer.
3. **Dream/Compile synthesis** — the existing loops fold the derived facts into
   `knowledge/` progressively ("nach und nach"). Curiosity + dream together do
   the enrichment.

## Architecture

### Part 1 — Folder Index (new collector)

- Config: `personal.watched_folders` — list of `{id, kind: local|smb, path|share,
  include/exclude globs, sensitivity hint}`. (Lifted to `config.py` +
  `config.example.yaml` + migration in the same commit, per the project's
  config-knob rule.)
- Build runs **outside the Claude-Code TCC sandbox** (CloudStorage/NAS paths are
  unreadable from a Claude-Code-spawned subprocess — see
  `feedback_macos_tcc_cloudstorage`). → LaunchAgent / system-scheduler
  (`system-level-scheduler.md`); NAS over SMB via `smbprotocol`
  (`nas-ingest.md`).
- Walks each root **body-blind** (no content reads). **Body-blind is NOT
  PII-blind** — filenames and paths routinely carry the exact sensitive facts
  this design surfaces (`Kündigung_Mietvertrag_2026.pdf`, `Renteninformation`,
  `Selbstauskunft`) and are a prompt-injection vector once they enter an LLM
  prompt. So stage 1 needs a **filename/path sanitization + sensitivity rule
  before anything is written to `raw/index/` or fed to the producer** — this is
  a non-opt-in PII surface (every build writes it), distinct from and arguably
  ahead of the derived-facts policy.
- Writes a per-root index into `raw/index/<root-id>.md`. **Minimum viable index
  = whatever lets the producer name a real file**: a depth-capped tree + recent-
  change list. The richer views (top-N biggest, oldest, file-type histogram,
  per-subfolder recency) are human-discovery surface (Approach C's rejected
  premise) — defer until a consumer proves it needs them. Sized as a **digest**,
  not a full tree-dump, so it fits the producer prompt (P3).
- **Re-index / staleness:** the build must be delta-aware (mtime/size diff), and
  a folder-scan answer must carry the source file's mtime so a later change can
  invalidate it. Mirror the 0.1.7 ingest-hash/skip-record discipline; do not
  re-emit unchanged trees. (No watermark story exists yet for this substrate —
  design it, don't inherit email's.)

### Part 2 — Curiosity folder-backend (extends existing loop)

- **Producer** (`curiosity/producer.py`, invoked from `compile.py` and dream):
  alongside `email-deep-scan`, emit `folder-deep-scan`. The producer receives
  the folder-index digest in-context (mirrors the numbered `email_folders`
  listing it already uses) and, for a detected gap, names specific target
  files/subtrees. **The `source_quote` gate does NOT carry over** — a body-blind
  index has no body to quote, so the email loop's load-bearing anti-hallucination
  anchor is gone. Replace it with a **verifiable file-exists anchor**: the named
  path must be present in the current index (the producer cannot invent a file).
  Keep a confidence gate analogous to email's. The producer triages off a weak
  signal (a filename) vs. email's full body → expect lower precision and worse
  cost ratio; the index must carry enough signal to triage well, in tension with
  keeping it small/prompt-injectable.
- **Backend** (`curiosity/backends/folder.py`, new): reads the named files
  **in-place and transiently** (local fs or SMB fetch), runs an agentic pass
  (Claude SDK — content-extraction/reasoning, not deterministic, and compile is
  Claude-only per `feedback_no_silent_provider_fallback`; the **producer stays
  Ollama**, split-provider exactly like email). The agentic read must be
  **path-scoped** to the named files only (`make_path_scope_hook`) with an
  explicit tool allowlist. Output = **distilled answer only**, written as a
  curiosity-answer artifact the next pass consumes. **No raw body copy enters the
  vault** (P2). Needs a failure/quarantine path (SMB timeout, file gone between
  index and read) — email's `MailboxReadError` / watermark-on-failure is the
  template.
- **TCC wall hits the backend too.** The in-place read of CloudStorage/NAS files
  cannot run inside a Claude-Code-spawned subprocess (`feedback_macos_tcc_
  cloudstorage`) — the same wall P4 moves the index build off. So the **file-read
  step must also run out-of-sandbox** (LaunchAgent/system-scheduler), which
  breaks the "just extend the in-session `cli.py:_dispatch`" story for any
  CloudStorage/NAS root. Plain-local paths can stay in-session; CloudStorage/NAS
  need the out-of-process reader. Resolve this split before S2.
- **Dispatch** (`curiosity/cli.py:_dispatch`): add the `folder-deep-scan` branch
  (in-session reader for plain-local roots; hand off to the out-of-sandbox reader
  for CloudStorage/NAS).

### Part 3 — Synthesis (existing loops, extended)

- The distilled answers flow into compile/dream so derived facts land in the
  right `knowledge/` articles (entity pages, fact nodes) with as-of dates,
  progressively.

## Premises (agreed in session unless flagged)

- **P1** — Demand is proven (the Selbstauskunft sweep), milestone-worthy.
- **P2 (the novelty)** — Contract: indexed files are read **transiently
  in-place, answer-only — no raw *body* copy into the vault**. Only distilled
  answers / derived facts persist. This is the structural PII control for
  *bodies* (PII bodies are read, never stored). Different contract from the
  email backend (which dumps `deep-<slug>.md` to `raw/` then distills). Caveat:
  the request artifacts (`raw/requests/`) and the index (`raw/index/`) DO live
  under `raw/` — they're metadata, not bodies; "no raw copy" means no body copy.
- **P3** — Index is body-blind metadata, digested small enough to inject into
  the producer prompt. **Body-blind ≠ PII-blind**: filenames/paths carry
  sensitive facts and are a prompt-injection surface, so the index needs a
  filename-sanitization/sensitivity pass — this is the FIRST PII gate, before
  any derived-facts policy, and it is non-opt-in (every build writes it).
- **P4** — Periodic build runs outside the Claude-Code TCC sandbox (LaunchAgent/
  system-scheduler; NAS via SMB).
- **P5** — Consumers are the existing curiosity + dream loops, extended — no new
  parallel machinery.

## Approaches Considered

### Approach A: Dependency-ordered slices (recommended)
  Summary: S1 Folder Index (local first, then SMB) → S2 Curiosity folder-backend
    (read-in-place, answer-only) wired to producer + dispatch → S3 Dream
    synthesis + generalized sensitivity policy + scheduler hardening.
  Effort: L   Risk: Med
  Pros: Each slice ships a working increment; S1+S2 already give the end-to-end
    loop on local folders; the novel P2 contract is proven early on real files;
    SMB/scheduler cost is deferred to where it's actually needed.
  Cons: Full value (NAS + dream synthesis) only at S3; three subsystems touched
    across the milestone. (Note: "cross-trove" synthesis — reasoning across
    multiple roots at once — is explicitly OUT of this milestone; if wanted it's
    a later milestone, not an undefined S3 rider.)
  Reuses: dispatch seam, producer prompt-scaffold, email-backend list_pending/
    walk UX, compile/dream synthesis.

### Approach B: Capability-parallel tracks
  Summary: Build index, backend, synthesis as parallel tracks, integrate at end.
  Effort: L   Risk: High
  Pros: Faster wall-clock with a milestone team; clean module boundaries.
  Cons: The read-in-place/answer-only contract stays unproven until integration;
    integration risk concentrated at the end; harder to demo an increment.
  Reuses: same as A.

### Approach C: Index-rich first, consumer later
  Summary: Invest in a powerful general index (graph + all views + NAS) before
    any consumer wiring.
  Effort: M (index) then L   Risk: Med
  Pros: Matches the operator's literal "periodisch indexes bauen" mental model;
    immediate discovery surface.
  Cons: Longest exposure to the DECISIONS-2026-05-22 anti-pattern (substrate
    with no consumer = dead weight); front-loads SMB/scheduler before any win;
    over-builds index views the consumer may not need.

## Recommended Approach

**Approach A.** Dependency-ordered slices keep every increment alive and prove
the one genuinely new thing — the in-place/answer-only contract (P2) — on real
files before generalizing to NAS. It honors the operator's own
synthesis-consumer gate (don't ship substrate without a consumer) while still
delivering the full system they asked for.

## Open Questions (for plan-milestone / plan-eng)

1. **Answer-landing contract — BLOCKING, not just open.** Where does the
   distilled answer persist? The naive options both fight existing contracts:
   (a) a curiosity-answer artifact re-distilled by compile — but compile's
   contract is to distill a *raw* source, and a folder-scan answer is *already
   distilled* → double-distill / no-op (`project_distill_dont_cite`); (b) agent
   writes the derived fact directly to an entity/fact page — collides with the
   3-layer agent-scope rule for `knowledge/` writes
   (`feedback_substrate_is_subject_not_instruction`); (c) a `daily/` rollup the
   dream-cycle folds in. You cannot build the backend without pinning this — it
   is as blocking as #2, not a nice-to-have.
2. **Generalized sensitivity policy.** P2 keeps raw PII out structurally, but a
   *derived* fact can still be sensitive. What derived facts may persist, and
   do they get `sensitivity:` frontmatter (as health)? This is the real
   cross-cutting blocker the finance entry flagged — generalize it, decide it
   before S3.
3. **Index form + size.** One MD digest per root (single consumer → single
   format)? What are the depth/top-N caps that keep it prompt-injectable at
   real tree sizes (1000s of files)?
4. **Trigger / frequency.** Weekly piggyback vs system-scheduler; how the
   producer gets the index digest in-context during compile vs dream.
5. **Cost control.** Agentic in-place reads cost per request — what confidence/
   index-triage gates throttle them (mirror email's `folder_confidence`)?
6. **Producer file-selection.** Does the producer name exact files, or a
   subtree the backend then narrows? Index granularity drives this.
7. **Filename-PII sanitization (S1, non-opt-in).** What rule strips/masks
   sensitive filenames before they hit `raw/index/` and the producer prompt?
   This is the first irreversible-PII surface and it applies to every build.
8. **Answer staleness.** A folder-scan answer is only true as of the file's
   mtime. How is it invalidated when the source changes (carry mtime + re-emit
   on diff)? No watermark scheme exists for this substrate yet.
9. **"In-place" + TCC for the backend read.** The CloudStorage/NAS body read
   can't run in the Claude-Code session — confirm the out-of-sandbox reader
   architecture (LaunchAgent reader emits answer artifacts the in-session loop
   then consumes?).

## Dependencies

- `system-level-scheduler.md` (TCC-safe periodic build) — prerequisite for the
  remote/NAS half; local-only S1 can run under existing piggybacks.
- `nas-ingest.md` (SMB scan mechanics) — feeds Part 1's remote half.
- `operator-financial-operational-fact-layer.md` — one consumer instance + the
  sensitivity-policy seed.
- Curiosity-loop internals (`producer.py`, `cli.py`, `backends/`) — extension
  points.

## Distribution

N/A — internal engine feature for the operator's own vault; ships via the
normal engine → commit → push → `wiki update` path.

## The Assignment

Before scaffolding, settle the three decisions that gate the build — none are
mechanics, all shape the architecture:
1. **Filename-PII rule (#7)** — what gets masked before any index lands in
   `raw/`. Non-opt-in, irreversible, fires on every build. Decide first.
2. **Derived-facts sensitivity policy (#2)** — what distilled answers may
   persist, with `sensitivity:` frontmatter.
3. **Answer-landing target (#1)** — where the backend's output goes, given that
   re-distill and direct-knowledge-write both fight existing contracts.

A wrong call on (1) or (2) leaks PII irreversibly; a wrong call on (3) means the
backend can't be built. Mechanics (SMB, scheduler, walk) are known and safe to
defer.

## What I noticed about how you think

- You corrected the frame twice and both times pulled it *up* a level: from
  "agent queries the filesystem" to "the wiki learns what it doesn't know," and
  from "the finance use case" to "schatzkästchen, das war nur ein beispiel."
  You design from the persona-coverage goal down, not from the mechanism up.
- *"der agent weiss doch nicht, was er nicht weiss"* — you located the real gap
  precisely: not retrieval, but discovery of unknown unknowns. The index isn't
  a search tool, it's a map that makes the dark territory legible to the loop.
- *"NICHT als kopie in RAW"* — you arrived at the privacy-preserving contract on
  your own, as an architecture choice, not a compliance afterthought. That's the
  sharpest decision in the design and it fell out of how you think about the
  loop, not out of a PII checklist.
