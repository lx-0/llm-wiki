---
milestone: M028
project: llm-wiki
created: 2026-06-13T15:51:29+0200
size: L
source_issue: https://github.com/lx-0/llm-wiki/issues/5
reporter: Sidwach (Sid)
---

# M028 -- Context

## Goal

Make `wiki correct apply` non-destructive and truthful: a `negation` fact
annotates the superseded article (supersede-by-default), the engine reports the
*real* filesystem delta (not the agent's self-narrative), destructive ops have a
safety net, and the apply-agent is sandboxed like `reconcile_fact()`.

## Exit criteria

1. Applying a `negation` fact whose terms appear in articles *entirely about* the
   now-superseded framing annotates them (`status: superseded` + frontmatter
   `superseded_by:`/`outdated_since:` + one-line banner under the H1) and deletes
   **nothing** by default. Deletion only fires behind an explicit signal (fact
   field or CLI flag) reserved for *factually false* content.
2. `apply` prints the real filesystem delta — `git status --porcelain` when git
   is present, else a pre/post mtime+hash snapshot — and emits a WARNING when the
   real delta diverges from the agent's claimed `## Applied summary`. The
   destructive accounting is never the LLM narrative.
3. Safety net for destruction: deletions move to `.trash/<ts>/` (or the run is
   refused on a dirty / non-git tree unless `--force`); every article is backed
   up before edit/delete, not just the fact file.
4. `--dry-run` runs the candidate greps and prints the file list + planned
   per-file action (edit / supersede / delete / rename) — blast radius visible
   before any paid call.
5. `apply()` is sandboxed like `reconcile_fact()`: `Bash` dropped from
   `allowed_tools`, a `make_path_scope_hook` PreToolUse hook constrains writes to
   `knowledge/` (minus `facts/`), `daily/`, `index.md`, `log.md`; bounded turns.
   An explicit rename helper replaces the `git mv` Bash path.
6. A first-class `supersession` status exists (`facts/correct.py` enum +
   `lint.py` + prompt) so `negation` stops conflating *false* with *outdated*.
7. Golden test reproducing the issue: one `negation` fact with a broad term no
   longer deletes 17 `knowledge/` articles; the printed summary count matches the
   `git status` delta.

## Size

L -- see `M028-ROADMAP.md` for slice breakdown. Operator chose full scope
(all 6 of Sid's prioritized fixes, including the optional schema change).

## Decisions locked in discuss phase

- 2026-06-13: Default semantics = **supersede/annotate**, not delete. For
  `negation`, `apply` marks the article superseded and keeps history; deletion is
  the rare opt-in reserved for factually-false content. Rationale (from issue #5):
  negation facts are overwhelmingly about *recency*, not *falsehood*; the
  facts-injection-into-compile path already overrides authoritatively without
  destroying the audit trail, so `apply` only needs to clean up stale article
  *bodies* — and "clean up" means mark+annotate. (Operator confirmed.)
- 2026-06-13: Full scope incl. fix #6 (first-class `supersession` status) accepted
  as L, not deferred. (Operator confirmed.)
- 2026-06-13: Reporting must be ground-truth (filesystem delta), never the agent's
  free-text summary. Trust boundary: the LLM proposes edits, the engine records
  what actually changed.

## Open questions

- **Deletion opt-in mechanism:** a `--allow-delete` CLI flag, a per-fact field, or
  both? (Resolve at slice time — leans toward CLI flag + fact field, mirroring how
  cloud opt-in is gated elsewhere.)
- **`supersession` vs `negation` enum:** does `supersession` become a distinct
  `status` value, or a modifier on `negation`? (Fix #6 — decide in the schema slice.)
- **Over-broad-term warning at `correct add` time** (issue's secondary suggestion):
  in M028 scope or its own follow-up? Warn when a `negation_term` matches N
  existing articles. (Lean: fold into the dry-run/blast-radius slice if cheap,
  else backlog.)
- **`.trash/` vs git-precondition:** ship both (trash always + refuse-on-dirty
  unless `--force`), or pick one? (Slice-time; `.trash/` is the substrate-agnostic
  safety net, the git-precondition is the cheap guard.)
- **Banner + frontmatter contract** must round-trip cleanly through a *subsequent*
  compile (the compile path already relabels "(historical)" — ensure M028's
  annotation and compile's supersession don't fight). Verify at slice time.
