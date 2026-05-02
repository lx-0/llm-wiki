---
milestone: M002
slice: S01
project: llm-wiki
created: 2026-05-02T14:50:00Z
status: done
task_count: 7
completed_tasks: 7
---

# M002-S01 — Slice Plan

**Goal:** Backbone + first proof — domain types, Reader/Filter Protocols, Collector Protocol with Registry, `EmailCollector` skeleton with `FakeReader`-driven test, and `wiki collect` CLI subcommand. After S01, `wiki collect --list` shows `email`; `wiki collect email --dry-run` runs against a fake reader and writes a sample `raw/notes/email/<fake>.md`. No real backend yet — the seam is provable.

## Tasks

- [x] T01 — `scripts/domain/mail.py` defines `MessageMeta`, `Message`, `FilterRule`, `FilterCondition`, `FilterAction` as frozen dataclasses with the field shapes locked in M002-CONTEXT (Q1+T2 decisions). No imports from `adapters/` or `collectors/`. Module is the bottom of the dependency graph.
- [x] T02 — `scripts/adapters/mailbox/base.py` defines `MailboxReader` and `MailboxFilter` `Protocol` types (T1 stateless decision). Plus `ApplyResult` dataclass for filter feedback. Module exposes `resolve_reader(account_dict)` / `resolve_filter(account_dict)` returning `None` for unknown kinds (graceful agnostic). Stub bodies return `None` for now — concrete adapters land in S02.
- [x] T03 — `scripts/collectors/base.py` defines `CollectorSpec` (frozen dataclass: name, output_subfolder, piggyback_default, piggyback_cooldown_hours, supports_incremental, supports_account_loop), `Collector` Protocol (`SPEC` ClassVar + `is_configured()` + `run(dry_run, incremental)` + `RunResult` dataclass), `@register` decorator, `all_collectors()`, `piggyback_collectors()` (filters by `SPEC.piggyback_default and is_configured()`).
- [x] T04 — `scripts/collectors/email.py` ships `EmailCollector` (decorated with `@register`). `SPEC` declares name=email, output_subfolder=raw/notes/email, piggyback_default=True, cooldown=24h, supports_incremental=True, supports_account_loop=True. `is_configured()` iterates `CONFIG.personal.accounts` and returns True iff at least one resolves to a non-None Reader. `run()` writes a markdown report per account to `raw/notes/email/<account>-<date>.md` using the report shape from the existing `scripts/scan-email.py` (preserved verbatim — no format changes in S01).
- [x] T05 — `scripts/collectors/__init__.py` imports `email` to trigger registration. Re-exports `all_collectors`, `piggyback_collectors`, `register`. Operators import via `from collectors import all_collectors`.
- [x] T06 — `wiki` CLI gets a `collect` subcommand. `wiki collect --list` enumerates registered Collectors with their SPECs. `wiki collect <name> [--dry-run] [--incremental] [--account <id>]` resolves the Collector and calls `run()`. Help text + dispatcher in `wiki` script + new `lib/collect.sh` for any bash-side helpers (probably none — the dispatch is thin).
- [x] T07 — `tests/test_email_collector_fakereader.py` (new dir if absent): defines a `FakeMailboxReader` with seeded `MessageMeta` list. Test 1: `EmailCollector` with one account configured to use FakeReader writes a markdown report to a tempdir. Test 2: account whose reader.kind doesn't resolve gets silently skipped (graceful agnostic). Test 3: `--dry-run` flag is honored (no file writes). Runnable via `uv run --project .wiki pytest tests/`.

## Verification

```bash
# After T01-T07:
cd <vault>/.wiki
uv run python -c "from collectors import all_collectors; print([c.SPEC.name for c in all_collectors()])"
# Expected: ['email']

uv run python -c "from domain.mail import MessageMeta; print(MessageMeta.__dataclass_fields__.keys())"
# Expected: dict_keys(['id', 'account_id', 'folder', 'from_addr', ...])

cd <vault>
./.wiki/wiki collect --list
# Expected: a one-line entry for 'email'

./.wiki/wiki collect email --dry-run
# Expected: "would write raw/notes/email/<fake>-<date>.md" — no actual files

cd <vault>/.wiki && uv run pytest tests/test_email_collector_fakereader.py -v
# Expected: 3 passing tests
```

## Out of scope for S01

- Real Reader / Filter implementations — those are S02 (Thunderbird, AllInkl) and S03 (Gmail).
- CONFIG schema enforcement — S02 introduces the hard error on legacy fields. S01 reads accounts via the existing `Personal.accounts` shape; if no account resolves to a non-None Reader, the collector is just no-op.
- Deletion of `scripts/scan-email.py` — S02. S01 leaves it untouched; the new `wiki collect email` runs in parallel.

## Done when

All 7 tasks `[x]` and the four verification commands pass.

## Notes

(Append observations during execution. Anything load-bearing → DECISIONS.md or KNOWLEDGE.md.)
