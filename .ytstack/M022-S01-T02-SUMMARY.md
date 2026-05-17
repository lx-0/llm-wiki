---
milestone: M022
slice: S01
task: T02
project: llm-wiki
closed: 2026-05-17T13:55:00Z
verification: passed
---

# M022-S01-T02 — Summary

## Outcome

`process_inbox()` in `scripts/process-inbox.py` rewritten end-to-end into a 3-branch two-zone flow:

1. **HTML branch** — `ingest-html.py --mode both` produces the artifact in `raw/articles/` (unchanged behavior). The original `.html` now moves to `raw/inbox-wiki/` via the new `_archive_to_inbox_wiki()` helper. Replaces `file_path.unlink(missing_ok=True)` — no more silent original-loss. **Operator-facing change**: every successfully-ingested HTML now leaves an auditable copy in the vault.
2. **Binary branch** (`EXTENSION_MAP` hit, sentinel `"binary"`) — archive-only to `raw/inbox-wiki/`, no LLM classify, no artifact write. Replaces the old routing to `raw/audio/` / `raw/papers/` (folders are still in `paths.py` but unwritten from this path).
3. **md/txt branch** — LLM classify (Ollama) → `shutil.copy2()` to artifact at `raw/<cat>/<name>.md` → `add_frontmatter()` on the artifact (NOT the original) → original (unmodified, no frontmatter) moves to `raw/inbox-wiki/`. **Two-zone invariant**: artifact has frontmatter, original is byte-identical to what hit the inbox.

Helper `_archive_to_inbox_wiki(file_path)` handles mtime-iso filename-collision suffix (`<stem>-YYYYMMDDTHHMMSS<.ext>`) — deterministic and idempotent.

Dry-run path prints both target paths per drop (artifact + archive) so operator can preview.

## Deviations from plan

None on the flow level. Minor implementation detail: the old code mutated `file_path` in-place via `add_frontmatter()` BEFORE moving — the new flow writes to the artifact copy, leaving the inbox-side original untouched until it moves to `raw/inbox-wiki/`. This is the correct two-zone semantics ("original = as-arrived").

## Follow-ups

- `RAW_AUDIO_DIR` + `RAW_PAPERS_DIR` constants in `paths.py` are dead from this path; still kept for one slice in case another collector references them. Sweep candidate for T05.
- Frontmatter stamped onto the artifact carries only the old fields (`type`, `date`, `origin: "inbox-drop"`, `tags`, `language`). New M022 channel/source fields (`channel: inbox-wiki`, `source_file: raw/inbox-wiki/<name>`) NOT added — out of T02 scope; surface decision in T05 with the integration tests.
- ingest-html.py itself unchanged: its artifact still lands in `raw/articles/<slug>.md` directly. Whether the artifact should carry a `source_file` frontmatter referencing the archived HTML is the same open question — defer.
- HTML failure path: if `ingest-html.py` returns nonzero, the HTML stays in `inbox/` (current behavior preserved). Future hardening: archive even on failure so the operator can retry without re-dropping. Defer.

## Verification

- 824/824 pytest pass after the rewrite (no regression — helpers tested by existing tests are untouched).
- End-to-end smoke probe: tmp inbox with `test.md`, `memo.mp3`, `page.html` + mocked `classify_file()` + mocked `subprocess.run`. Asserts all six invariants:
  - md original archived in `raw/inbox-wiki/test.md` ✓
  - md artifact at `raw/notes/test.md` with frontmatter ✓
  - md original UNMODIFIED (starts with `# Hello`, no frontmatter) ✓
  - md artifact HAS frontmatter (starts with `---\n`) ✓
  - binary `memo.mp3` archived in `raw/inbox-wiki/`, no artifact ✓
  - html `page.html` archived in `raw/inbox-wiki/` (not unlinked) ✓
  - inbox/ empty after run ✓
- Commit: `c51494a` (atomic with T01).

T02 closes the slice's main behavioral change. T03+T04 sweep cleanup, T05 lands the persisted integration tests covering the smoke-probe invariants.
