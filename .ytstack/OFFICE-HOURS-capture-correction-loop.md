---
name: capture-correction-loop
one-liner: "A correction-link loop for llm-wiki operators that surfaces how the brain read each cryptic quick-capture and lets them overturn a wrong reading by ID — the brain supersedes the old interpretation and re-interprets just that item."
date: 2026-05-23
source-pitch: voice note from Sidney (second engine operator), forwarded 2026-05-22
mode: startup-diagnostic (brownfield feature validation)
status: CEO-reviewed (REDUCTION → B-minus) — ready for plan-milestone
---

## CEO review 2026-05-23 — PROCEED, mode = SCOPE REDUCTION (B-minus)

Decision: build, but cut the surgical patch. Office-hours had already twice-sharpened
the wedge; the only open scope question was the load-bearing "targeted downstream
patch in compile's agent-side-write model" risk (the M018 / `commit_article` class
of re-architecture that already blew up once). REDUCTION eliminates it rather than
mitigating it.

**Dream state (why this wedge is the right one):** the 12-month ideal is a general
"interpretations are correctable by ID + the brain learns operator-specific priors
from corrections" capability. The capture loop is the wedge for that. B-minus's
ID-keyed supersede-marker is the substrate-agnostic primitive that generalizes; the
dropped surgical patch would have been bespoke and *less* on-trajectory. So the
smaller cut is also the more aligned cut.

**v1 must-ship (B-minus):**
1. Thin capture collector — reuse file-drop/voice-style door, assign a **stable
   capture-ID** per capture, write to `raw/` with the ID in frontmatter.
2. Capture-ID provenance — ID survives `raw/` → compiled artifact (extend
   `compiled_from`).
3. Digest section — recent captures keyed by ID → interpretation + the context the
   brain added (extend the existing `daily-digest`).
4. Correction-ingest — a capture line referencing a known ID is a correction;
   writes a **supersede-marker** against that capture's interpretation.
5. compile honours the supersede-marker → regenerates the affected article on the
   **next normal compile cycle** (existing post-pass machinery, no instant patch).

**NOT in v1 (follow-up, do not sneak back in):**
- Targeted instant single-item patch (the dropped surgical primitive) — only if
  async proves too slow in practice.
- Confidence-gated proactive push (alternative C) — after data on correction
  frequency.
- Correction-priors learning (the 12-month cathedral) — after the loop is used.
- Generalizing the back-channel beyond captures to all substrates — trajectory,
  not v1.

**Remaining risk for plan-eng-review / plan-milestone:** item 5's seam — does compile
have a clean "regenerate the article(s) derived from capture-ID X" path, or only
full-corpus / per-source-file compiles? The supersede-marker → affected-article link
is the thing to nail down. If compile is per-source-file, "superseded capture →
re-compile that source" is natural; verify before slicing.

---

# Office Hours — Capture Correction Loop

## The pitch (as received)

