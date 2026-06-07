# `wiki correct apply` — clarification over-reach + partial/non-resumable runs

Two defects observed running `wiki correct apply` on the **lxw** vault (engine v0.1.6),
applying three real org-rename facts (ystacks→`Yesterday-AI/skills`; yastack+yopstack
bundled into `Yesterday-AI/yesterday-skills`; product lineage leadme→experts-app→Academy).
Source: `scripts/facts/correct_apply.py` + `prompts/correct_apply.md`.

## Defect A — page-level "Superseded" banners on pages that only *reference* the entity

For `clarification` / `disambiguation` facts the agent greps `negation_terms` across
`knowledge/` and edits every match. `prompts/correct_apply.md` does **not** distinguish:

- a page whose **subject IS** the corrected entity → a top-of-page note is appropriate, vs.
- a page that merely **references** the entity → the note must be scoped to the reference,
  never a generic page-level banner.

Result: the ystacks→skills fact inserted a top-of-page banner
`> **Superseded marketplace context (2026-05-31):** …`
onto `knowledge/projects/ytstack.md` and `knowledge/projects/paperclip-companies.md` —
**both `status: active`**. ytstack only *lists into* the renamed catalog; it is not
superseded. At a glance the banner reads as if the page's own subject is dead. The body
text was correctly scoped ("References below to the … catalog"), so the defect is the
**heading + top-of-page placement**, not the content — but on an active-subject page any
`> **Superseded …**` lead-in is misleading. (Operator flagged it immediately: "ytstack
ist NICHT obsolete, aber der correction ändert dies, warum?")

The `ystacks-*` *concept* pages fared fine: their banners scope to "catalog **name**" and
explicitly add "the discipline itself is unchanged" — those read correctly. So the rule
is learnable: it's specifically the generic page-level "Superseded"/"Obsolete" lead-in on
a reference-only page that breaks.

### Suggested prompt fix (`correct_apply.md`)
For non-`negation` statuses, before editing a match decide subject-vs-reference:
> The file's **subject** is named by its `title:` / H1. If the corrected entity IS the
> subject, a brief top-of-page note is OK. If the page only **references** the entity,
> scope the correction to the specific line/section and do **not** add a page-level
> "Superseded"/"Obsolete" banner; never phrase a reference-page note so the page's own
> subject reads as deprecated.

Optionally pass the fact's subject + aliases into the prompt so subject-vs-reference is
deterministic rather than inferred.

## Defect B — run crashed mid-propagation, leaving a partial, non-resumable correction

The third (lineage) apply crashed:
```
ERROR  Fatal error in message reader: Command failed with exit code 1 (exit code: 1)
ERROR    correct_apply ✗ failed after 348.6s — kind=unknown
WARNING    [CLI-STDERR] (empty — bundled CLI exited without writing to stderr)
```
The agent had already edited ~10 files (frontmatter `status: predecessor`, lineage notes)
but never printed the `## Applied summary`, and `index.md` / `.wiki/logs/operations.md`
updates were likely incomplete. Per-file edits are atomic (no half-written files), but the
correction is **partially applied with no signal of where it stopped**.

Asks:
1. The bundled CLI exited non-zero with **empty stderr** — surface the real cause
   (max-turns? context/length? transient API error?). `--max-turns 50` may be the ceiling
   on a large vault and should be configurable / reported when hit.
2. `apply` should be **idempotent / resumable** — re-running must not double-insert banners
   (skip files already carrying the fact's note, keyed e.g. on the `facts/<slug>` ref).
3. On failure, emit a partial-application manifest (files touched) so the run can be
   finished or reverted deterministically.

## Repro
1. `wiki correct add` a `clarification` fact renaming repo X→Y with `--term "Org/X"`.
2. `wiki correct apply <slug>`.
3. Observe a top-of-page `Superseded` banner on every page that *references* X, including
   active-subject pages.

---
_Filed from the lxw vault session 2026-05-31. Operator authorized this backlog entry;
the lxw-side banners on the two active pages were hand-corrected/removed there._
