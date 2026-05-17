---
milestone: M022
slice: S02
task: T03
project: llm-wiki
closed: 2026-05-17T14:30:00Z
verification: passed
---

# M022-S02-T03 — Summary

## Outcome

- `tests/test_voice_collector.py`: four `.processed/`-assertions rewritten against `voice_mod.MOBILE_ARCHIVE_DIR` (test_real_run + test_dotfiles_and_wrong_suffix + test_empty_source_file). Two new regression guards added (`assert not (inbox / ".processed").exists()`) to catch any future regression that recreates the legacy subdir. Module docstring updated.
- `tests/test_pictures_collector.py` NEW: minimal smoke test asserting the vision-pipeline routes the original PNG to `MOBILE_ARCHIVE_DIR` and never recreates `<inbox>/.processed/`. Vision call (`describe_picture`), thumbnail (`_make_thumbnail`), and Ollama reachability (`ollama_client.is_reachable`) all mocked — no network, no real LLM.

## Deviations from plan

None on the voice side. Pictures-test scope kept minimal (one routing assertion) rather than replicating voice's full 8-test suite — the operator-facing acceptance test for pictures is the batch-report quality, which is a manual probe by design.

## Follow-ups

- More pictures-test coverage (frontmatter shape of per-image sidecar, batch-report content, thumbnail generation, picture-batch frontmatter type) is value-add but not blocking M022. Backlog candidate.

## Verification

- `uv run --project .wiki pytest tests/test_voice_collector.py tests/test_pictures_collector.py -v` → 9/9 passed.
- Full suite 835/835.
- Commit: `87a631b` (atomic with T01+T02).
