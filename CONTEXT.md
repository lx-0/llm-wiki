# CONTEXT.md — Domain + Architecture Glossary

The vocabulary used across this codebase. Single source of truth for naming. New code MUST use these terms; if you're tempted to invent a synonym, update this file instead.

Ordered roughly: domain-level concepts first, architecture concepts second.

## Domain

### Substrate

A source of raw personal data — mailbox, calendar, browser history/bookmarks, screenshots, tabs, agent-memory store, web clippings, NAS exports, manual notes. Each substrate produces material that may flow into `<vault>/raw/` (see [docs/concept.md](docs/concept.md)). Some substrates are referenced (mailbox bodies stay in IMAP; only metadata reaches `raw/`); others are owned (web clippings + audio + papers + agent-memory snapshots have copies stored in `raw/`). The split is deliberate; see [docs/concept.md § Storage rules](docs/concept.md).

### Collector

The substrate-specific module that turns a substrate into `raw/` files. One Collector per substrate, not per backend. `EmailCollector` covers all mailbox backends; `BrowserCollector` covers Firefox + Chrome; etc. Implementation: `scripts/collectors/<name>.py`. Discovered at runtime via [Registry](#registry).

### Substrate-with-accounts

A substrate where one operator has multiple identities. Email and calendar are account-substrates: `CONFIG.personal.accounts.<id>` lists each. Browser, screenshots, tabs are not — they're singletons.

### Account.kind

The discriminator that maps an `accounts.<id>` entry to concrete [Reader](#reader) and [Filter](#filter) adapters. CONFIG schema:

```yaml
personal:
  accounts:
    work:
      email: x@example.com
      reader: { kind: thunderbird-mbox, mbox_paths: [...] }
      filter: { kind: all-inkl-procmail, ... }
    private:
      email: y@gmail.com
      reader: { kind: gmail-api, oauth_token_env: GMAIL_OAUTH }
      filter: { kind: gmail-api, ... }
```

`reader.kind` and `filter.kind` are independent — an account can read via one backend and write rules via another (the legacy "Thunderbird mbox + All-Inkl Procmail" hybrid is exactly this).

### Domain types

The Python types that flow through the engine — neither adapter-specific nor collector-specific. Live in `scripts/domain/mail.py` (and future `scripts/domain/<substrate>.py`):

- `MessageMeta` — frozen dataclass: id, account_id, folder, from_addr, to_addrs, subject, date, size_bytes, in_reply_to, message_id
- `Message` — `MessageMeta` + body_text, body_html, attachment_filenames
- `FilterRule` — name + `FilterCondition` + `FilterAction`
- `FilterCondition` — from_addrs, subject_contains, body_contains (all OR-combined)
- `FilterAction` — kind (move|tag|flag|delete) + target

Adapters import from `domain/`; the reverse import is forbidden.

### Producer

A module that consumes a *compiled* knowledge source (a file under `<vault>/raw/` that has already been turned into a wiki article by `compile.py`) and emits **derived material** somewhere else — suggestion notes, knowledge-gap requests, third-party belief extractions. Mirrors [Collector](#collector) but operates on the **opposite side** of the engine:

| | Collector | Producer |
|---|---|---|
| Reads from | outside the vault (mailbox, browser, calendar, …) | inside the vault (a just-compiled source file) |
| Writes to | `<vault>/raw/<subfolder>/` | `<vault>/raw/requests/`, `<vault>/raw/suggestions/`, `<vault>/knowledge/takes/` |
| Trigger | `wiki collect` / piggyback after flush | per-source post-pass inside compile.py's loop |
| CLI verb | `wiki collect <name>` | `wiki produce <name> <source>` |

Today's Producers: `suggestions` (email-source action items via Claude SDK), `curiosity` (knowledge-gap requests via Ollama gemma4), `takes` (third-party belief extraction via Claude SDK, M011). Implementation: `scripts/producers/<name>.py`. Discovered at runtime via [ProducerRegistry](#producerregistry).

Disambiguation: DECISIONS.md occasionally uses lowercase "producer" loosely (e.g. "dashboard_stats.py is the producer of the dashboard cache"). The capitalized term is the concept defined here.

### ProducerSpec

The static declaration on each Producer class — `name`, `enabled_config_key`, `source_glob_config_key`. Drives ProducerRegistry queries + per-source gate checks + CLI dispatch. Parallel to [CollectorSpec](#collectorspec).

```python
@dataclass(frozen=True)
class ProducerSpec:
    name: str
    enabled_config_key: str | None       # e.g. "features.extract_takes"; None = always on
    source_glob_config_key: str | None   # e.g. "limits.extract_takes_source_globs"; None = every source
```

Both gates are evaluated by the **orchestrator** (compile.py's post-pass loop), not by the Producer. Producers do not duplicate gate-check code internally — they assume that if `run()` is called, the gates passed.

### ProducerResult

What `Producer.run()` returns. Replaces today's `None`-returning shape so per-source aggregation, cost reporting, and end-of-run summaries become possible.

```python
@dataclass(frozen=True)
class ProducerResult:
    producer: str                        # SPEC.name
    status: Literal["ok", "skipped", "failed"]
    reason: str | None                   # why skipped/failed (None when ok)
    outputs: tuple[Path, ...]            # files written
```

Failure contract: a `failed` Producer **never blocks** the compile-source state save. The orchestrator wraps each `Producer.run()` in a try/except, logs the result, marks the Producer failed for this source, and proceeds. Quiet bug it prevents: a curiosity-pass crash today silently skips the per-file state save (state save is after all three `await`s), causing the next compile run to re-spend Claude SDK tokens recompiling the same source.

### Preprocessor

A module that normalizes material already **inside** the vault (the `inbox/` drop-zone, the Obsidian Web Clipper `Clippings/` folder, or a single HTML file/URL) into the `raw/**` shape the compile loop reads. Runs BEFORE compile, whereas a [Producer](#producer) runs after it. Distinct from a [Collector](#collector): a Collector reads a [Substrate](#substrate) from OUTSIDE the vault (mailbox, calendar, browser); a Preprocessor only reshapes locally-staged material. Preprocessors are singletons (no `accounts.<id>` fan-out), so the seam is lighter than the Collector one — no Reader/Filter split. Implementation: `scripts/preprocessors/<name>.py`, discovered at runtime via the PreprocessorRegistry. Today: `inbox`, `html`, `clippings`. (The `html` module file is `html_ingest.py`, not `html.py`, to avoid shadowing the stdlib `html` package when `cli.py` runs directly.)

Parallel machinery, mirroring the Producer family: **PreprocessorSpec** — static declaration per class (`name`, `output_subfolder`, `takes_source`; `takes_source=True` means `run()` requires a `source` path/URL argument, e.g. `html`; `False` for the folder-sweep singletons `inbox`/`clippings` that scan a fixed staging dir). **PreprocessResult** — what `run()` returns (`files_written`, `files_skipped`, `message`, `errors`), parallel to RunResult / ProducerResult. **PreprocessorRegistry** — same `@register` / `all_preprocessors` / `get_preprocessor` shape as [Registry](#registry) and [ProducerRegistry](#producerregistry), kept separate because preprocessors have a distinct lifecycle (pre-compile, singletons, no CONFIG account tree). Operator surface: `wiki preprocess --list | <name> [source]`.

### Compile route

The discriminated decision `decide_route(source, content) → Route` makes about a single source **before any I/O or LLM call**. Pure: depends only on source path + content + CONFIG, so the dispatch-table lookup (`SUBSTRATE_PROMPTS` / `_DEFAULT_DISPATCH`, which pin model + max_turns per substrate — since C13/2026-07-18 there are no config-side escalation tiers) becomes one table-testable function. Variants:

```python
Route = (
    Skip(reason: str)                              # empty / final-only / substrate-skip-list
    | IndexOnly(title: str, wikilinks: list[str])  # source-and-final: indexed, not distilled
    | HealthStub()                                 # health-rollup metric stub: recorded deterministically, no agent
    | Compile(metadata: CompileMetadata,           # needs an LLM call
              classification: Classification)      # single vs aggregated-memory chunking, from classify()
)
```

`decide_route` runs all the *pure* pre-LLM logic — `infer_compile_role`, skip-list check, the dispatch-table lookup (`SUBSTRATE_PROMPTS` / `_DEFAULT_DISPATCH`), and `classify()`. The `Compile` variant also carries `dispatch_key` (the resolved `SUBSTRATE_PROMPTS` key), so execution-side logging never re-derives the routing decision. The **memory pre-pass** (`resolve_project_slug` + `ensure_timeline_section`, which writes a `## Timeline` section) is *not* part of the decision — it does I/O, so it lives on the execution side inside the `Compile` handler.

### CompileOutcome

What `compile_file()` returns — one typed result per source, replacing the legacy magic-key dict (`{"_skipped": …}` / `{"_failure": …}` / usage-dict). Mirrors CompileResult and ProducerResult so end-of-run aggregation reads uniformly.

```python
@dataclass(frozen=True)
class CompileOutcome:
    status: Literal["compiled", "skipped", "failed"]
    skip_reason: str | None = None
    failure_kind: str | None = None     # string (not a FailureClass object), like CompileResult
    failure_detail: str | None = None
    ingest_hash: bool = False           # main() persists state[ingested][rel]=hash iff True
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    article: str | None = None   # agent's final text, forwarded to run_post_passes
```

`failure_kind`/`failure_detail` are strings (not a `FailureClass` object) — same choice as `CompileResult`, keeping the type free of a `core.sdk_helpers` import; `main()` reconstructs `FailureClass` when it needs the consecutive-failure abort heuristic. `ingest_hash` replaces the `_STATE_MUTATING_SKIPS` registry: execution handlers no longer self-persist state. `main()` is the **single state-save site**, persisting the ingested-hash iff the outcome asks for it — the same way the LLM success path already works.

### DreamOutcome

The typed per-entity result of `dream_entity()`, mirroring [CompileOutcome](#compileoutcome). Carries entity + corpus stats + tokens/cost and a `kind` string (`None` = synthesized; else a skip kind in `_DREAM_SKIP_KINDS` or a failure kind in `_DREAM_FAILURE_KINDS`). `status` / `failed` / `exit_code` are derived properties; the module-level `dream_exit_code()` maps one outcome or a batch to the single CLI exit code, so the entity/sweep/piggyback branches can never diverge again (`per_call_timeout` → 6, `prompt_too_large` → 3, `sdk_failure` → 4, uniform on every path).

### SweepCandidate

One entity with every dream-sweep-selection gate verdict (priority, source, age_days, `cooldown_active`, `backoff_active`, `excluded`, weight) resolved once by `build_sweep_candidates()`. The single source of truth both consumers read: `dream_all_entities` filters on cooldown + backoff and applies selection jitter; `wiki dream list-candidates` renders the full row — so the operator debug view surfaces the insufficient-corpus backoff it was previously blind to.

### Reports vocabulary (M019 analytical surface)

- **InferenceConfig** — the parsed `inference:` section of an instrument.yaml (enabled, min_confidence, bandable_coverage_pct, default_lookback_days, max_curiosity_per_run, optional model override), surfaced on `InstrumentMeta` by `load_instrument`. Downstream (runner, audit probe) reads it off the loaded instrument instead of re-parsing raw yaml; missing keys fall back to dataclass defaults.
- **Concern band** — a cutoffs.yaml band flagged `concern: true`, marking it clinically elevated. Surfaced as `Instrument.concern_bands` and written into per-instrument report frontmatter; the meta-report raises a flag when an instrument's current band is in this set. Replaces the old hardcoded `severe_bands` dict.
- **Substrate-scope seam** — `scripts/reports/_engine/substrate_scope.py`: the module owning which of the operator's substrate an inference run may read (`CLINICAL_DEFAULT_SUBSTRATE_GLOBS` + `resolve_substrate_files`). The privacy boundary of the reports feature; both the production runner and the audit probe import it (the probe imports production, never the reverse).
- **schema_invalid** — a `FailureClass.kind` minted for malformed-agent-output inference failures (JSON that won't parse/validate), so inference retryability is a pure function of `failure.kind` rather than a substring match on the error message. Retryable alongside `cli_crash` and `unknown`.

## Architecture

This codebase uses the [improve-codebase-architecture skill's vocabulary](https://skills.gooseworks.ai). Key terms below; full reference in that skill's `LANGUAGE.md`.

### Module

Anything with an interface and an implementation. Functions, classes, packages, slices.

### Interface

Everything a caller must know to use a module: types, invariants, error modes, ordering, config — not just the type signature.

### Depth

Leverage at the interface. Deep = a lot of behavior behind a small interface. Shallow = interface nearly as complex as the implementation.

### Seam

Where an interface lives. A place behavior can be altered without editing in place. Use this term, not "boundary."

### Adapter

A concrete thing satisfying an interface at a seam. Each [Reader](#reader) implementation is an adapter. Each [Filter](#filter) implementation is an adapter.

### Reader

The read-side mailbox seam. Stateless `Protocol` (Python). Methods: `list_folders()`, `scan_metadata(folder, since)`, `scan_deep(folder, limit, since)`. Adapters: `ThunderbirdMboxReader`, `GmailReader`, `ImapReader`. Defined in `scripts/adapters/mailbox/base.py`. Account → Reader resolution lives in `scripts/adapters/mailbox/__init__.py:resolve_reader()`.

### Filter

The write-side mailbox seam. Stateless `Protocol`. Methods: `apply(rule, dry_run)`, `list_existing()`. Adapters: `ThunderbirdMsgFilter`, `GmailFilter`, `AllInklProcmailFilter`. Same module + resolution pattern as [Reader](#reader).

The Read and Filter seams are **independent** — a Reader and a Filter for the same account-id can be different kinds (legacy: read Thunderbird mbox, write All-Inkl Procmail).

### Registry

The auto-discovery layer for [Collectors](#collector). `scripts/collectors/base.py` exports a `@register` decorator; each `scripts/collectors/<name>.py` registers its Collector class on import. `scripts/collectors/__init__.py` imports all submodules to trigger registration. `flush.py:piggyback_collectors()` and the `wiki collect` CLI both consume `Registry.all_collectors()`.

### ProducerRegistry

The auto-discovery layer for [Producers](#producer). Same shape as [Registry](#registry) but parallel — Producers live in `scripts/producers/`, register via their own `@register` decorator, and are consumed by `compile.py`'s post-pass loop + the `wiki produce` CLI. Kept separate (not merged into Registry) because Collectors and Producers have different lifecycles, different config trees, and different CLI verbs — conflating them creates the misnomer trap that `core/piggybacks.py:_BUILTIN_PIGGYBACK_TASKS` (né `flush.py:_LEGACY_PIGGYBACK_COMMANDS`) fell into before its 2026-07-18 rename: most entries were deliberate non-Collector tasks, not unported legacy.

Registration order **is** run order. Today's order is preserved across the refactor: suggestions → curiosity → takes (matches the historical `await` sequence in `compile.py:1272-1281`).

### CollectorSpec

The static declaration on each Collector class — `name`, `output_subfolder`, `piggyback_default`, `piggyback_cooldown_hours`, `supports_incremental`, `supports_account_loop`. Drives Registry queries + piggyback discovery + CLI dispatch. `supports_account_loop` is load-bearing since 0.3.0: `collectors/cli.py` reads it to decide whether `wiki collect --account <id>` is honorable (forwarded to `run()`) or an operator error (exit 1) — it was previously declarative-only with zero readers.

### Account-loop harness

The shared per-account orchestration seam in `scripts/collectors/base.py` (`resolve_accounts`, `filter_accounts`, `migrate_flat_state`, [Watermark](#watermark), `run_account_loop`). It owns the cross-account concerns the kind-discriminated collectors used to hand-replicate: the kind-dispatch resolver, the `--account` filter, per-account failure isolation with ` · ` message aggregation, and the save-if-touched signal. Payload-generic (each collector returns its own per-account payload) and never normalises state-file shapes on disk — those stay decision-locked per substrate. CONFIG-free: it takes the accounts mapping as a parameter so each collector's own monkeypatched `CONFIG` still wins in tests. Consumers: gmeet, jamie, calendar, health; email adopts only `filter_accounts` (DECISIONS 2026-07-18 — it is the original pattern, not a copy).

### Watermark

A typed monotonic high-water mark (`base.Watermark`) encoding the advance-on-success / hold-on-failure contract. Seed it with the stored value, feed candidates via `observe` (None ignored, ISO-8601 string compare), then persist `value` iff `advanced`. Hold-on-failure is structural: a collector that returns early on a scan failure never reaches the persist step, so the mark stays put. Replaces the `highest is None or str(x) > str(highest)` blocks gmeet/jamie/health each re-typed.

### Inbox-intake harness

The shared two-zone folder-watch seam in `collectors/base.py` (`scan_inbox`, `archive_to_zone`, `append_rollup`) used by the voice/capture/pictures trio. `scan_inbox` filters a watched inbox by suffix and sorts by mtime; `archive_to_zone` moves a processed source into the vault audit zone with the mtime-suffix collision policy (the archive-move IS the per-source dedup); `append_rollup` writes a daily-rollup line and swallows failures (the rollup is a side-effect, never fatal).

### Frontmatter grammar

The single parse/write seam for leading YAML frontmatter blocks: `scripts/core/frontmatter.py`. One documented tolerance policy (EOF fence, trailing fence spaces, CRLF; malformed/non-dict YAML degrades to `{}` in tolerant mode, raises `FrontmatterError` in strict mode). Hot paths use the regex-only `field()` accessor (no yaml import); write-anew goes through `write()`/`serialize()`, single-key updates through `update_fields()` (surgical line-replace per DECISIONS 2026-05-15). New code MUST NOT hand-roll a `startswith("---")` parser — that is how the compile router and classifier came to read different `type:` answers from the same bytes.

### Sentinel region

A span of text bracketed by a `begin` marker and an `end` marker (e.g. `<!-- backlinks:begin --> … <!-- backlinks:end -->`). Engine passes own such a region so they can insert/replace it idempotently on re-run while operator/compiler text OUTSIDE the markers survives untouched. Located and spliced by `core.markers.find_region` (the single primitive, with `replace_region` / `ensure_region` / `strip_region` on top), which defines behaviour for missing (None), reversed/end-before-begin (None — never a corrupting splice), and duplicated (first begin + first end after it) markers.

### replace_block

The fourth flock-protected write form on `core.daily_capture` (alongside `append` / `append_with_source` / `replace_section`): insert-or-replace of one sentinel-keyed block inside `daily/<date>/<source>.md`, keyed by its begin/end markers. This is how the sessions hook writes `daily/<date>/sessions.md` — each session owns one `<!-- wiki:session <id> begin/end -->` region, replaced in place on re-flush — restoring the one-writer-per-(date,source) invariant for the last bypassing source.

### StateStore

The locked/atomic JSON state seam, `scripts/core/state_store.py`. One home for the flock primitives (`locked` / `try_locked` / `acquire_process_lock`), the `state.json` **merge-under-lock** writer (`update_state`: every writer takes a fresh disk read under an exclusive flock, mutates only the keys it OWNS, saves atomically — replacing whole-dict last-writer-wins saves), and a load-once/locked-update facade class for hot side-state files (dream-activation, insufficient-corpus). Reading state stays in `core.utils`; every WRITE path belongs here or goes through the atomic `core.utils.save_json_state` (tmp + `os.replace`).

### Ingested ledger

The `state.json` `ingested` map: ROOT_DIR-relative path → plain 16-hex content hash (legacy `{"hash": …}` dict values tolerated). Its schema lives ONLY in `core.state_store` (`ingested_ledger` / `is_ingested` / `pending_paths`); consumers (`compile.select_files`, `dashboard_stats.list_pending_compiles`, `flush.maybe_trigger_compile`) never re-derive it — a hand-rolled copy in flush drifted and went silently dead.

### Swallow

The labeled intentional-suppression seam: `core.errors.swallow(label, *, level, logger)`. A ContextDecorator that suppresses `Exception` (never `KeyboardInterrupt`/`SystemExit`) and logs one labeled line per suppression, making suppression intent greppable (`grep -rn 'swallow('`). Default level WARNING (lands in the errors-only log archives); DEBUG for best-effort cleanup (`agen.aclose`, IMAP logout) and hot-loop per-item fallbacks. Not for boundaries with a richer contract — adapter seams raise typed errors, SDK calls route through `core.sdk_helpers`, collector/producer boundaries log + return typed results. Decision tree: AGENTS.md § Exception handling.

### run_sdk_query / SdkRunResult

The one Claude-SDK call harness in `core/sdk_helpers.py` and its typed outcome. Never raises for SDK failures; returns `failure: FailureClass | None` so callers keep retry/skip/abort policy. Carries token counts on BOTH bases: `input_tokens`/`output_tokens` cache-inclusive (LEDGER basis, `ResultMessage.usage` preferred) and `uncached_*` raw per-turn sums (runaway-budget basis, DECISIONS 2026-06-02). Records to LEDGER on every outcome, including partial spend from timeouts and crashes.

### SdkCallSpec

The per-site policy declaration for one Claude-SDK call through `run_sdk_query`: label/logger, model, cwd, max_turns, system_prompt, allowed/disallowed tools, permission_mode, setting_sources, write scope, stall timeout, provenance. The harness unifies **mechanics, not policy** — every knob that differs between call sites lives here, caller-owned (DECISIONS 2026-05-04 honored inside the 2026-07-18 reopening).

### WriteScope

The path-scope declaration a call site hands to the harness for agent Write/Edit: `roots` (allowed), `denied_subpaths` (deny-precedence carve-outs like `knowledge/facts/`), and optional `legacy_allowed_tools` (the pre-hook glob rollback shape, active only when `features.compile_callback_gate` is off). The harness turns it into the PreToolUse Write|Edit hook wiring every site previously hand-assembled; `deny_all_writes` reproduces the M019 wedge exactly.

### Config schema

The side-effect-free module `scripts/core/config_schema.py` holding every knob's name, type, default, and documentation comment. Single source of truth with three consumers: `core.config` (builds the runtime CONFIG singleton and owns the side effects: dotenv, YAML read, TIMEZONE), the config-key migration (derives injected values; policy names live in `INJECTED_KEYS`/`NEVER_INJECTED`), and `core.config_docs` (generates the docs/config.md tables and sync-checks config.example.yaml). Adding a knob without a migration policy entry fails the suite.

### Command table (CLI dispatcher)

The `CommandSpec` table in `scripts/cli.py` is the single source of truth for the `wiki` command catalog: each row declares name, group, one-line summary, dispatch kind (py/bash/auth), handler script, banner, refresh-after, needs-vault, and the rich per-command help. `wiki help` renders from it, `menu.py`'s coverage is test-pinned against it, and the bash `wiki` entry-point delegates every Python-backed subcommand to it. The bash layer owns only bootstrap (symlink resolution + fail-closed vault guard + TTY detection) and the genuinely-bash commands. The dispatcher runs each handler as a child process, and owns the once-per-command dashboard refresh through flush.py's fcntl lock.

### SubRoute

A first-arg-selected alternate handler within a single `wiki` command: the selecting token is consumed and the rest of the argv passes through. Used by `wiki correct apply` (→ `facts/correct_apply.py`, with its own banner) and `wiki backfill <kind>` (→ the matching `backfill_*.py`). Defined on `CommandSpec.subroutes` in `scripts/cli.py`.

### Machine-readable seam

A `--json` (or `--progress-json`) output mode on a CLI surface consumed by the desktop app or agents, following the `wiki doctor --json` / `wiki menu --json` precedent. The human table/log stays the operator surface and may change wording freely; the JSON payload is the stable contract GUI/agent consumers parse. All four desktop-consumed pipeline surfaces expose one: `wiki collect --list --json`, `wiki triage list --json`, `wiki query --json`, and `wiki compile --progress-json` — the latter emitting flushed `PROGRESS {"current": i, "total": n}` stdout lines at batch start and per compiled file.

### runWiki

The single seam between the desktop app and the vault's `wiki` CLI (`desktop/src/vault/wiki-exec.ts`). `runWiki(args, {parse, timeout, onLine}) → WikiResult` owns vault resolution, PATH augmentation, spawn, stdout/stderr collection, ANSI stripping, JSON-parse-with-fallback, a SIGTERM-then-SIGKILL timeout, and error normalization. **WikiResult** is the normalized outcome (`{ ok, code, stdout, stderr, durationMs, data, error }`); `runWiki` resolves (never rejects) — all failures surface via a typed error (`no-vault` | `spawn-failed` | `timeout`) + `ok:false`. Its `collectChild` core is split out to be unit-testable with a fake child; the six former per-module spawn sites (compile/collectors/query/triage/doctor/menu) collapse to args + a small parse on top.

### LintContext

The corpus model of a lint run, built once per run by `lint.build_context`: canonical article enumeration (`core.utils.list_wiki_articles` → `core.links.iter_articles`, recursive, includes `knowledge/MOCs/`), parsed frontmatter (`core.frontmatter`), stripped bodies, footer-aware outgoing slugs (`links.outgoing_canonical_slugs`), and the derived inbound map. Every structural check is a pure function `check(ctx) → list[Issue]`; the builder is the single legal place for a corpus pass (the 2026-05-30 one-O(N)-pass rule lives there).

### Issue

One lint finding: frozen dataclass (severity, check, file, detail, auto_fixable) plus structured payload fields `fact_slug` / `target_slug` that consumers (reconcile, dashboard renderers) key on. The `detail` prose is display-only and is never parsed — prose-scraping consumers were the source of the shipped NFD-umlaut truncation bug.

### retarget_links

THE wikilink rewriter in `core.links`, used by every retargeting flow (`rename_article`, `links_audit --fix`, `dedup` merge). Masks frontmatter and code fences, preserves embed-bang/`#anchor`/`\|`/`|alias` decorations. Matching policy (resolve-to-file vs literal-by-string) and walker policy (index.md in or out) stay caller-side — deliberate per-flow differences, not drift.

### Graceful agnostic

Design rule: a Collector / Adapter whose required CONFIG keys are empty MUST `is_configured() → False` and be silently skipped, NOT crash. Examples: `EmailCollector` with zero accounts whose Reader-kind resolves; `BrowserCollector` with neither `firefox_profile` nor Chrome paths set. Empty config → empty work, no error.

## Out of scope (for now)

- Multi-vault ingest (one engine writing to N vaults).
- Concurrent collector execution. Sequential is the contract; parallelism is implementation-side, not interface-side.
- Adapters for substrates without an `accounts.<id>` entry. Browser/calendar/etc. don't get the Reader+Filter pattern (they're singletons).
