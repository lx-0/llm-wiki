# Preferences

Project-level operator preferences for llm-wiki. These ship as a starting point; a fork or new operator should adjust to taste. Anything that should travel with **you** as a contributor (your tone, your language, your editor, your global git policies) belongs in your personal config (e.g. your global `CLAUDE.md`), not here.

## Explain level

explain_level: terse

Options: default | terse | brutal

The project leans terse — no filler, no recap, no apology loops after corrections. Override per-session if you prefer more context.

## Scope discipline (project-level)

- Don't add features, refactor, or introduce abstractions beyond what the task requires.
- When the user says "add X to Y", that means ADD; don't replace. If ambiguous, ask once.
- Don't modify pieces that are working unless the task explicitly says so.
- The user's input is the full scope — don't deduplicate or hunt for adjacent context unless asked.

## Verification (project-level)

- Before claiming a feature is "done": grep TODOs, type-ignores, dead config, skipped tests. CI green ≠ done.
- For UI / frontend changes: start the dev server and manually exercise the feature. Type-checking and tests verify code, not feature.
- Before recommending a memory-stored detail: verify the file or symbol still exists in the current code.

## Engine conventions

- **CLAUDE.md ≤ 200 lines.** Keep it as an opinionated index, not documentation.
- **Integration tests should hit a real backend, not mocks.** The compile pipeline has Ollama + Claude calls that mocks don't catch divergence in.
- **Verify library APIs against current docs before suggesting them** (e.g. via the `context7` MCP if available) — training data lags real-world APIs, especially for fast-moving deps.

## Model preferences

(No project-specific overrides yet. ytstack default routing applies.)

## Timeouts

(No overrides.)

## Notes for forks

If you fork this repo: replace this file with your own preferences. The agent reads it on every session start, so anything you put here (response tone, scope rules, custom conventions) becomes the contract.
