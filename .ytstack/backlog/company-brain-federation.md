# Company-Brain — federation topology + critique of Suh's "single timeline" thesis

**Status:** concept / pre-office-hours findings (2026-06-13). NOT a committed milestone.
**Purpose:** Capture the architecture findings from the Alex+Sid conversation about
running llm-wiki as a *company* wiki, so the upcoming office-hours + roadmap
discussion starts from a worked-through position instead of a blank page.
**Companion docs:** `gbrain-comparison.md` (team-sharing / multi-tenant is a problem
llm-wiki has *not* committed to), `karpathy-comparison.md`, `architecture-scaling-2028.md`,
`llm-transcripts-collector.md` (the agent-chat substrate that Suh's thesis leans on),
`operator-financial-operational-fact-layer.md` (company master-data substrate).

---

## 0. Origin

Sid shared a John Suh (@john_ssuh) X post framed as *"die Zukunft unseres Brains,
teilweise noch nicht so gut gelöst — müssten mal die Köpfe zusammenstecken."*

**Suh's thesis (verbatim gist):** companies may need to be *rebuilt from the ground up*
around a *single timeline* of all observability + product metrics + file changes in a
retrievable system — "Datadog + Posthog + Google Drive + Slack (really a unified
filesystem of Claude Code chats + Codex chats)." Claimed as the *new data foundation
to maximize AI*. Rationale: keeping track of diffs on existing systems is basically
impossible → can't produce longitudinal info on decisions and rollbacks. Skeptical
existing businesses adopt (means overhauling instrumentation + business data), but
businesses built on it "can execute 100x better and faster."

---

## 1. Verdict on Suh's thesis: ~70% recycled data-warehouse vision, ~30% one genuinely new insight

The new 30% is underrated; the 70% will eat the project if taken literally.

### The real insight (the 30%)

The genuinely new part is **not** "everything in one system" — that is the 30-year-old
single-source-of-truth dream (Data Lake → Lakehouse → CDP → Snowflake). It always fails
the same way: the value is in correlation/retrieval/semantics, not colocation, and the
maintenance cost of a universal schema grows faster than the value.

What is actually new is narrow and specific:

> **The unit of record shifts from the event/row to the *decision-with-its-reasoning-trace*.**

Agent chats (Claude Code / Codex) are the **first artifact in business history that
captures the *why* alongside the *what* in machine-retrievable form** — the deliberation,
the rejected alternatives, the rollback reasoning. Classical systems log outcomes
(a commit, a metric jump, a deploy) and discard the deliberation. If you retain the
*deliberation substrate*, you can reconstruct decisions and rollbacks longitudinally —
"basically impossible" today, and genuinely new because this deliberation simply did not
exist in retrievable form before LLM agents began emitting it as a byproduct.

### Where Suh overreaches (the 70%)

1. **"Rebuild from the ground up" / "100x" = greenfield fallacy.** Big-bang "unify all
   data first, value later" inverts the risk curve into the exact shape that kills large
   IT projects. The successful version of unified observability is *always* bottom-up and
   incremental — which contradicts "rebuilt from the ground up."
2. **The code→business analogy breaks exactly where he leans hardest.** Coding agents need
   diff-history — true, narrow, tractable *because code has a commit graph and deterministic
   rollbacks*. A "rollback" of a business decision (pricing, a hire, a strategy pivot) has
   **no clean inverse and no canonical representation.** `git revert` for a company does not
   exist. He extrapolates from the one domain that has diff-structure to all domains that
   don't.
3. **Four incompatible data types crammed into "single timeline":** observability
   (high-cardinality numeric time-series), product metrics (aggregated numeric), files
   (documents), agent chats (deliberation text). Datadog exists *separately from* your docs
   precisely because volume/cost/query profiles are incompatible. The separation is a
   response to real physics (cardinality, latency, retention economics), not legacy cruft.
