---
milestone: M003
slice: S04
project: llm-wiki
created: 2026-05-03T00:00:00Z
status: planned
task_count: 5
completed_tasks: 0
---

# M003-S04 — Slice Plan

**Goal:** Add a MOC ("Map of Content") layer to the vault — operator-curated index pages that group knowledge by theme. Engine ships 3 empty seed MOCs (people, projects, concepts) matching the existing `knowledge/` subfolder structure; the operator fills them per vault. Dashboard surfaces the MOC list. Lint understands the new type.

**Out of scope (deferred):** state.history.jsonl + P2 charts (S05), Bases browser (S06), MOC auto-suggestion via LLM, Datacore card views.

## Architectural decisions baked in

- **MOCs live in `knowledge/MOCs/`.** Inside `knowledge/` because they ARE knowledge artefacts. Capitalised dir to make them visually distinct in the file tree. Pluralised because there will be many.
- **Type frontmatter: `type: moc`.** Same schema-frontmatter pattern S01 established for concept/connection/fact. Lint's `check_article_type` extended to recognise `MOCs/ → moc`.
- **Seeds are skeletons, not content.** Operator's vault has unique themes; we seed structural placeholders (people, projects, concepts) with H1 + 2-line description + empty Dataview block. Operator edits.
- **Dashboard MOC section uses Dataview, not hand-listed.** A single `dataview` block shows all `MOCs/*.md` files. Operator-added MOCs auto-appear.
- **No new plugins.** Dataview already in S01. Markdown heading + bullet list inside the MOC files is enough for a v1.

## Tasks

- [ ] T01 — Schema + lint. Update `templates/AGENTS.example.md` to document `type: moc` for files in `knowledge/MOCs/`. Update `scripts/lint.py:check_article_type` to map `MOCs/` → `moc`. Add a unit test asserting an article in `MOCs/foo.md` with `type: concept` is flagged as type_mismatch (not silently accepted). Done when `uv run pytest tests/ -k article_type -v` shows the new test green.

- [ ] T02 — Seed MOC files in templates. Create `templates/knowledge/MOCs/people.md`, `templates/knowledge/MOCs/projects.md`, `templates/knowledge/MOCs/concepts.md`. Each: frontmatter (`type: moc`, `title: <Name>`), H1, 2-line description, an empty `dataview` LIST WHERE block scoped to the relevant `knowledge/<folder>/` subdir. `lib/seed.sh:seed_vault_templates` extends to copy `knowledge/MOCs/*.md` into `target/knowledge/MOCs/` (additive — never overwrite operator's MOC content). Done when `wiki seed` on a fresh vault produces three populated MOC stubs.

- [ ] T03 — Dashboard MOC section. Insert `## 🗂 MOCs` between Lint triage and Run sections in `templates/dashboard.md`. Single dataview block: `LIST FROM "knowledge/MOCs"` with file.link. Done when grep shows the section + dataview block; manual smoke confirms the 3 seed MOCs appear after `wiki seed`.

- [ ] T04 — PROCESS.md docs. Add `### MOC-Layer` subsection inside §12 (Vault UX Layer) describing what MOCs are, where they live, how the type/lint/dashboard wiring works, the 3 seed MOCs ship as starting points. Done when `grep -nE "MOC|MOCs" docs/PROCESS.md` shows the new section.

- [ ] T05 — Manual smoke + verification. Run full pytest suite. Apply seed to lxw vault (just templates → vault, no live test for now since auto-fill MOCs would require operator content). Append note to S04-PLAN with smoke result. Done when `uv run pytest tests/ -q` shows all green and the smoke note is appended.

## Done when

All 5 tasks marked `[x]` and verified. M003 exit criterion #5 ("≥3 MOCs in `knowledge/MOCs/` linked from Dashboard") satisfied.

## Notes

(Add observations during slice execution.)
