---
milestone: M002
slice: S02
project: llm-wiki
created: 2026-05-02T14:50:00Z
status: done
task_count: 7
completed_tasks: 7
---

# M002-S02 — Slice Plan

**Goal:** Migrate the existing capability (Thunderbird mbox read + Thunderbird msgFilterRules write + All-Inkl Procmail write) into Reader/Filter adapters. After S02, `scripts/scan-email.py` and `scripts/thunderbird-rules.py` are deleted; `scripts/execute-suggestions.py` no longer branches on account type; `flush.py` discovers piggybacks via Registry; `wiki_config.py` enforces the new nested schema with a hard error on legacy fields. The operator migrates `<vault>/.wiki/config.yaml` once, by hand. Functionality is preserved end-to-end through the new seam.

## Tasks

- [x] T01 — `scripts/adapters/mailbox/thunderbird.py`: `ThunderbirdMboxReader` (port `scan_mbox_metadata`, `scan_mbox_deep`, `extract_body`, `find_mbox_files` from `scripts/scan-email.py`); `ThunderbirdMsgFilter` (port the `msgFilterRules.dat` parsing/writing from `scripts/thunderbird-rules.py`). Both implement the Protocols from `adapters/mailbox/base.py`. Tests: `tests/test_thunderbird_adapter.py` against a fixture mbox + a fixture msgFilterRules.dat.
- [x] T02 — `scripts/adapters/mailbox/allinkl.py`: `AllInklProcmailFilter` (port the All-Inkl Webmail Procmail API client from `scripts/thunderbird-rules.py:601-680` — login, get_procmail_config, save_procmail_config, the destructive-on-empty-body backup discipline from `.ytstack/KNOWLEDGE.md`). Tests with mocked HTTP via `httpx.MockTransport`.
- [x] T03 — `scripts/adapters/mailbox/__init__.py` registers the kind→adapter dispatchers. `resolve_reader(account)` returns `ThunderbirdMboxReader(...)` for `reader.kind=="thunderbird-mbox"`, else `None`. `resolve_filter(account)` similar for `thunderbird-msgfilter` and `all-inkl-procmail`. Unknown kinds → `None` (graceful agnostic). Logs a one-line warning on unknown kind so the operator notices typos without crashing.
- [x] T04 — `scripts/wiki_config.py:Personal.accounts` schema: switch from flat fields to nested `reader: {kind, …}` / `filter: {kind, …}` blocks. Loader detects legacy fields (any of `mbox_paths`, `imap_host`, `has_procmail`, `filter_paths` at account top level) and raises `ConfigError` with the offending account-id + a copy-pastable migration template pointing at CONTEXT.md. Update `config.example.yaml` to show the new shape with three example account-stanzas (thunderbird-mbox + all-inkl-procmail; gmail-api both sides — placeholder; thunderbird-mbox + thunderbird-msgfilter).
- [x] T05 — `scripts/execute-suggestions.py:163-185`: replace the `if has_procmail_support / elif is_gmail / else msgFilterRules` block with `filter_adapter = resolve_filter(account); if filter_adapter is None: skip-and-warn; else filter_adapter.apply(rule, dry_run=dry_run)`. Drop the `tb_rules.has_procmail_support` and `tb_rules.is_gmail_account` helpers (they're dead code after this).
- [x] T06 — `scripts/flush.py`: replace the hardcoded `_PIGGYBACK_COMMANDS` dict (lines ~46+) with `from collectors import piggyback_collectors`. Loop iterates Collectors; cooldown / `enabled` / `max_per_run` come from `SPEC` + `CONFIG.piggybacks.<name>` (per-task overrides preserved via existing config layer). Re-test that lint, review-wiki, scan-screenshots, optimize-claude-md, follow-requests, sync-memories, retry-failed-flushes still spawn — they need wrapping into Collector subclasses too if they aren't already (cheap: thin Collector that shells out to the existing script during this transition; full migration is M003).
- [x] T07 — Delete `scripts/scan-email.py` and `scripts/thunderbird-rules.py`. Operator migrates `<vault>/.wiki/config.yaml` to the new schema by hand (one-time edit, takes ~2 minutes for the existing accounts). Run end-to-end smoke: `wiki collect email --account work` produces a `raw/notes/email/work-<date>.md` whose shape matches what `scan-email.py` wrote yesterday (manual diff against the last historical report).

## Verification

```bash
# After T01-T07:
cd <vault>/.wiki && uv run pytest tests/test_thunderbird_adapter.py tests/test_allinkl_adapter.py -v
# Expected: green

# Confirm legacy schema rejection:
echo "personal:\n  accounts:\n    legacy:\n      email: x@y.com\n      mbox_paths: [INBOX.mbox]" > /tmp/legacy.yaml
WIKI_CONFIG_PATH=/tmp/legacy.yaml uv run python -c "from wiki_config import CONFIG; CONFIG.personal" 2>&1 | grep -q "ConfigError" && echo "✓ legacy rejected"

# Confirm execute-suggestions no longer branches on account type:
grep -E "has_procmail_support|is_gmail_account" scripts/execute-suggestions.py && echo "✗ dead branches remain" || echo "✓ no type-branching"

# Confirm scan-email.py + thunderbird-rules.py gone:
test ! -f scripts/scan-email.py && test ! -f scripts/thunderbird-rules.py && echo "✓ legacy scripts deleted"

# Confirm Registry-driven piggybacks:
grep -E "_PIGGYBACK_COMMANDS\s*=" scripts/flush.py && echo "✗ still hardcoded" || echo "✓ piggybacks via Registry"

# Live end-to-end:
cd <vault>
./.wiki/wiki collect email --account work
test -f raw/notes/email/work-$(date +%Y-%m-%d).md && echo "✓ live scan via Thunderbird adapter"
```

## Out of scope for S02

- Gmail Reader / Filter — S03.
- IMAP-direct Reader (separate kind from gmail-api). Could be added in S03 or M003.
- Migration of other piggyback scripts (lint, review-wiki, scan-screenshots, etc.) into proper Collectors with full SPECs. T06 wraps them as thin Collectors-that-shell-out; full Collector-ification is deferred to M003 when the second substrate type forces the issue.

## Done when

All 7 tasks `[x]`. Verification commands all pass. Operator confirms `wiki collect email --account work` produces equivalent output to the last `scan-email.py` run.

## Notes

(Append observations during execution.)
