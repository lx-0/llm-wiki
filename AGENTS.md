# AGENTS.md

Conventions for whoever changes this repo — AI coding agents and human contributors. What the engine does, feature by feature, lives in `docs/` (`FEATURES.md` per feature, `cli.md` per command, `config.md` per knob, `engine-layout.md` per file); this file holds the rules a change must keep.

## Contents

- **Before any change:** [What this repo is](#what-this-repo-is) · [Repo layout](#repo-layout) · [Style](#style) · [When in doubt](#when-in-doubt)
- **Adding something:** [a tunable](#adding-a-tunable) · [personal data](#adding-per-instance--personal-data) · [a seedable config](#adding-a-seedable-config-drift--overlay-rules) · [a prompt](#adding-a-prompt) · [an agent target](#adding-an-agent-target-for-hook-install) · [an intake channel](#evaluating-a-new-intake-channel)
- **Changing compile or the articles:** [author attribution](#frontmatter--author-attribution) · [`compile_role`](#frontmatter--compile_role-axis-m007) · [wikilinks](#wikilinks-relative-to-file-convention) · [feature invariants](#feature-invariants) · [the SDK and substrate](#spawning-claude-agent-sdk-with-substrate-input-hard-rule-locked-2026-05-15)
- **Changing the plumbing:** [a `--json` payload](#changing-a---json-payload-menu--doctor) · [paths](#path-handling) · [the Python environment](#python-environment) · [YAML & JSON](#yaml--json) · [side effects](#side-effects) · [exceptions](#exception-handling-decision-tree)

## What this repo is

The **engine** of an LLM Wiki — a Karpathy-pattern personal knowledge base. The repo is not a vault; it's the code that runs inside one, installed as `<vault>/.wiki/`. A vault has four layers:

1. **`raw/`** — curated sources: the LLM reads, never writes. Collectors write per-substrate subfolders (`raw/notes/<substrate>/`, `raw/transcripts/{jamie,gmeet,wispr}/`, `raw/voice/`, `raw/captures/`, `raw/index/`); each collector's output shape is its row in `docs/FEATURES.md` and in `docs/PROCESS.md`'s scanner table. Mobile intake archives its sources under `raw/inbox-mobile/` (two-zone intake, M022).
2. **`daily/`** — the per-day rollup. `daily/<date>/<source>.md` is append-only with exactly one writer per source, through `core.daily_capture` (fcntl-locked, `KNOWN_SOURCES`-validated); provenance back to `raw/` lives in a `sources:` frontmatter list, never an in-body `[[…]]` link (Obsidian ignores `raw/`, so a body link renders dead). `daily/<date>.md` is the compile-stage digest (≤ 500 words) the `daily-digest` agent distils; lint's `check_daily_consistency` holds the two shapes together.
3. **`knowledge/`** — the compiled wiki: the LLM owns it, the human reads it. Atomic articles (`concept | connection | qa | moc | fact`) and two-layer entity pages (`person | project`, M005: a State block above `---` with `## State`, `## Action Items` in Obsidian-Tasks syntax, `## Open Threads`; an append-only `## Timeline` below), enforced by lint. `facts/` is human-owned through `wiki correct` and overrides every source. `concepts/` and `qa/` carry a domain tag from `CONFIG.graph_view.domain_tags` (graph colouring; lint enforces it).
4. **`workspace/`** — the operator's working layer. The `intents` producer (gated off by default) files intake notes as `task | idea | note` into `workspace/inbox/`; accepting a task moves it to `workspace/tasks/<NNN>.md` and lists it in `workspace/todo.md`, and execution stays operator-gated (`orchestrate-tasks`). The three triage surfaces — `wiki triage`, the dashboard panel, `triage.html` — share one source of truth, the `status:`/`type:` frontmatter, pinned by `tests/test_triage_record_contract.py`.

The **vault's own `AGENTS.md`** (a separate file, seeded from `templates/AGENTS.example.md`) is the article schema the compiler embeds into every compile prompt. This file is for whoever changes the engine.

## Repo layout

```text
llm-wiki/                    ← installed as <vault>/.wiki/ — file by file: docs/engine-layout.md
├── wiki                     ← the bash bootstrap (≤ 150 lines, no library); every command goes to scripts/cli.py
├── scripts/                 ← the source root — NOT a package (§ Python environment)
│   ├── cli.py · cli_catalog.py · cli_help.py   ← the dispatcher, its one CommandSpec table, the help texts
│   ├── core/                ← shared plumbing, imported never invoked (paths, config, sdk_helpers, console, entry, …)
│   ├── collectors/ adapters/ domain/           ← substrate → raw/ writers (`wiki collect`), their clients, pure types
│   ├── preprocessors/ compile_stages/ producers/  ← pre-compile intake, the compile pipeline, post-compile extractors
│   ├── dashboard/ reports/_engine/ publish/ bridge/ migrations/ suggestions/ curiosity/ intents/ facts/
│   └── *.py                 ← top-level entry modules (compile, flush, query, lint, doctor, menu, dream, …)
├── hooks/                   ← agent hooks, plain scripts; _bootstrap.py is the engine's one sys.path bootstrap
├── prompts/ templates/ skills/  ← LLM prompts (.md, ${var}), the vault's seed files, engine skills
├── desktop/                 ← Electron menubar GUI (npm, not pnpm) — talks to the engine only through --json seams
├── tests/                   ← pytest (pythonpath = scripts + hooks); tests/golden/ = the behaviour oracle
└── docs/ · config.example.yaml · pyproject.toml + uv.lock · install.sh
```

## Conventions

### Adding a tunable

1. Extend the matching dataclass in `scripts/core/config_schema.py`, with a `#` comment above
   the field: that comment IS the documentation (`docs/config.md`'s Meaning column).
2. Document the default in `config.example.yaml`; `tests/test_config_docs.py` fails on a
   missing key or a non-default value.
3. Regenerate `docs/config.md`'s tables with `PYTHONPATH=scripts uv run python -m
   core.config_docs --write` (a drift test fails otherwise).
4. Replace the hardcoded constant in the script with `CONFIG.<section>.<field>`.
5. Don't add ad-hoc constants back to scripts — extend the config layer.
6. **Add the key NAME to `scripts/migrations/migrate_config_keys.py`**: `INJECTED_KEYS[<parent>]`
   (written into operator vaults, value from the schema) or `NEVER_INJECTED[<parent>]` (an
   explicit fall-through, e.g. secrets that belong in `.env`).
   `test_migrate_config_keys.py::test_every_schema_knob_has_a_migration_policy` fails until one
   carries it. Without injection the operator never sees the knob. Renames and removals extend
   `PIGGYBACK_RENAMES` / `KEY_DROPS` the same way. The migration is the only legal write path
   into an operator's `<vault>/.wiki/config.yaml`.

### Adding per-instance / personal data

Different rule for anything personal: email addresses, customer/partner names,
hostnames, mbox paths, project names mentioned in prompts, etc.

1. Extend `Personal` in `scripts/core/config.py`.
2. `config.example.yaml` ships an **empty** default for the field — never a real value.
3. The actual value goes in the user's local `config.yaml` (gitignored).
4. Consumers (prompts via `${var}`, compile.py schema enums, collector runtime maps) read
   `CONFIG.personal.*` and handle the empty case gracefully.
5. A value that drives both a prompt AND a schema enum is read by BOTH from `CONFIG.personal.*`
   (`email_folders`: `compile_curiosity.md`'s listing and `compile.py`'s schema `enum`).

### Frontmatter — author attribution

Source files may carry an optional `author: <name>` (or `author: [name1, name2]`) frontmatter key. When present, `compile.py` routes distilled beliefs/decisions/opinions to that person's `knowledge/people/<slug>.md` page. When absent, the compile prompt falls back to `personal.implicit_operator_author` (single-tenant convenience; null by default — multi-tenant vaults leave unattributed content generic). Explicit `author:` always wins.

`personal.implicit_operator_author` is also the **canonical vault-owner identifier**. When set, `compile.py:_build_owner_block()` renders a "## Operator / vault owner" section into every substrate compile prompt, naming the owner and pointing the agent at `knowledge/people/<slug>.md`, so the agent resolves self-references ("I", "we", "my company"). Null = no section rendered.

`knowledge/` articles may carry an optional `domain:` frontmatter key — a cross-cutting life-domain axis (default enum `company | personal | ai | meta`, extensible via `CONFIG.personal.domains`). Pure filter, never required; lint `check_domain_value` warns on values outside the enum; `wiki query --domain <value>` restricts an answer to it.

`personal.output_language` (default `"auto"`: the source material's language) pins the **output prose language** of compiled articles; code, identifiers, proper names and the structural section headers (`## State`, `## Timeline`, …) stay verbatim. It reaches every compile substrate prompt, the curiosity producer and dream-entity through `${output_language_instruction}` (`core.prompts.build_output_language_instruction`). Distinct from `personal.voice_transcribe_language` (input transcription). Issue #4.

### Frontmatter — `compile_role` axis (M007)

Any `.md` file in the vault may carry `compile_role:` — how `compile.py` treats it:

- **`source-only`** (the default for `raw/`, `daily/`, `inbox/`, `knowledge/`) — substrate, distilled into `knowledge/` articles.
- **`source-and-final`** — the page IS the final form (operator long-form, by convention under `raw/notes/longform/`): compile indexes it by pathname and marks it ingested, with no SDK call and no parallel `knowledge/concepts/<title>.md`. Cite it by pathname, never add it to `compiled_from:` (that key is for distilled substrate).
- **`final-only`** — engine-skip, hand-curated: hidden from MOC auto-includes (`WHERE compile_role != "final-only"`), dashboard counts and `wiki query`'s default scope (`--include-final-only`); `pin.py` refuses it.

Without the key the role is inferred from the top-level folder (`core.compile_role.LOCATION_DEFAULTS`, toggle `limits.compile_role_default_by_location`); explicit frontmatter wins, and lint `check_compile_role` rejects unknown values.

### Feature invariants

Each feature's behaviour, gates and knobs are its row in `docs/FEATURES.md`, its command in `docs/cli.md` and its keys in `docs/config.md` (dream priority's resolution order included). What a change to them must keep:

- **Tokens, never dollars.** Every LLM call records tokens per `(provider, model)` at its call site (`core/usage.py`; the Ollama client records itself, Claude SDK sites record `AssistantMessage.usage`); gates are token- or count-based (DECISIONS 2026-05-23).
- **Agents that edit the wiki get no Bash and a write scope.** `wiki reconcile` writes only `knowledge/concepts/`; `wiki correct apply` supersedes instead of deleting (deletion is opt-in behind a clean git tree) and proposes renames and deletions that the engine executes (M028, issue #5).
- **Web research never re-enters `raw/`.** `wiki dream web-research` writes only its sentinel block inside `knowledge/` (`run_web_research` refuses any other target); otherwise the compiler would re-synthesize web text as operator substrate.
- **Link rewrites go through `core.links`**, the one resolver (dedup merges, renames) — never a second hand-rolled rewriter.
- **Opt-in features stay double-gated off**: a `features.*` flag AND a `piggybacks.*` block (`concept_reconcile`, `health_trends`); `dream_web_research` is gated per vault and per entity.

### Adding a seedable config (drift + overlay rules)

`wiki seed` applies `templates/` into the vault. How a template file is handled depends on whether operators customise it:

- **Engine-owned (markdown/YAML — `AGENTS.md`, `dashboard.md`, `knowledge.base`):** whole-file (`seed_cli.Seeder.copy`; `core/seed.py:walk` lists every seeded file and how). Seed-if-missing, keep-if-exists, refresh with a targeted `wiki seed <path> --force`. Operators shouldn't hand-edit these; they're regenerated.
- **Customisable JSON configs (`graph.json`, `app.json`, plugin `data.json`):** route through `seed_cli.Seeder.overlay`. The engine owns the template (base); the operator's delta lives in an **untracked** overlay at `<vault>/.wiki/custom/<rel>`; the live file is derived as `template ⊕ overlay` (`core.seed.apply_overlay` / `derive`: an element-wise deep merge). This keeps the file engine-updatable (new keys flow in) while preserving customisations — operators edit the overlay, `--force` re-derives from template ⊕ overlay, `wiki seed --extract-custom <rel>` bootstraps an overlay from existing drift. An overlay only overrides: a key or array entry the operator removed, or a value cleared to `null`, comes back from the template on `--force` (`.ytstack/backlog/overlay-cannot-carry-deletions.md`). NEVER make a customisable config keep-or-`--force` whole-file — that recreates the force-vs-drift dilemma.
- **Accumulating lists (community-plugins, shell-commands, meta-bind buttons):** bespoke additive merges in `core/seed.py` (`union_list`, `merge_registry` by id, `env_appended`), preserving operator entries while adding/updating engine-managed ones.

Drift detection on the JSON configs is key-order-insensitive (the canonical `jq -S` form, `core.jqjson.canonical` in the port), so don't worry about Obsidian re-serialising key order. Copied files (markdown, html, css, yaml) compare byte for byte.

### Changing a `--json` payload (menu / doctor)

1. Change the `TypedDict` in `scripts/core/contracts.py` — the one definition the builders
   (`core/actions.py`, `core/health/`, `menu_context.py`, `doctor.py`) return.
2. Regenerate the schemas: `PYTHONPATH=scripts uv run python -m core.contracts --write`
   (the suite runs `--check` and validates the oracle goldens against them).
3. Bump `core.actions.SCHEMA` (and the `Literal` in `contracts.py`) when a consumer must learn
   the change — the desktop refuses a schema it does not know.

### Adding a prompt

1. Drop `<name>.md` into `prompts/`.
2. Use `${var}` for placeholders (not Python's `{var}` — JSON/YAML examples in prompts have literal braces).
3. Call `from prompts import render` and `prompt = render("name", var=value)`.

**Per-prompt model (Prompty-style frontmatter).** A prompt MAY open with a YAML frontmatter block declaring its model — e.g. `scan_pictures_vision.md` / `scan_screenshots_vision.md` pin `model: qwen2.5vl:7b` (strong local OCR) and `intent_classify.md` pins `model: claude-haiku-4-5` (cheap triage). `render()` strips the frontmatter from the body (it never reaches the LLM); the caller resolves the model with `prompt_model("<name>", <fallback>, …)` — **frontmatter `model:` wins, else the first truthy fallback** (caller default → config knob → `compile_model`). This puts the model choice next to the prompt it belongs to instead of hardcoded at the call site; config knobs (`models.vision_model`, `models.intent_classify_model`) remain the fallback. (Agent-task specs `prompts/agents/*.md` carry their own `model:` via `AgentSpec`, a separate parser.)

### Adding an agent target (for hook install)

1. Add an `Agent` to `AGENTS` in `scripts/core/agents.py`: name, detection dir, config file,
   its hooks (event, script, timeout in the agent's unit) and `flat=True` for Cursor-style
   bare entries. `wiki hooks`, `wiki status` and doctor's `hooks-installed` read it.
2. Record its payloads: `uv run pytest tests/test_agents_registry.py --snapshot-update`
   writes `tests/golden/agents/payload-<name>-*.json`. Read them and commit them with the
   agent; from then on a changed byte in an installed hook command fails a test.
3. Status table, install/uninstall flows, and detection logic pick it up automatically.

### Wikilinks (relative-to-file convention)

A link in a markdown file is relative to that file. Obsidian resolves a slash-bearing wikilink against the **vault root** (`<vault>/`, where `.obsidian/` lives), so the historic `[[concepts/foo]]` form — relative to `knowledge/`, not the article — pointed at the non-existent `<vault>/concepts/foo.md` and Obsidian offered to create an empty stub when clicked from a nested article. Links are now stored **relative to their containing article**: same-bucket `[[foo]]`, cross-bucket `[[../people/alex]]`, substrate `[[../../daily/2026-05-15.md]]`.

`core.links` is the single resolver (`resolve_link`, `canonical_slug`, `relativize_text`). When **authoring** links (prompts, `wiki pin`, hand-edits) use the unambiguous full-path form `[[knowledge/<type>/<slug>]]` or `[[daily/…]]`/`[[raw/…]]` — the `relativize_wikilinks` post-compile pass (gated by `features.relativize_wikilinks`, default on) rewrites every link to the correct relative path. Don't hand-compute `../`. `core.backlinks` renders footers relative; `lint` resolves source-relative. `index.md` is exempt (its links already resolve source-relative from `knowledge/`). One-off corpus migration: `scripts/migrations/relativize_wikilinks.py --vault <vault> --apply`.

### Path handling

Scripts use `Path(__file__).resolve().parent` for `SCRIPTS_DIR`, `.parent.parent` for `WIKI_DIR`, `.parent.parent.parent` for the vault root. After `install.sh` clones the repo into `<vault>/.wiki/`, this resolves correctly. Don't hardcode absolute paths.

**In a development checkout that last step is wrong by construction:** `ROOT_DIR` resolves to the directory *next to* the repo, so `DAILY_DIR`, `RAW_DIR`, `KNOWLEDGE_DIR` and the `_dashboard-*.md` targets point at the operator's filesystem. Consequences for anything you write:

- **Tests must never reach a `ROOT_DIR`-derived constant.** Monkeypatch it at the module that owns it — `core.daily_capture.DAILY_DIR`, not `core.paths.DAILY_DIR`, if that's where the write site reads it. `tests/conftest.py` repoints the known ones and a write guard (`tests/_vault_isolation.py`) raises `VaultWriteEscape` on anything that escapes the checkout, so a forgotten one is a red test rather than a silent leak.
- **Running engine scripts from the repo writes outside it.** `wiki flush`, dashboard regeneration and friends will happily create `<repo>/../_dashboard-*.md`. Exercise write paths against a real vault or a scratch one (`WIKI_VAULT`-style redirection), never from the checkout.

### Python environment

The Python venv lives at `<vault>/.wiki/.venv/` (inside the engine, NOT at the vault root). The first `wiki` call creates it (`install.sh` runs `wiki seed`), and the bootstrap re-syncs it whenever `uv.lock` or `pyproject.toml` is newer than its `.wiki-synced` stamp. **Exception — cloud-synced vaults** (iCloud Drive, `~/Library/CloudStorage`): the environment lives at `~/.venvs/<vault>-wiki`, addressed via `UV_PROJECT_ENVIRONMENT`, which the `wiki` bootstrap exports and the installed hook commands carry literally (rule: the bootstrap `wiki`, held with `wiki doctor`'s copy to one table in `tests/test_engine_env_location.py`; rationale: `docs/engine-layout.md` hard rule). On such a vault, run engine commands through `wiki …`; a bare `uv run --project .wiki` would rebuild an environment inside the cloud folder.

`scripts/` is the engine's source root, not a package (DECISIONS 2026-10-14; no `scripts/__init__.py`, ever — `tests/test_layout.py` guards it). Three ways to invoke engine code, and which one applies depends on where the module sits:

- **Through `wiki`** — `wiki <command>`. The dispatcher spawns the handler as `python -m <module>` with `scripts/` on `PYTHONPATH` (`core/entry.py` builds argv + env for every Python-side spawn). The operator-facing form; every documented command has one.
- **A top-level script by path** — `cd <vault>/.wiki && uv run python scripts/<X>.py <args>`, or from any CWD `uv run --project <vault>/.wiki python <vault>/.wiki/scripts/<X>.py <args>` (the bootstrap `wiki` runs `scripts/cli.py` by path, with the engine's environment; the hooks run `hooks/<x>.py` alike). Python puts a script's own directory first on `sys.path`, and for `scripts/<X>.py` that directory *is* the source root, so `core.*` imports resolve.
- **A sub-package module as a module** — `PYTHONPATH=<vault>/.wiki/scripts uv run --project <vault>/.wiki python -m <pkg>.<module> <args>` (`migrations.migrate_config_keys`, `core.config`, `collectors.cli`). Running such a file by path (`python scripts/collectors/scan_tabs.py`) fails with `ModuleNotFoundError: core`: the per-module `sys.path` bootstraps that once made it work are gone (M033-S02-T04), and the only bootstrap left is `hooks/_bootstrap.py`, for the hooks, which run as plain scripts from the agent harness. A package whose `__init__` imports its modules to register them (`preprocessors`, `producers`) double-imports such a module under `-m` (a `RuntimeWarning`); those commands get a top-level entry script instead (`process_inbox.py`, `ingest_html.py`). A collector module under `-m` would run as `__main__`, a second copy beside the one the registry imports by name (`collectors` itself imports none since M034-S06-T03), its `@register` included — hence `ingest_youtube.py` and `index_folders.py` — and a collector's own flags go through `wiki collect <name> -- <flags>` to its module's `main(argv)`. `tests/test_cli_dispatch.py` refuses a handler that reaches into such a package directly, `tests/test_layout.py` refuses a documented by-path invocation of a sub-package module.

`hooks/session-end.py` and `hooks/pre-compact.py` spawn `flush.py` with `--project` for the same reason. Anything that spawns engine code from outside `.wiki/` MUST pass `--project`, otherwise `uv` can't find `pyproject.toml`; anything that spawns a sub-package module MUST put `scripts/` on `PYTHONPATH` (`core.entry.python_m` + `child_env`; the bash bootstrap spawns no module, only `scripts/cli.py` by path).

### YAML & JSON

- **YAML editing in CLI** → goes through `config.py set` (Python with PyYAML). Bash never parses YAML.
- **JSON merge for agent configs** → `core.agents.merge` / `without_wiki_hooks` (they keep other tools' hooks); a backup through `core.backup` before every write.
- **LLM JSON output** → use `jsonrepair` or schema-constrained decoding (Ollama `format` field). Never raw `JSON.parse`.

### Side effects

- Hooks run in **<10s** budget — no API calls, only file I/O. Heavy work goes to spawned background processes (`flush.py`, piggybacks).
- `compile.py` and `query.py` use the Claude Agent SDK with `model=CONFIG.models.compile_model`. Other scripts use Ollama (configurable via `models.ollama_url`).
- Every config write makes a `.bak.YYYYMMDD-HHMMSS`. Idempotent install/uninstall.
- The engine writes **inside the vault and `.wiki/` only**, with one exception: when `skills.global_install` is on, `wiki skills install/sync` symlinks `use-llm-wiki` into `~/.claude/skills/` and records the vault root in `~/.config/llm-wiki/vaults` (the discovery registry the skill reads). Both writes fail soft — a missing global link is recoverable, a hard error on `wiki update` is not.

### Exception handling (decision tree)

The engine runs unattended — its dominant failure mode is the **silent skip**. A failure that
produces no log line is invisible by design, so bare `except Exception: pass` and unlogged
fallback-returns are banned. For every new `except Exception`, walk this tree top-down:

1. **Adapter seam** (mailbox / calendar / Drive reader or filter)? → raise a **typed error**
   (`MailboxReadError`, `DriveAPIError`, `CalendarAPIError`) with `from e`. The collector
   boundary catches, logs, and isolates it (`core watermark-on-failure` stays intact).
2. **Claude SDK call**? → route through `core.sdk_helpers` (`run_sdk_query`,
   `classify_failure` + `log_sdk_failure`). Never hand-roll SDK exception handling.
3. **Collector / Producer boundary** (one account, one source)? → `log.exception(...)` +
   return the typed result (`AccountLoopOutcome` error entry, `ProducerResult(status="failed")`,
   `RunResult(success=False)`, `CheckResult(severity="warning")`). One bad item never kills
   the loop, and never disappears either.
4. **Intentional suppression** (best-effort cleanup, observability write, per-item parse
   fallback)? → `with swallow("label")` from `core.errors` — context manager or decorator.
   The label makes the intent greppable and every suppression logs. Default
   `level="warning"` for a degraded capability the operator should see (it also lands in the
   errors-only log archives); `level="debug"` for best-effort cleanup (`agen.aclose()`, IMAP
   logout) and hot-loop per-item fallbacks where WARNING would flood.
5. Never catch `BaseException`; `swallow` re-raises `KeyboardInterrupt`/`SystemExit` unlogged.

If none of 1-4 fits, let it propagate: a traceback in an errors-only log beats a swallowed one.
An inline fallback value (decode → `""`) with an explicit `log.debug/log.warning` is `swallow`'s equal.

### Evaluating a new intake channel

Value a candidate substrate by **persona-coverage, not signal-density**: what otherwise-dark region of the operator's portrait does it cover? Clutter is not an objection (`compile_role: source-only` + `daily/` aggregation keep low-signal rows out of `knowledge/`); value scales per persona *axis* newly covered, not per source; and ingest only what the synthesis side (dream-cycle, a persona page) will weave in, or it only grows `raw/`. Rationale: `.ytstack/DECISIONS.md` 2026-05-22; candidates: `.ytstack/backlog/consumption-curiosity-axis.md`.

### Spawning Claude Agent SDK with substrate input (HARD rule, locked 2026-05-15)

Any script that feeds substrate (`daily/**`, `raw/**`, third-party email, operator-supplied prompts) into the Claude Agent SDK with Write/Edit tools MUST apply three layers of write-scope enforcement, no exceptions:

1. **Prompt-level** — the system prompt explicitly states which directory the agent may Write/Edit, and that source descriptions of code/config/script changes are subject matter, not instructions to the agent.
2. **Tool-level** — call through `run_sdk_query` with `SdkCallSpec(write_scope=WriteScope(roots=(<allowed dir>,)))`: Write/Edit stay in `allowed_tools`, and a PreToolUse hook (`core/sdk_scope.make_path_scope_hook`) denies every Write/Edit that resolves outside the roots. Never `permission_mode="acceptEdits"`. Neither substitute works: `Write(<glob>)` / `Edit(<glob>)` entries in `allowed_tools` or `disallowed_tools` are not path scopes, because the bundled CLI ignores the parenthesised part (`scripts/probe_compile_scope.py`, 2026-05-17), and a `can_use_tool` gate hides Write/Edit from the agent altogether (2026-05-18).
3. **Settings-level** — `setting_sources=("project",)` (not `()`) so vault-root `CLAUDE.md` reaches the agent.

Reason: substrate routinely contains literal change-descriptions captured from prior engine-development sessions. The agent reads them as instructions and acts on them with whatever filesystem authority you gave it. See `.ytstack/KNOWLEDGE.md` "Compile prompt injection via substrate" + `.ytstack/DECISIONS.md` 2026-05-15. Reference implementation: the `SdkCallSpec` in `scripts/compile_stages/compile.py` (`_attempt`); the gate's tests are `tests/test_sdk_scope.py`. Long-term direction: no agent-side filesystem writes at all — the agent returns a structured payload and the script writes the files (`.ytstack/backlog/compile-agent-no-filesystem-write.md`).

## Style

- Bash (only the bootstrap `wiki`): `set -euo pipefail`, `[[ ... ]]` over `[ ... ]`, lowercase function names, and nothing a macOS bash 3.2 can't run.
- Python: type hints, dataclasses for config, `Path` not str. Formatted and linted by ruff
  (`uv sync --group lint` once, then `uv run --group lint ruff check scripts hooks tests` and
  `ruff format --check scripts hooks tests`); the rule set and each ignore's reason live in
  `pyproject.toml`, and `scripts/core/config_schema.py` is kept out of the formatter (its field
  comments are the source of `docs/config.md`). Type-checked by ty on `scripts/core/`
  (`uv run --group typecheck ty check scripts/core`, pinned exactly); a suppression names ty's
  own rule (`# ty: ignore[rule]`) with the reason beside it. The same gates run in pre-commit
  and in CI (`.github/workflows/ci.yml`, with pytest and the desktop suite). Once per clone:
  `git config blame.ignoreRevsFile .git-blame-ignore-revs`.
- Size gates (all in the suite): a function under 150 lines (`tests/test_function_length.py`,
  empty allowlist); a `scripts/` module at most 1,000 lines unless `docs/engine-layout.md`
  § "Large modules" gives the reason (`tests/test_module_size.py`) — both lists only shrink;
  `README.md` ≤ 300 lines and this file ≤ 250 (`tests/test_doc_budget.py`), where a section
  without a reader in the Contents moves to `docs/`.
- No emoji in code. Logs use ASCII status markers (✓ ! ✗) only via the helpers in `core/console` (`ok` / `warn` / `info` / `fail` / `print_error`); the bootstrap `wiki` has only its `die`.
- A command module (any handler the catalogue dispatches, and every collector module `wiki collect` runs) writes its output through `core/console`: `say` for plain lines (print's contract), the helpers above for status. It never calls `print(` itself; `tests/test_output_seam.py` refuses one outside its allowlist, which names a reason per entry.
- Commit messages: imperative mood, short subject (≤70 chars), body explains why.

## When in doubt

- Read `docs/concept.md` for the design rationale.
- Read `docs/architecture.excalidraw` (open in Obsidian / excalidraw.com) for the data flow.
- Read `docs/FEATURES.md` for the implementation map (status, code location, known gaps per feature). Update it whenever you add / move / retire a feature.
- Check `.ytstack/backlog/` for unvalidated future-milestone pitches; `.ytstack/STATE.md` for current milestone status.