Sidney runs a "notes-to-self" habit: a WhatsApp group with only himself where he
dumps everything — article snippets, cryptic one-liners ("Alex Küsschen geben am
Montag"), reminders. One tap to open, get it out of his head. The tool doesn't
matter (WhatsApp / Notion / a single Google Doc — anything one-tap).

He wants this for the Brain (the llm-wiki engine, which he runs on his own vault):
a watched surface the Brain polls every few minutes / half hour, ingests new notes,
interprets the cryptic ones with context. **Plus a feedback loop** — an evening /
weekend digest of what it made of his cryptic notes, into which he can intervene
and correct: "no dude, I said *crack the nuts*, not *kiss Alex* — context was we
were at the bakery."

## Diagnostic

### Q1 — Demand reality: STRONG

Sidney already built the workaround himself and uses it daily (WhatsApp self-group).
That is behavior, not interest. A self-built, habitually-used workaround is the
strongest demand signal in the book — the problem is painful enough that he solved
it badly rather than not at all.

### Q2 — Status quo

WhatsApp self-chat (or Notion / a Google Doc). Cost: captures die in WhatsApp,
they never reach the Brain. And on the rare path where the Brain *does* read a
cryptic note, there is no way to tell it "you read that wrong."

### Q3 — Specific human

Sidney — a second operator of the engine, running his own vault. Named, real,
reachable.

### Q4 — Narrowest wedge (two premise-challenges sharpened this)

**Premise-challenge 1 — the capture door is not the value.** Append-only
single-stream capture is trivially solved by the existing file-drop substrate
(`inbox/` + `process-inbox.py`, `voice.py` folder-watch). Operator confirmed:
"single-stream capture finde ich nicht so den innovativen pitch, das geht auch
easy per Datei." So a new capture surface is **not** the feature.

**What already exists (≈80% of the pitch):**
- **Scheduled polling** — the piggyback scheduler in `flush.py` runs collectors on
  cooldown (voice 1h, pictures 6h, …). A capture collector just registers with
  `piggyback_default=True`.
- **Interpretation** — `compile` reads notes → `knowledge/`.
- **Digest (partial)** — `daily_digest_runner.py` + the `daily-digest` agent
  already produce an operator-facing `daily/<date>.md` (≤500 words). But it
  digests *sources*, not "here is how I read your cryptic captures, correct me."

**The one real gap: a correction channel for cryptic captures.**

**Premise-challenge 2 — `reconcile` cannot carry the cheap version.** The first
candidate wedge was "correction = drop a new note, let the existing reconcile
routine sort it out." Verification killed it: `scripts/reconcile.py` is
signal-driven and **fact-violation-only** — it fires only when a concept
contradicts a registered hard fact, and concept↔concept contradictions are
PROPOSE-ONLY. A free-text correction ("re: nuts, I meant crack not kiss") is not a
hard-fact violation; reconcile never touches it. The correction would just become
another independent note, leaving the original misreading standing in parallel.

So the "borrow reconcile" version is hollow. The smallest wedge that *actually
delivers the "talk back" feeling* is the minimal correction-link loop. Operator
chose this over the honest-but-half loop.

## Validated wedge: minimal correction-link loop

```
capture           → ingested, gets a STABLE ID
interpret         → compile reads it (existing), ID carried into provenance
digest            → "capture X [id:a3f] → I read it as Y (→ article Z, context I added: …)"
correct           → operator replies "a3f: crack the nuts, context = bakery"
                    → supersede interpretation Y
                    → re-interpret ONLY item a3f
                    → patch the downstream artifact
```

The correction channel reuses the **same capture door** (a line that starts with a
known ID is a correction) — no new surface, stays one-tap.

## What is genuinely new (the build surface)

1. **Stable capture-ID at ingest**, carried from `raw/` through to the compiled
   artifact's provenance (extends the existing `compiled_from` frontmatter).
2. **Digest section** that lists recent captures → interpretation + the context the
   Brain added, keyed by ID, so a wrong reading is spottable.
3. **Correction-ingest + supersede + targeted re-interpret + downstream patch** —
   the new primitive. This is the load-bearing piece.

## Reuses (do NOT rebuild)

`flush.py` piggyback scheduler · `compile` · `daily_digest_runner.py` /
`daily-digest` agent · `inbox`/`voice` file-drop as the capture door (operator's
choice of concrete surface — not the point).

## Load-bearing risks (for plan-eng-review)

- **Targeted patch vs agent-side writes.** `compile` writes `knowledge/`
  agent-side via SDK tool-use (the `commit_article` "pure I/O extraction" was
  already found to be re-architecture, not extraction — M018). "Re-interpret and
  surgically patch just item a3f's downstream article without a full recompile"
  must work within that agent-side write model. This is the hard part and the most
  likely place the scope balloons.
- **Provenance survival.** Capture-ID must survive raw/ → compiled artifact.
  `compiled_from` exists; needs a per-capture-ID extension.
- **Supersede semantics.** What does "supersede Y" mean concretely — delete the
  sentence, mark it stale, replace it? Different answers, different blast radius.
- **One-meeting-one-file vs one-capture-one-item.** Captures are line-grained;
  most substrate is file-grained. The ID must be sub-file.

## Alternatives considered

**A — recapture + reconcile (REJECTED).** Effort S. Rejected on verification:
reconcile is fact-violation-only, never fires for free-text corrections; the loop
would be hollow (misreading persists in parallel).

**B — minimal correction-link loop (CHOSEN).** Effort M–L. Delivers the actual
"talk back → Brain fixes it" feeling. New: ID system + correction-ingest +
supersede + targeted re-interpret.

**C — confidence-gated proactive push (DEFERRED).** Effort L. Brain self-scores
interpretation confidence, pushes only the uncertain captures as questions
("'crack the nuts' → I read X, right?"). Deferred: small-LLM confidence scoring is
unreliable, needs a push channel, bigger. Revisit *after* B proves the loop is
actually used — if Sidney rarely corrects, C is wasted; if he corrects often,
C is the natural ergonomic upgrade.

## Premises (confirm before scaffolding)

1. The capture surface is a solved problem — reuse file-drop, do not build a new
   one. ✅ (operator confirmed)
2. The only feature worth building is the correction loop; scheduling / interpret /
   digest are assembly of existing parts. ✅
3. `reconcile` is the wrong tool for this; the correction needs its own primitive. ✅
4. The correction channel rides the existing capture door (ID-prefixed line), not a
   new UI. — agree?
5. v1 targets Sidney's vault as the first consumer; the feature ships in the shared
   engine for both operators. — agree?

## Next step

Pitch is strong (real demand, twice-sharpened wedge, the hollow path already
pruned). It is one coherent M-sized feature, not a vague platform.

- Recommended: `ytstack:plan-ceo-review` (concept mode) to stress-test scope /
  ambition before scaffolding — specifically whether the "targeted downstream
  patch" risk justifies starting at C-shape or pulling B even thinner.
- Or, given it is a single well-bounded feature in an existing project, go straight
  to `ytstack:plan-milestone`.

Do not auto-chain — operator picks.
