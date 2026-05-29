# AD-HOC: Operations log out of `knowledge/`, into `.wiki/logs/operations.md` (2026-05-28)

## Trigger
Operator reported Obsidian crashing on lxw vault open. `knowledge/log.md` had
grown to **2 MB / ~15k lines** (six months of compile + dream entries). The
file was quarantined as `.log.md.disabled-test` to stop the crash while
preserving history — the working state was "Obsidian works, history alive,
but ingest agents have nowhere to log to".

## Root cause
The operations log is engine telemetry, not knowledge. Putting it inside
`knowledge/` was legacy convenience (operator could browse history from
inside Obsidian) but cost: Obsidian indexed every `.md` in `knowledge/`,
live-preview rendered the whole multi-megabyte file on open, Graph View
treated it as a hub linking every article. Every wiki criterion the log
satisfies is incidental; every cost it imposes is real.

## Decision
Relocate `LOG_FILE` from `KNOWLEDGE_DIR / "log.md"` to
`LOGS_DIR / "operations.md"` (`<vault>/.wiki/logs/operations.md`). Same
directory that already houses `flush.log` — Obsidian doesn't index
`.`-prefixed top-level folders. Other options rejected: monthly rotation
inside `knowledge/`, last-N truncation, `.obsidianignore` — all keep the
file indexed and only delay the next crash. Full rationale: DECISIONS
2026-05-28.

## Implementation
- `scripts/core/paths.py` — LOG_FILE relocated to LOGS_DIR section; layout
  comment updated.
- `scripts/compile_stages/compile.py`, `scripts/dream.py`,
  `scripts/facts/correct_apply.py` — each `make_path_scope_hook` call
  extended with LOG_FILE in its allowed-write-roots list. Path-as-root
  matches the exact file (Python `relative_to` semantics), so agents can
  append to the audit trail under the path-scope gate without widening
  write access to `.wiki/` generally.
- `scripts/reconcile.py` — `LOG_FILE.parent.mkdir(parents=True, exist_ok=True)`
  added (dest dir may not exist on a never-compiled vault).
- `scripts/optimize-claude-md.py` — dropped local LOG_FILE redef, imports
  from `core.paths`.
- Prompts touched (`compile_main`, `compile_health`, `query_file_back`,
  `correct_apply`, `dream_entity`, `dream_entity_system`,
  `agents/dream-cycle`, plus `compile_default`/`calendar`/`daily`/`pictures`/
  `screenshots` "No log.md update" prose): every `knowledge/log.md`
  reference rewritten to `.wiki/logs/operations.md`; bare "log.md" in
  the "no log update" headers softened to "operations log".
- `scripts/migrations/migrate_log_md_path.py` — new one-shot migration:
  finds `<vault>/knowledge/log.md` AND the lxw `.log.md.disabled-test`
  quarantine name, moves to `.wiki/logs/operations.md`. Idempotent;
  re-runs find nothing. If both source and dest exist, prepends source
  under the existing header and leaves a `.migrated-<ts>` audit copy.
- `wiki` (`cmd_update`) — invokes the migration after the config-keys
  migration so existing vaults pick the move up on next `wiki update`.

## Doc / template sync
- `templates/dashboard.md` — dropped the "Compile log" quick-access link.
- `templates/AGENTS.example.md` — `log.md` removed from the `knowledge/`
  tree diagram; build-log section retargets to `.wiki/logs/operations.md`;
  conventions line updated.
- `templates/.obsidian/graph.json` + `extended-graph/data.json` —
  removed the now-dead `-path:knowledge/log` exclusion.
- `docs/PRINCIPLES.md`, `docs/PROCESS.md`, `docs/cli.md`,
  `docs/concept.md` — path string updates + a PRINCIPLES note that the
  chronological record now lives outside the indexed vault.
- `.ytstack/DECISIONS.md` (this entry) + `.ytstack/KNOWLEDGE.md` (graph
  filter + multi-step-prompt notes) reflect the relocation.

## Defensive
The `if name in ("index.md", "log.md")` filters in `lint.py`, `health.py`,
`dashboard/dashboard_stats.py`, `menu_context.py`, `migrations/migrate_add_type.py`
are left in place. After migration they're defensive no-ops; if an operator
manually drops a `log.md` back into `knowledge/` (or a stale file survives
something), the filters keep ignoring it. Cheap insurance.

## Verification
- Dry-run against lxw vault: confirmed 2 MB `.log.md.disabled-test` resolves to
  correct destination.
- Test suite: 1041 green (4 pre-existing dream-sampling fails unrelated).
- Operator ran `wiki update` on lxw afterwards — migration moved the file,
  Obsidian opens normally.

## Commit
`ce8314b` — fix(log): relocate operations log out of knowledge/ to .wiki/logs/operations.md
