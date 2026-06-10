---
milestone: M027
slice: S04
task: T01
project: llm-wiki
closed: 2026-06-10T21:00:00+0200
verification: passed
---

# M027-S04-T01 -- Summary

## Commits

- `221fb33` -- feat(M027-S04-T01): folder-scan provider seam + Claude SDK reader — closes Q9
- `8976436` -- plan(M027-S04-T01): provider seam + Claude SDK in-place reader — closes Q9

## Outcome

**Q9 closed.** `curiosity/backends/folder_providers.py` defines the
provider contract: `ScanAnswer` (distilled `answer_md` — never the raw
body; `as_of_mtime` stat'd BEFORE the read as the staleness anchor;
cache-aware token counts; `error` field for fail-soft) +
`FolderScanProvider` Protocol + `get_provider()` registry keyed by the
new `models.folder_scan_provider` knob (default `claude-sdk`; unknown
name → loud ConfigError, no silent fallback; a local LLM/agent provider
is a one-entry registry addition later). `ClaudeSdkProvider` runs the
agentic in-place read tighter-sandboxed than compile/dream:
`allowed_tools=["Read"]` only, PreToolUse
`make_path_scope_hook([file_abs])` exact-file scope, `cwd` = file
parent, `max_turns=6`, StderrCapture + `log_sdk_failure`; empty SDK
result → `error="empty_result"`; FileNotFoundError propagates
(quarantine is T03's). Prompts `folder_scan_answer{,_system}.md` carry
the answer-extract contract (P2), exact-value quoting, and the
`NOT ANSWERED IN THIS FILE` sentinel. Knob + KEY_ADDITIONS migration in
the same commit (round-trip 86→87).

## Deviations from plan

- None structural. Two helper signatures verified live instead of
  guessed (`log_sdk_failure(label=, started=, capture=)`;
  `UsageTokens.total_input` not `cache_inclusive_input`).

## Follow-ups

- ⚠️ SDK path is mock-verified only; first live read happens in T04's
  e2e on a real trove (REGEL #1 boundary).
- T02 next: persistence answer-only to
  `raw/notes/folder/answer-<slug>.md` (email deep-scan shape, provenance
  frontmatter incl. `as_of_mtime`) + the P2 test that no raw body lands
  anywhere under the vault; wire `process_request` real-run to
  provider → persist → request status flip.
- None for DECISIONS (Q9 closure is the planned decision, recorded in
  CONTEXT via plan/summary) / KNOWLEDGE.

## Verification

Command: `uv run pytest tests/test_folder_scan_provider.py
tests/test_migrate_config_keys.py -q` then `uv run pytest -q` -- passed.
Full suite **1252 passed, 0 failed** (1246 → 1252).
