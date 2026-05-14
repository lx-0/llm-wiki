# `use-llm-wiki` skill — agentic use of the wiki CLI from any project

**Triggered by:** operator request 2026-05-14. The engine ships 5 skills, all
vault-internal (they operate *on* a vault, symlinked into `<vault>/.claude/skills/`).
Missing: a skill that lets an agent working in *any* project consult — and
contribute to — a locally-available wiki via the `wiki` CLI.
**Priority:** P1 — closes the "output > input ratio" loop the README sells. The
wiki is meant to be read more often than written, by *every* agent given access;
right now an agent only discovers the wiki if it happens to be cwd'd inside it.

## Problem

The 5 bundled skills (`engine-pr`, `excalidraw-diagram`, `ingest-audio`,
`vault-health-check`, `vault-triage`) are vault-internal: they assume the agent
is operating inside the vault and target `<vault>/.claude/skills/`. There is no
skill for the inverse direction — an agent in some *unrelated* project that
wants to:

- **read** the knowledge base to answer a question grounded in the operator's
  own compiled knowledge, or
- **contribute** back to it (capture context, record a hard fact, ingest a
  source it just found), or
- **maintain** it (run compile, lint, review).

"Falls ein Wiki lokal verfügbar ist" is the load-bearing qualifier: the skill
must work from an arbitrary cwd and first *discover* whether a wiki exists at
all — if none, it does not apply and exits cleanly.

## Proposed approach

Four parts: the skill itself, a `--global` install path, a vault registry the
skill reads to locate the wiki, and a config key + setup-wizard question so the
global opt-in is a first-class tunable (not flag-only).

### 1. The skill — `skills/use-llm-wiki/SKILL.md`

Ships in the engine `skills/` dir like the other 5 (versioned, picked up by
`wiki update`). New: it is also **global-eligible** — see part 2.

`allowed-tools`: `Bash`, `Read`, `Glob`, `Grep`, `AskUserQuestion`.

**Step 1 — Locate the wiki (the "falls verfügbar" gate).** Discovery probe, in
priority order:

1. `LLM_WIKI_ROOT` env var → vault root; CLI is `$LLM_WIKI_ROOT/.wiki/wiki`.
   Explicit operator override, wins over everything.
2. **Walk up from cwd** for a `.wiki/wiki` executable — the agent is literally
   inside a vault (or a subdir of one). Wins over the registry.
3. **Registry** `~/.config/llm-wiki/vaults` (newline-delimited absolute
   vault-root paths, written by `wiki skills install --global`):
   - 1 entry → use it.
   - >1 entries → `AskUserQuestion` to pick (or honour `LLM_WIKI_ROOT`).