4. **"100x better and faster" is the tell.** No mechanism given. The bottleneck on business
   execution is almost never *retrieval of past data* — it's judgment, coordination, and the
   irreducible latency of the real world (customers, hiring, markets). Better memory does not
   compress those.

---

## 2. The reach-boundary insight (the load-bearing finding)

Decision-provenance is tractable in exactly the conditions ytstack already satisfies — and
intractable outside them. ytstack is a **context-continuity harness for one project
instance** (engineering-scoped); the `DECISIONS.md` + `SUMMARY` + `ROADMAP` provenance is a
*byproduct* of that, not its purpose. It works for two reasons, both bound to the project
instance:

1. **Bounded unit** — a project has a boundary, lifecycle, diff-able artifacts (code, plans).
   A company has none of these as a whole.
2. **Byproduct generator** — the coding agent *emits* the deliberation for free because it
   does the work.

Suh says "extend to businesses as a whole." Both preconditions vanish past the project
boundary. **There is no byproduct generator for business decisions** — no agent that lays
the pricing decision or the hire down as JSONL with a reasoning trace. Without one you are
back to *manual* decision-logging, which is a **discipline problem, not a storage problem.**
No data architecture fixes a company being bad at writing down its *why*. Suh sells a storage
solution to a discipline problem.

This grounds the honest scope of the whole vision:

> **Reach of the vision = the fraction of company work done *through* AI agents.**

Today: coding (provenance falls out for free; ytstack proves it at project grain). As agents
enter ops/marketing/support, each domain brings its *own* byproduct-provenance stream. "Businesses
as a whole" = "businesses, as far as agents do the work." It grows — but you *get it incrementally,
for free, exactly where agents already work.* The opposite of "rebuild the company around a
timeline now."

**Corollary — the company version is NOT a bigger ytstack.** A company-wide harness would be
the big-bang mistake. The unit that *has* provenance is always the bounded thing — person,
project, decision. The company is a **graph over many bounded instances + people**, not a
harness wrapped around the org.

---

## 3. The right abstraction: decision-provenance *graph*, not single *timeline*

"Single timeline" is what makes it sound like a data-lake and a firehose. The buildable
abstraction is a **queryable decision-provenance graph**: decisions as first-class nodes,
each linked to the evidence (metrics, files, chats) that produced it. Linkage across
separate stores delivers the correlation value *without* the rebuild/single-system
conclusion — even the good 30% does not require colocation.

---

## 4. The federation topology (operator's vision — materially stronger than "brain = company wiki")

Each person runs their **own personal llm-wiki**; the **company wiki sits above**; **channels
between them ensure only company-related data flows up.** This fixes the hardest blocker from
the first-pass critique:

- **Privacy becomes a structural property, not a policy.** `raw/` (mail / health / voice —
  the radically private) *never leaves the personal vault*. The channel is the only boundary;
  everything below it is private by construction. This is a *better* privacy model than a
  central company wiki with ACLs, because the default is fail-closed and a human sits at the
  boundary. → eliminates the "company brain needs per-person read-scopes" blocker.
