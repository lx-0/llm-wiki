---
milestone: M033
slice: S03
task: T02
project: llm-wiki
closed: 2026-10-14T22:25:00+02:00
verification: passed
---

# M033-S03-T02 -- Summary

## Commits

`f4e8a3c` — the folds, the inlines, the guard, the test on the seam; this summary, the
slice-plan flip and STATE follow under the same ref (`git log --grep '^M033-S03-T02'`).
Planning commit `cdcec83`.

## Outcome

No function outside `core/frontmatter.py` reads a fence with a grammar of its own. The
seven package-side copies are gone: `menu_context._read_frontmatter_field` keeps its 2 KB
head read and asks `frontmatter.field`; `collectors/gmeet._split_frontmatter` keeps its
`None` = "not our file" contract through `parse_strict`; `core/agent_spec._split_frontmatter`
keeps `SpecError` (one prefix, the seam's wording) through `parse_strict`;
`core/prompts._split_frontmatter` keeps its documented `({}, text)` contract — an opening
block that is not a mapping is no frontmatter and the whole text stays the prompt — through
`parse_strict` (so no behaviour change rides on the fold; all seven prompt files that open
with a fence parse as mappings anyway); `verify_report._extract_frontmatter` → `parse_strict`
or `None`; `core/utils._parse_fact_frontmatter` keeps the raw-text contract;
`core/links._strip_frontmatter_and_fences` takes its frontmatter extent from `split_fence`
(an unterminated fence is no frontmatter — every line of such a file is live for link
rewriting; CRLF and trailing-space fences now count). `preprocessors/inbox.add_frontmatter`'s
"already has frontmatter" probe (`startswith("---")`) asks `split_fence` for a closed fence.
Three one-line forwarders went: `facts/correct._read_frontmatter` (1 call site),
`timeline._parse_frontmatter` (1), `route._parse_frontmatter` (its only consumer,
`compile.py`'s memory pre-pass, calls the seam; the import went). Kept on purpose:
`take._read_frontmatter` (4 call sites), the C03 accessors `route._frontmatter_type` /
`_frontmatter_compile_role` / `_frontmatter_field` and `classify._frontmatter_type`
(test-pinned), T01's read-wrappers, and the three hand-built writers
(`voice._build_frontmatter`, `capture_collector._build_frontmatter`, `inbox.add_frontmatter`)
whose YAML shapes (`tags: [voice]`, `raw_transcript: |`, a quoted `origin`) `serialize`'s
safe_dump block style would not reproduce — recorded in the S03 notes as a write-side shape
decision for a later arc. Repo-wide `def …frontmatter…(` 26 → 23.

Parity before the fold (`/tmp/t02-parity.py`, 13 shapes × 7 helpers): 72 of 91 identical.
The 19 differences: the seam's tolerance (CRLF, fence at EOF, trailing fence spaces — gmeet,
agent_spec, utils, links); one old-grammar bug — the non-greedy regexes in `prompts` and
`agent_spec` let a `----` line close the fence (the seam reads it as part of the block and
rejects the malformed YAML); the body-after-fence shape on malformed / empty blocks (moot
for prompts, which keeps `({}, text)`); `menu_context` now drops a trailing `# comment`
(YAML rule); `links` treats an unterminated fence as no frontmatter (old: the whole file was
dead for rewriting).

Guard: `tests/test_frontmatter_parity.py::test_no_private_frontmatter_grammar_outside_the_seam`
scans every top-level `*frontmatter*` function under `scripts/` for `yaml.safe_load`, a
fence regex (`\A---`, `^---`) or a fence probe (`startswith("---`, `find("\n---`,
`index("\n---`). RED on ten functions with the first smell list (it also caught the three
writers' emitted `---` lines, which are not parsing — the smells were narrowed to READ
grammar), then RED on the inbox probe alone, green after.

## Deviations from plan

- The acceptance in the slice line ("the def-name grep prints only `core/frontmatter.py`")
  would also condemn the read-wrappers T01 and this task keep on purpose; the guard above
  is the precise form of "0 private parsers" and the S03 notes say so.
- `prompts` keeps its `({}, text)` contract instead of taking the seam's body-after-fence
  shape (the plan listed that as a decision; the measured facts made the conservative
  choice free).
- `inbox.add_frontmatter` was not on the list — the guard found its fence probe; folded.
- `route._frontmatter_field` stays (five assertions in `tests/test_compile_role_dispatch.py`
  import it).

## Follow-ups

- Write-side shape fold (`serialize` for the three writers) — a later arc; S03 notes.
- T03 (slugify) next.

## Verification

Plan command 1: `uv run pytest tests/test_frontmatter_parity.py tests/test_frontmatter.py
tests/reports -q` (+ inbox, links, compile-role tests) → 390 passed; `uv run pytest -q` →
**2072 passed, 1 skipped**; `ruff check` → `All checks passed!`; `ruff format --check` →
clean after one reformat (the test module). Plan command 2 (the grep over the seven files) →
no output. Oracle green inside the suite. CI on `origin/main`: recorded in STATE.
