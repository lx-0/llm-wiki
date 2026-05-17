---
milestone: M022
slice: S03
task: T02
project: llm-wiki
closed: 2026-05-17T14:50:00Z
verification: cancelled
---

# M022-S03-T02 — Summary (CANCELLED)

## Outcome

Cancelled during S03 planning. The slice originally called for `.gitkeep` templates so `wiki seed --force` could create the new `raw/inbox-wiki/` + `raw/inbox-mobile/{voice,pictures}/` directories on fresh installs. Inspection of `lib/seed.sh` showed `seed_vault_templates()` only seeds an explicit allow-list (README, AGENTS, dashboard, knowledge.base, Templates/*.md, MOCs, .obsidian) — it doesn't walk `templates/raw/` at all. The collectors all use `*.mkdir(parents=True, exist_ok=True)` so the dirs come into existence on first use.

## Deviations from plan

T02 cancelled outright. No code touched.

## Follow-ups

If `wiki seed --force` is ever extended to walk `templates/raw/` (currently it doesn't), revisit whether placeholder `.gitkeep` files would benefit operator-facing visibility of the new audit zones in fresh-vault installs.

## Verification

n/a — no code change.