- **The boundary-guard machinery already exists.** M027 ("human-approval walk is the
  content/cloud gate; metadata index unmasked, content gated", DECISIONS 2026-06-07) is exactly
  the channel-governance pattern: a human approves, per-item, what crosses a sensitivity
  boundary. The company channel is the same shape: "company-related? → approve → promote."
- **Two federation axes, same shape:** *people* federate up (personal-brain → company-brain),
  and *initiatives* federate up (per-project ytstack → company graph). Both connect via the
  thin reconciliation layer described below.

---

## 5. Design forks & hard problems (input for office-hours)

### Fork A — what flows up: raw or distilled? → **recommend distilled**
- Raw up → company-brain re-compiles: pays compile cost N× and drags substrate over the
  boundary (weaker privacy).
- Distilled up → personal-brain compiles once, promotes *finished articles*: raw stays private
  by construction (strongest guarantee); company-brain's job becomes **reconciliation, not
  re-distillation.**
- Recommendation: **distilled.** It preserves the personal brain's work and makes the strongest
  privacy story. Cost: surfaces the cross-vault entity-merge problem (below) as the company
  brain's core new capability.

### Hard problem 1 — channel must be **fail-closed**
"Only company data flows up" is a fail-closed requirement. Auto-classification ("LLM guesses
company-relevance") is fail-*open*: a false-positive leaks private data upward — the exact
failure to prevent. So: **default private, explicit promote, human-approved.** Auto-classify may
only *suggest* (compiler-suggestions pattern: suggest / approve / execute), never promote.

### Hard problem 2 — cross-vault entity-resolution + multi-author reconciliation (the new core capability)
N people write articles about the *same* shared entity (one project, one customer, one decision).
The toolkit already exists, single-vault — federation makes it cross-vault:
- **Takes (M011, WHO believes WHAT) + Author-attribution (M009):** the company brain does NOT
  collapse N views into one truth — it holds them as *attributed takes* on a shared entity-page.
  "Alex vs. Sid on the architecture direction" lives as attributed tension, not an overwritten claim.
- **Connections (M012, tension / mechanism / dependency):** where the *org portrait* emerges — from
  the tensions between views, not their averaging. The org-brain's synthesis target is the org's
  tension-landscape over shared entities, not a second self-cartography.
- **`wiki dedup` (shipped — difflib + German-phonetic-key):** the seed of cross-vault entity
  resolution. **Net-new:** shared *project/concept* identity across vaults. Person identity has a
  seed (`implicit_operator_author` slug = person-page filename); shared project/concept IDs do not.

### Hard problem 3 — scope must be a **compile-time article axis** (avoid the redacted-mirror leak)
Article-grain promotion leaks if an article *mixes* scopes (a `projects/yesterday-x.md` that mentions,
in passing, a private health detail or a personal opinion). Redacting at the channel is the
redacted-mirror trap (round-trip over a sanitized copy leaks or destroys). Clean fix: **scope is a
compile-time frontmatter axis — sibling of `compile-role` (M007) and `domain` (M013).** The compiler
separates company- and personal-content into distinct articles *from the start*; only `scope: company`
articles are channel-eligible. The fail-closed guarantee becomes structural (one axis + filter), not
post-hoc redaction.

---

## 6. Explicitly out of scope / dropped
- **Metrics (Datadog / Posthog).** Federation does not add numeric time-series, and distilling
  metrics ≠ distilling prose. Drop it deliberately: a company *wiki* (knowledge / decisions / people /
  projects) is a coherent scope without time-series. Suh's full vision includes metrics; the realistic
  llm-wiki-derived company brain does not — an honest scope decision, not a gap to apologize for.
- **"Rebuild from scratch" framing.** Rejected on the greenfield-fallacy grounds above.

---

## 7. The single test question for office-hours (separates substance from FOMO)

> "Name a concrete decision from the last 6 months we'd have made *better/faster* if metrics + files +
> chats had sat in **one** retrievable system — and was the bottleneck really *retrieval*, or was it
> judgment / coordination?"

Three real examples where retrieval was the bottleneck → it's worth building. Struggling to name them →
you're about to build a data-lake out of FOMO.

---

## 8. One-line summary
Suh's intuition is good, his conclusion is wrong. The buildable kernel is **decision-provenance as a
graph over the agent-deliberation substrate**, captured incrementally wherever agents already do the
work — **not** "rebuild the company around a single timeline." For llm-wiki specifically: a **federation**
(personal brains ⊕ fail-closed channel ⊕ company reconciliation brain), with the open work condensing to
three things — (1) `scope:` as a compile-time axis, (2) a fail-closed promote channel (reuse the M027
approval machine), (3) cross-vault entity identity + multi-author reconciliation (Takes / Connections are
there; shared IDs are not).
