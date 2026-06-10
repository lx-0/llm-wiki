---
milestone: M027
slice: S05
task: T03
project: llm-wiki
closed: 2026-06-11T01:35:00+0200
verification: passed
---

# M027-S05-T03 -- Summary

## Commits

- `1d4b23d` -- fix(M027-S05-T03): dedicated folder-answer dispatch — type + SUBSTRATE_PROMPTS entry
- `c03d4b9` -- fix(M027-S05-T03): compile_main rule 12 — folder answers are explicitly-requested facts
- `0406b5f` -- docs(KNOWLEDGE): done+ingested proves no knowledge-write
- `869c1f9` -- plan(M027-S05-T03): lxw operations e2e — exit criterion #6

## Outcome

**Exit criterion #6 demonstrated live on lxw.** Full loop: operator-
consented request (Hetzner invoice PDF, work-company) → real SDK
in-place read → answer-only artifact (`sensitivity: internal` stamped,
`as_of: 2026-06-10`) → compile → fact in
`knowledge/projects/yesterday-ai-cloud.md` (State + Timeline, amount /
invoice no. / per-project breakdown, provenance to the answer artifact)
→ `wiki query "Was hat uns Hetzner im Mai 2026 in Rechnung gestellt?"`
returns the folder-sourced fact WITH provenance and cross-links it to
the narrative layer (Y-Claw = agent fleet). Total spend ≈ $0.40.

**Two real engine bugs found + fixed en route** (the e2e earning its
keep): (1) `compile_main` rule 1's "not trivial facts" bar dismissed the
explicitly-requested fact → rule 12 exempts folder answers (never end
with zero writes). (2) Layer-2: rule 12 was invisible because
`type: note` rides `compile_default` via `_DEFAULT_DISPATCH` — two
zero-write "done" runs. Fix: answers carry `type: folder-answer` +
dedicated `SUBSTRATE_PROMPTS` entry (`compile_main`, 20 turns,
haiku-4.5); the T01 routing-parity pin was consciously replaced by a
dedicated-dispatch pin (its declared purpose). KNOWLEDGE entry:
"done+ingested proves no knowledge-write; new substrates silently
inherit compile_default."

## Deviations from plan

- Producer abstained on both real sources (`file_low_confidence` — Q7
  gate working; dir-skeleton-only trimmed tree gives weak filename
  signal) → operator-consented seed per the plan's fallback (file chosen
  via AskUserQuestion: Hetzner invoice over DKB depot CSV).
- `work-company` additionally tagged `sensitivity: internal` so the
  carry was testable despite the untagged-file choice.
- Three compile calls instead of one (two zero-write diagnoses) —
  covered by the plan's classify-and-fix clause.

## Follow-ups

- **Sensitivity carry design finding:** the artifact stamp works
  (deterministic); the ARTICLE-level carry did not fire — and
  shouldn't blanket-fire: tagging a 95%-untagged mixed-source article
  `internal` because of one fact is ill-defined. The honest carrier is
  the per-fact provenance link to the tagged artifact. Rule 11 stays as
  guidance; revisit semantics with the financial-fact-layer consumer.
  → noted in KNOWLEDGE; no further action now.
- Producer precision (Q7): trimmed-tree filename signal is weak —
  candidate lever for S06/later: per-root digest injection instead of
  all-roots, or grep-based digest access.
- S05 complete → `/ytstack:reassess-roadmap`; only S06 remains.

## Verification

Live: `wiki compile --file …answer-hetzner…` →
`type=folder-answer → compile_main @ haiku-4-5`, fact written;
`wiki query` returns it with provenance (output quoted in-session).
Engine suite **1272 passed, 1 skipped**.
