---
milestone: M027
slice: S01
task: T02
project: llm-wiki
closed: 2026-06-07T13:10:00+0200
verification: passed
---

# M027-S01-T02 -- Summary

## Commits

- `2d587c1` -- plan(M027-S01-T02): answer-landing contract = option (a)
- `7aa12ed` -- feat(M027-S01-T02): lock answer-landing contract (a)

(The ytstack `M###-S##-T##:`-prefix grep finds nothing -- conventional-commit
subjects (`plan(...)`, `feat(...)`) carry the ref in parens, not as a prefix.)

## Outcome

The answer-landing contract is locked as **option (a)** in DECISIONS.md
(2026-06-07 "M027 answer-landing contract"): the folder-backend (S04) reads the
named file(s) in-place and writes a **topic-focused answer-extract** to
`raw/notes/folder/answer-<slug>.md` -- a sibling of the email backend's
`raw/notes/email/deep-<slug>.md` (`DEEP_SCAN_DIR` in
`curiosity/backends/email.py`). The extract is a **normal compile source** (NOT
compile-skip); the next `compile` pass distills it into `knowledge/` via the
established compile knowledge-writer (entity/fact pages, wikilinks, dedup). So
compile is the **single knowledge-writer** -- it both generates the curiosity
request (post-compile producer pass) and consumes the answer on the next pass.
CONTEXT Q1 is closed and the P2 wording is refined (no full file BODY persists;
the derived extract does, as a compile source).

## Deviations from plan

- None of substance. Concrete landing path pinned to `raw/notes/folder/` after
  reading the email backend's `DEEP_SCAN_DIR = raw/notes/email/` precedent (the
  plan said "pin by reading where email lands" -- done).
- "Double-distill" objection from the plan-task discussion was retired per the
  operator's framing (backend extracts source material, compile is the only
  distill-to-knowledge step) -- recorded in the DECISIONS entry.

## Follow-ups

- **Cross-slice constraint for S02:** when S02 marks the metadata index
  compile-skip, it MUST NOT also exclude `raw/notes/folder/` -- the answer
  artifacts there are compile sources and must be distilled. Index = skip,
  answers = distil. Flag in S02's plan.
- S03 (request shape) + S04 (backend write) + S05 (compile-consume) all build
  against this contract; S04 writes the `raw/notes/folder/answer-<slug>.md` with
  provenance frontmatter (source path, topic, request id, as-of mtime).
- Optional `sensitivity:` tag (Q3) is decided in S05 at persist time.

## Verification

Commands:
- `grep -n "answer-landing" .ytstack/DECISIONS.md` -- **matched** (the locked
  contract entry).
- `grep -n "Q1" .ytstack/M027-CONTEXT.md` -- **matched** (`Q1 ... CLOSED`).

verification: passed. (Decision-doc task -- no code; the deliverable is the
locked contract, present + concrete enough for S03/S04/S05.)
