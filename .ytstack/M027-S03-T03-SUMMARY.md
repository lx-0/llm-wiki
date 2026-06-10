---
milestone: M027
slice: S03
task: T03
project: llm-wiki
closed: 2026-06-10T19:25:00+0200
verification: passed
---

# M027-S03-T03 -- Summary

## Commits

- `39299b1` -- feat(M027-S03-T03): folder-deep-scan dispatch + producer registration
- `6f5a873` -- plan(M027-S03-T03): folder-deep-scan dispatch branch + producer registration

## Outcome

`curiosity/cli.py:_dispatch` now routes `type: folder-deep-scan` to the
new `curiosity/backends/folder.py` (the generic unsupported-error no
longer fires for folder requests; genuinely unknown types still hit it).
The backend is the honest S04 skeleton: it shape-checks the request,
resolves `root_id` → `personal.watched_folders` entry → absolute
candidate path and reports file-exists (stat only — body-blind holds,
doubles as a staleness signal). Dry-run logs what S04 would do including
the informed-consent line ("file X will be loaded and sent to the
configured backend to answer Y — approve?") and succeeds; a real run
returns `success=False, error="folder backend not implemented (S04)"`
and leaves the request file byte-untouched (stays `pending` for S04).
`producers/folder_curiosity.py` registers `FolderCuriosityProducer`
(failure contract α, appended after takes in `producers/__init__.py`) —
**the folder pass now runs in the post-compile loop** wherever
`features.curiosity_loop` + `watched_folders` + digests exist.

## Deviations from plan

None — plan held (5 files as listed).

## Follow-ups

- **lxw goes live on next `wiki update`:** every compile pass will run
  the folder producer against real sources + the real digests
  (llama3.1:8b, $0) and may start writing pending `folder-deep-scan`
  requests. This is where the Q7 precision-tuning loop starts —
  watch `raw/requests/` + the drop-counter log lines
  (`file_not_indexed` / `file_low_confidence` rates).
- T04 (last S03 task): fixture-integration tests — producer against a
  REAL fixture index (walk → write → produce, only the LLM mocked),
  closing the slice's "Done when".
- None for DECISIONS/KNOWLEDGE.

## Verification

Command: `uv run pytest tests/test_curiosity_folder_producer.py -q` then
`uv run pytest -q` -- passed. Full suite **1242 passed, 0 failed**
(1238 → 1242).
