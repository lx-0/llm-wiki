# Lift `jamie` to multi-tenant — `personal.accounts.<id>.jamie` with `kind: jamie-api`

**Status: DONE 2026-05-15** — shipped same-day as the gmeet lift / architecture policy.
`JamieConfig` + `Personal.jamie` removed from `core/config.py`; `_resolve_jamie_accounts()`
+ `_JamieAccount` dataclass + per-account `_run_one_account()` loop in `collectors/jamie.py`;
`SPEC.supports_account_loop = True`; per-account state migration (legacy flat `last_seen_ts`
→ `state["default"]["last_seen_ts"]`). `config.example.yaml` per-account `jamie:` example
landed alongside `gmeet:`. `docs/cli.md` + `docs/config.md` flipped to multi-tenant.
204/204 pass. Architecture policy fully applied — no flat `personal.<service>` blocks
remain for account-bound collectors.

Original scope kept below for reference / history.

---

**Priority:** P2 — not a live bug today (jamie is single-Jamie-account in practice for the
operator), but the **architecture policy** locked on 2026-05-15 says account-bound
collectors must be multi-tenant from day one. Jamie is the last flat hold-out.

**Origin:** 2026-05-15. The gmeet multi-tenant lift commit established the policy
(DECISIONS.md "2026-05-15: Architecture policy — account-bound collectors/adapters
multi-tenant from day one") and lifted gmeet retroactively. Jamie was deliberately
left out of that commit so it stayed focused on the immediately-blocking gmeet case.

## Scope

Mirror the gmeet lift exactly:

- **`scripts/core/config.py`**: drop `JamieConfig` dataclass + `Personal.jamie` field.
  Keep the `Limits.jamie_*` knobs (they're shared default-cap state, not per-account
  identity). Update the `# NOTE: jamie is still flat` comment that the gmeet lift
  left behind — once jamie is lifted, that comment goes too.
- **`scripts/collectors/jamie.py`**: add `_JamieAccount` dataclass +
  `_resolve_jamie_accounts()` reading `CONFIG.personal.accounts.<id>.jamie` with
  `kind == "jamie-api"`. Per-account fields: `api_key_env`, `key_type`
  (`personal`|`workspace`), `since`, `max_per_run`, `account_id` (optional cosmetic
  override; defaults to the `<id>` key). Refactor `JamieCollector.__init__` /
  `run()` to loop over accounts the same way `gmeet.py:_run_one_account` does.
  `SPEC.supports_account_loop = True`. Per-account state keys in
  `state/jamie-state.json`: `{<account_id>: {last_seen_ts: ...}}` with a one-shot
  legacy-flat (`{last_seen_ts: ...}`) → `state["default"]["last_seen_ts"]`
  migration on first read.
- **`config.example.yaml`**: drop the `personal.jamie:` flat block; add a `jamie:`
  sub-block to one of the account examples (analogous to the gmeet sub-block):
  ```yaml
  jamie:
    kind: jamie-api
    api_key_env: JAMIE_API_KEY              # env var holding the jk_... key
    key_type: personal                      # personal | workspace
    since: ""                               # ISO date backfill cap; empty = no cap
    max_per_run: null                       # null = inherit CONFIG.limits.jamie_max_per_run
  ```
  Update the `accounts:` section header comment to list `jamie?` alongside
  `reader?`/`filter?`/`gmeet?`.
- **lxw vault `config.yaml`**: post-lift, the operator moves their `personal.jamie`
  block under whichever account owns that Jamie subscription (probably a new
  account-id like `jamie-lxw` if it doesn't map to an existing email account).
  Document the migration in the commit body.
- **Docs**: PROCESS.md scanner-table row for `collectors/jamie.py` updated to note
  multi-tenant; AGENTS.md `raw/transcripts/jamie/` line untouched (no path change).

## Edge cases / failure modes

- **Empty `personal.accounts`**: `is_configured()` returns False, piggyback skips —
  same graceful-agnostic contract as gmeet.
- **Account has `jamie:` sub-block but no `api_key_env` set / env var unset**: the
  per-account scan returns "no api key" without aborting other accounts. Mirror
  gmeet's per-account `try/except` shape.
- **State migration**: legacy `state/jamie-state.json` with flat `last_seen_ts` →
  bucket under `state["default"]["last_seen_ts"]` on first read (matches the
  gmeet migration). Lxw operator's existing watermark is preserved.

## Done when

`personal.jamie` is gone from `core/config.py`; `JamieCollector` enumerates
accounts; full suite green; lxw `config.yaml` migrated. The `# NOTE: jamie is
still flat` comment in `Personal.jamie`'s former neighbourhood is also removed.
