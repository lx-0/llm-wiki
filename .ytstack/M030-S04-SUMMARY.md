---
milestone: M030
slice: S04
project: llm-wiki
closed: 2026-08-25T13:00:00+0200
verification: passed
---

# M030-S04 -- Summary (ALLES vault-wide into ONE wiki)

## Commits

- `42a25ad` multi-root corpus, vault-rel manifest + migration, publish.roots knob (T01-T03)
- `77d59d6`* UTF-16 description cap (*landed under S02 close, found by live runs of this arc)
- `958ed7c` bounded 5xx/connection retry with backoff
- `3c545c7` token provider with forced mid-run refresh
- plus `fix(publish)`: deterministic 120-cap slugs; escalating disambiguation (parent → full path → path+hash)

## Outcome

The whole lxw vault markdown publishes into the single managed wiki `llm-wiki`: **6571 articles live + start page** (knowledge 2024, raw 3798, daily 535, reports 136, workspace 82, minus 4 secret-gate skips), 24 MiB / 100 MiB quota. Rollout preserved every live slug: the widened dry-run showed **0 retractions** (manifest v1→v2 layout migration proven live), and 603 knowledge articles republished because their raw/daily links now resolve to real `[[slug]]` links instead of degrading to text — the drill-down chain works remotely. Idempotence proof after completion: rerun plans exactly the 4 persistent secret-gate skips, 6571 unchanged, zero writes. 3860 non-markdown files are reported as having no contract channel (no silent cap).

Persistent skips (server secret gate, correct behavior — operator may sanitize):
`daily/2026-06-26/sessions.md`, `daily/2026-07-02/sessions.md` (sk-prefix key shapes), `knowledge/.../accept-multiple-paste-formats.md`, `knowledge/.../ssh-pubkey-pure-js-derivation.md` (private-key blocks).

## Real-corpus findings fixed en route (each with regression tests)

1. >120-char stems in raw/memories/ — deterministic 120-cap instead of plan abort.
2. Same stem + same parent name across reports/studies runs — escalating disambiguation ladder.
3. Upstream deploys mid-run (every meinkontext merge deploys; 503 connection resets) — bounded 5xx retry w/ backoff.
4. Access-JWT expiry mid-run (-32001 after 51 min) — token provider with one forced refresh per request.

## Verification

Widened dry-run 0-retract gate; final run exit 0 (`published: 1210 created, 603 updated, 0 retracted, 4758 unchanged`); independent get_status echo (wikis rollup: llm-wiki 5875→final count via rerun-unchanged 6571); idempotent rerun. Suite 1855 green.