4. None of the above → **skill does not apply.** Print one line ("no local
   LLM-wiki found — skill does not apply") and stop. No error.

The `wiki` script is self-locating (derives `WIKI_DIR`/`ROOT_DIR` from its own
path), so once the skill knows `<vault>/.wiki/wiki` it can invoke it from any
cwd.

**Step 2 — Pick the operation tier.** Three tiers, escalating cost + risk:

| Tier | Commands | Gate |
|---|---|---|
| **Read** (default) | grep `knowledge/index.md` + `Read` the matched article; `wiki query "Q"` for cross-article synthesis | No confirmation. Prefer the index-grep path — every compiled article is a plain Markdown read (the README's whole thesis). Reserve `wiki query` for questions that span articles; it spends one LLM call. |
| **Contribute** (mutating) | `wiki flush`, `wiki correct add`, `wiki ingest-html`, `wiki ingest-youtube`, `wiki collect <name>` | Confirm with the operator before running — these write to the vault. |
| **Maintain** ($$$ / heavy) | `wiki compile`, `wiki lint`, `wiki review-wiki`, `wiki curiosity`, `wiki suggestions`, `wiki process-inbox`, `wiki correct apply` | Explicit confirmation **and** name the cost. `compile` / `correct apply` / large `query` spend real Claude budget; `review-wiki` / `curiosity` are local-LLM but slow. |

**Rules / guardrails:**

- **Read-first.** Prefer `grep knowledge/index.md` → `Read article` over
  `wiki query`. The index is large — grep by topic, never load it whole.
- **Never write to `raw/` directly.** The `wiki ingest-*` / `wiki collect`
  subcommands are the only sanctioned write path; `raw/` is LLM-read-only.
- **Mutating ops → confirm.** No `flush` / `correct` / `ingest` / `compile`
  without operator sign-off.
- **$$$ ops → name the cost.** Don't run `compile` or `correct apply` silently.
- **Live data, not memory.** Re-run `wiki status` / re-grep the index; never
  argue from a cached earlier result.
- **Don't treat the engine repo as a vault.** The engine checkout has
  `scripts/` but a stub `config.yaml` and no `knowledge/` — the walk-up probe
  must confirm a real vault (presence of `knowledge/index.md`), not just any
  `.wiki/`.

### 2. `--global` install path — `lib/skills.sh` + `wiki`

`wiki skills install` today symlinks every engine skill into the **vault's**
`.claude/skills/` with a *relative* target (`../../.wiki/skills/<name>`). Add a
global path, driven by the `skills.global_install` config key (part 4) — the
`--global` flag is just a one-shot shortcut that flips that key:

- `GLOBAL_SKILLS=(use-llm-wiki)` — array of global-eligible skill names. Only
  these are linked globally; the other 5 stay vault-internal (they need
  `VAULT_ROOT` and operate *in* a vault). Extensible if more cross-project
  skills appear.
- `wiki skills install` reads `skills.global_install`. When **true**, after the
  normal vault-local install it also:
  1. for each `GLOBAL_SKILLS` entry, symlinks `~/.claude/skills/<name>` →
     `$WIKI_DIR/skills/<name>` (**absolute** target — relative won't resolve
     from `~/.claude/`), **then**
  2. registers this vault: append `$ROOT_DIR` to `~/.config/llm-wiki/vaults`
     (create dir, dedup).
  When **false**, vault-local only — unchanged from today.
- `wiki skills install --global` → `config_set skills.global_install true`,
  then run the install (single code path — the flag is a config shortcut, so
  the opt-in *persists*; matches "make it global" intent). `--no-global` →
  `config_set … false` + run.
- `wiki skills uninstall` → vault-local removal, unchanged. `wiki skills
  uninstall --global` → also remove global symlinks pointing into *this*
  vault's `.wiki/skills/`, deregister `$ROOT_DIR`, and set
  `skills.global_install false`. Foreign / other-vault entries untouched.
- `wiki skills status` → existing per-skill table + a "GLOBAL" section showing
  the `skills.global_install` value, the `~/.claude/skills/` link state, and
  the registry contents — always shown, on or off.
- `wiki skills sync` (run by `wiki update`) → reads `skills.global_install`;
  when true, also refreshes the global symlinks + re-registers. So a vault that
  opted in stays globally linked across updates with no re-flagging — the
  config key is the durable opt-in, the registry is derived state.

**Global symlink ownership.** A global link is "engine-owned" iff its target
matches `*/.wiki/skills/<name>`. The global symlink can only point at one
vault, but that is fine: the SKILL.md does **not** use the symlink target for
discovery — it reads the registry (which holds *all* opted-in vaults). The
symlink only makes the skill *discoverable* by Claude Code; any vault's copy of
`SKILL.md` is byte-identical (same engine version). So a "collision" where
`~/.claude/skills/use-llm-wiki` already points at another vault is **not** an
error — leave it, just register the new vault. Only a *foreign* entry (not a
symlink into any `.wiki/skills/`) is reported and left untouched, same as the
vault-local rule.

### 3. Vault registry — `~/.config/llm-wiki/vaults`

Plain newline-delimited file of absolute vault-root paths. Tool-agnostic home
(`~/.config/llm-wiki/`, not `~/.claude/`) because the registry is engine state,
not a Claude-Code artifact — even though the consumer (`SKILL.md`) is currently
Claude-Code-specific. Written only by `wiki skills install/uninstall` and `wiki skills sync` (driven
by `skills.global_install`). Read by the skill's discovery probe.

### 4. Config key + setup-wizard question

The global opt-in is a tunable, so it goes through `wiki_config.py` +
`config.example.yaml` on first commit (per the project's "lift to CONFIG
immediately" rule) — not a flag-only behaviour.

- New `skills` config section (own dataclass, own `config.example.yaml` block) —
  the domain noun matches the `wiki skills` subcommand and leaves room for
  future skills tunables. Single field for now:
  - `skills.global_install: bool = False` — when true, `wiki skills install`
    and `wiki skills sync` also link `GLOBAL_SKILLS` into `~/.claude/skills/`
    and register the vault. Default false keeps installs vault-local.
- `WikiConfig` gains `skills: Skills`; `load()` gains the merge line.
- **Setup wizard** (`config_cmd_setup_wizard` in `lib/config.sh`) gets a 6th
  question — "Make this wiki's `use-llm-wiki` skill available to agents in any
  project?" — defaulting from the current key value. Banner "5 questions" → "6".
- **Config editor** (`config_cmd_edit`) gets `skills` added to the section
  picker list.
- **Config status** (`config_cmd_status`) gets a `skills.global_install` row.

The config key is the canonical control; `--global` / `--no-global` are
one-shot shortcuts that write it. `wiki config set skills.global_install true`
followed by `wiki skills install` is the fully equivalent path.

## Touchpoints

- `skills/use-llm-wiki/SKILL.md` — **new.** The skill.
- `lib/skills.sh` — `GLOBAL_SKILLS` array; `GLOBAL_SKILLS_DST` (`~/.claude/skills`);
  `REGISTRY_FILE` (`~/.config/llm-wiki/vaults`); `_skill_is_global_engine_owned`;
  `skills_install_global_silent` / `skills_uninstall_global` / registry
  read-write helpers; config-key read gating `skills_cmd_install` /
  `skills_cmd_sync`; `--global` handling + "GLOBAL" section in
  `skills_cmd_status`.
- `wiki` — `cmd_skills()` arg parsing for `--global` / `--no-global` (config
  shortcut); `help_skills()` text; header comment block (lines 15–18).
  `cmd_update` already calls `skills_cmd_sync` — no change.
- `scripts/core/wiki_config.py` — `Skills` dataclass; `WikiConfig.skills` field;
  `load()` merge line.
- `config.example.yaml` — new `skills:` block.
- `lib/config.sh` — `config_cmd_setup_wizard` 6th question + banner; `config_cmd_edit`
  section list; `config_cmd_status` row.
- `docs/PROCESS.md` — skills-distribution section: `--global` + registry + config key.
- `docs/cli.md`, `docs/config.md` — `wiki skills` flags + `skills.*` key.
- `README.md` — "5 skills bundled" stat → 6; skills list; `wiki skills`
  examples; the engine-layout `.claude/skills/` row.
- `AGENTS.md` — repo-layout `skills/` note if it enumerates skills; the
  `~/.config/llm-wiki/vaults` registry as a new side-effect surface; the new
  config section in the "adding a tunable" convention if it lists sections.
- `docs/architecture.excalidraw` — skills-distribution box, if depicted.

## Edge cases

- **No wiki found** → skill prints one line, exits. Not an error, not a retry.
- **Multiple registered vaults** → `LLM_WIKI_ROOT` wins; else `AskUserQuestion`.
- **Walk-up hits the engine repo** (has `.wiki/`-like `scripts/` but no
  `knowledge/index.md`) → reject, fall through to registry.
- **`wiki` not executable / `uv` missing** → surface the dependency error
  verbatim; don't paper over it.
- **Global symlink collides with a foreign entry** → warn, leave untouched
  (same policy as vault-local).
- **Global symlink points at a different vault** → not a collision; leave it,
  just register the new vault (SKILL.md content is engine-identical).
- **Registry references a deleted vault** → discovery probe skips paths whose
  `.wiki/wiki` no longer exists; `wiki skills status --global` flags stale
  entries; a future `sync` could prune them (defer — out of scope here).
- **`~/.config` unwritable / sandboxed** → registry write fails soft with a
  warning; `--global` symlink can still work via env var / walk-up.

## Open questions

- Should `vault-health-check` / `vault-triage` also become global-eligible?
  They operate *in* a vault and need `VAULT_ROOT` — deferred. `GLOBAL_SKILLS`
  is an array precisely so this can be revisited without restructuring.
- Should `sync` prune registry entries for deleted vaults? Deferred — `status
  --global` flags them; pruning is a separate, low-stakes follow-up.
- Registry format: flat newline file vs. JSON with metadata (last-seen, label).
  Flat file for now — minimal, greppable, matches the engine's "single format
  when one consumer" preference. Revisit only if the skill needs per-vault
  metadata.

## Source

Operator request, 2026-05-14 conversation. Follows the `llm-wiki-change`
5-phase process (Concept → Verify → Implement → Document → Visualize).
