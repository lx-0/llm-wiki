---
milestone: M002
slice: S03
project: llm-wiki
created: 2026-05-02T14:50:00Z
status: planned
task_count: 6
completed_tasks: 0
---

# M002-S03 — Slice Plan

**Goal:** The actual user-facing capability — a real Gmail account in `CONFIG.personal.accounts` runs end-to-end. `wiki collect email --account <id>` scans Gmail via the API and writes a report; `execute-suggestions.py` applies a filter rule via Gmail API on operator approval. Multi-account multi-kind setup (e.g. work=Thunderbird-mbox+AllInkl-Procmail, private=Gmail+Gmail) is the live shape. The original "scan-email mit Gmail" use-case ships.

## Tasks

- [ ] T01 — Resolve the Gmail OAuth strategy (open question from M002-CONTEXT). Decision: store the OAuth token at `<vault>/.wiki/state/gmail-token-<account-id>.json` (gitignored — it's runtime state). Refresh-token flow on 401. Initial OAuth bootstrap via a new `wiki gmail-auth <account-id>` subcommand that runs the standard installed-app OAuth dance and writes the token. `CONFIG.personal.accounts.<id>.reader = { kind: gmail-api, oauth_client_secret_env: <env-var-name> }` — operator sets the env var to a path pointing at a Google-issued client_secret.json. Document this in `CONTEXT.md` Reader section.
- [ ] T02 — `scripts/adapters/mailbox/gmail.py`: `GmailReader` (Gmail API client via `google-auth` + `googleapiclient`; methods: `list_folders` → label list; `scan_metadata` → `messages.list` with paging + per-message `messages.get(format=metadata)`; `scan_deep` → `messages.get(format=full)` with body decode). Stateless Protocol: each call opens a fresh service object using the cached token; refresh token on first 401 then retry once.
- [ ] T03 — `scripts/adapters/mailbox/gmail.py`: `GmailFilter` (Gmail API: `users.settings.filters.list` + `users.settings.filters.create`). `apply(FilterRule)` translates `FilterCondition.from_addrs` to Gmail's `from:` query syntax, `FilterAction.kind=="move"` to `addLabelIds=[<label>]`. Idempotent: dedup-check via `list_existing()` before create. `dry_run=True` prints the API call without dispatching.
- [ ] T04 — `wiki gmail-auth <account-id>` subcommand: reads `account.reader.oauth_client_secret_env` from CONFIG, runs the local-loopback OAuth flow (port from `google-auth-oauthlib`), writes the token to `.wiki/state/gmail-token-<account-id>.json`. Idempotent: re-running re-issues the consent screen. Help text + integration into `wiki help`.
- [ ] T05 — Update `scripts/adapters/mailbox/__init__.py:resolve_reader` / `resolve_filter` to dispatch `gmail-api` kind to the new adapters. Update `config.example.yaml` with a real-shaped Gmail account stanza (placeholder env-var + label).
- [ ] T06 — Live smoke test: configure a real Gmail account in operator's `<vault>/.wiki/config.yaml`. Run `wiki gmail-auth private` (one-time). Run `wiki collect email --account private` — confirm it produces a metadata report to `raw/notes/email/private-<date>.md` covering all labels with sender stats. Drop a `FilterRule` into `raw/suggestions/` (manual, for now) and run `execute-suggestions.py` — confirm it creates the filter via Gmail API. Append findings to `.ytstack/KNOWLEDGE.md` (rate limits, auth quirks, anything load-bearing).

## Verification

```bash
# After T01-T05 (offline tests):
cd <vault>/.wiki
uv run pytest tests/test_gmail_adapter.py -v
# Expected: green; tests use mocked googleapiclient

# Schema docs:
grep "gmail-api" config.example.yaml
# Expected: a complete example stanza

# Help text wired:
./.wiki/wiki help | grep gmail-auth
# Expected: gmail-auth subcommand listed

# T06 — live, requires real creds:
cd <vault>
./.wiki/wiki gmail-auth private              # one-time OAuth
./.wiki/wiki collect email --account private # end-to-end scan
test -f raw/notes/email/private-$(date +%Y-%m-%d).md && echo "✓ live Gmail scan"

# Filter-side live test:
cat > raw/suggestions/test-rule.yaml <<EOF
status: pending
account: private
rule:
  name: "Test newsletter rule"
  condition:
    from_addrs: ["newsletter@example.com"]
  action:
    kind: move
    target: INBOX/Test
EOF
./.wiki/wiki ... # however suggestions get applied — confirm Gmail filter created
```

## Out of scope for S03

- IMAP-direct Reader (non-Gmail non-AllInkl accounts). Defer until a real third backend is needed.
- Sieve filter writer for IMAP. Same — defer.
- Calendar / browser / screenshots / tabs / memory collectors migrated to the Collector pattern. M003 candidate (now that the seam shape is validated by mailbox).
- Gmail watch/push notifications for incremental scan via webhook. Standard `messages.list?historyId=…` polling is sufficient for now.

## Done when

All 6 tasks `[x]`. Live smoke test (T06) green against a real Gmail account. Operator confirms multi-account multi-kind setup works (e.g. simultaneously: work=Thunderbird-mbox+AllInkl-Procmail, private=Gmail+Gmail).

## Notes

(Append observations during execution. The Gmail API has known quirks: 250 quota-units/sec/user, deduplication in `messages.list`, label-vs-folder semantics. Document in KNOWLEDGE.md as they surface.)
