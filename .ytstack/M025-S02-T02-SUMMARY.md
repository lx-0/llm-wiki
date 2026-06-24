---
milestone: M025
slice: S02
task: T02
project: llm-wiki
closed: 2026-06-25
verification: passed-with-operator-caveat
---

# M025-S02-T02 — Summary

## Outcome

The daily digest now carries a **Captures** section: each capture of the day, keyed by
short-id, with its interpretation (the article it was compiled into) + a superseded
marker.

- `core/capture_index.build_captures_section(date_iso, *, vault_root=None) -> str | None`
  builds the `## Captures` markdown deterministically (filters the index to captures
  `created` that day, resolves each via `resolve_articles()`, reads a one-line gist from
  the raw capture via `_capture_gist()`). `None` on no-capture days. A table lookup, not
  an LLM call.
- `daily_digest_runner.py` injects it into `daily/<date>.md` **after** the agent writes
  the digest (`_attach_captures_section` + pure `_inject_captures_section`,
  replace-or-append, idempotent — a re-run doesn't stack a second section). Best-effort:
  injection failure never fails the digest run.
- `prompts/agents/daily-digest.md` gains one rule: skip `captures.md`, don't write a
  `## Captures` section — the deterministic one is attached, so the agent must not
  duplicate it.

## Deviation from plan (principled)

The plan said "extend the `daily-digest` prompt to render recent captures". Instead the
section is built **Python-side and injected by the runner**, because capture-id → article
+ status is a deterministic table lookup — exactly the `feedback_no_agent_for_deterministic`
case, and it makes the output exact + unit-testable (REGEL #1) instead of LLM-dependent.
The prompt change is reduced to *suppressing* agent coverage of captures, not producing
the section.

## Verification

`uv run --project .wiki pytest tests/test_capture_index.py tests/test_daily_digest_runner.py`
— 15 passed (3 new builder tests: resolve+filter-by-day, none-on-empty-day, superseded
marker; 3 new injection tests: append, idempotent-replace, preserve-following-section).
Full suite: **1397 passed, 1 skipped**.

**Operator-verified (REGEL #1 — NOT headless-testable):** the *rendered* digest — i.e.
the agent actually honouring the new "skip captures.md" instruction, and the injected
section reading well in Obsidian — needs one real `wiki agent daily-digest` run on a day
with captures. The deterministic builder + injection are fully tested; the agent's
obedience to the prompt rule is not.

## Follow-ups

- **T03** — correction recognition: a capture body referencing a known short capture-id
  (`re:<id>` / `corrects:<id>`) gets `kind: correction` + `corrects: <id>` frontmatter,
  distinct from a fresh capture; the supersede *write-back* is S03. Plus
  `docs/setup-captures.md`.
