---
milestone: M030
slice: S02
task: T05
project: llm-wiki
closed: 2026-08-25T11:20:00Z
verification: passed
---

# M030-S02-T05 -- Summary

## Commits

- `77d59d6` fix(publish): cap descriptions by UTF-16 units (found by this live run)
- `8128fd3` fix(publish): sys.path bootstrap for child-process dispatch (found by this live run)
- `46dd66d` fix(config): merge the publish section in load() + loader regression test (found by this live run)

## Outcome

First full LIVE publish of the lxw vault to dev.meinkontext.de, operator-driven end-to-end: `wiki update` → knobs set (read-back verified) → `wiki publish --auth` (browser consent; **refresh token WAS issued** — the open risk from T06 is closed) → dry-run review (2024 create, 0 anomalies) → live run: **2020 created + start page in 30:38 min**, then after the UTF-16 fix a rerun **2 created / 2020 unchanged** (live idempotency proof). Server echo via independent client (get_status): 2021→2023 knowledge objects, 8.4 MiB / 100 MiB, digest shows the wiki as a name+count section. Remaining skips by design: `accept-multiple-paste-formats` + `ssh-pubkey-pure-js-derivation` — both carry private-key-block-shaped content and are correctly rejected by the server's secret gate (operator may sanitize the articles or leave them local-only).

## Deviations from plan

Three found-live-and-fixed bugs, each with a regression guard: (1) config loader silently ignored the whole `publish:` section (hand-maintained merge list — now a derive-from-schema test), (2) child-process dispatch missing sys.path bootstrap (bridge pattern applied), (3) description cap measured Python codepoints, server measures UTF-16 units (emoji count double — beulco/sprenger rejected live, now unit-capped).

## Follow-ups

- Operator decision pending: sanitize the 2 secret-gated articles or leave unpublished.
- SCOPE WIDENING ordered by operator 2026-08-25 ("ALLES" = whole vault, not knowledge/-only): raw/ (3798 md), daily/ (535), reports/ (136), workspace/ (82) ≈ +25 MiB — S04; wiki-split decision (one vs two managed wikis) pending operator answer. Non-md assets (2473 png, 904 json, audio) have no contract channel — upstream ask if wanted.

## Verification

Live run exit 0 + `published:` report; independent get_status echo; rerun idempotency (2/2020/0). -- passed.
