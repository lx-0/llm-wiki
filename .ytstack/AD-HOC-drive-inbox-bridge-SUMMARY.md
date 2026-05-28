# AD-HOC — Drive inbox bridge (rsync mirror around macOS TCC) (2026-05-28)

**Trigger:** Operator dropped a phone-side intake folder under Google Drive
(`/Users/alex/Library/CloudStorage/GoogleDrive-…/My Drive/wiki-inbox/`,
currently holding `pictures/screenshots-tablet/` with Android-tablet
screenshots). Pointing a substrate collector directly at the Drive mount
works from the operator's shell but silently fails from Claude-Code-spawned
piggyback runs: macOS TCC blocks the engine subprocess from reading
`~/Library/CloudStorage/`. Operator request: "kannst du einen rsync bridge
fuer das llm-wiki vorsehen und mit ausliefern?" — scoped as ad-hoc, no new
milestone.

## What shipped

A user-shell / LaunchAgent-runnable bridge that pre-mirrors sandbox-restricted
inbox folders into local paths the substrate collectors then folder-watch as
their `<substrate>_inbox`. Substrate-agnostic: one mapping = one folder pair.
Operator wires each `local` into the matching `*_inbox` key separately.

**Why bridge instead of granting Claude Code Full Disk Access:** FDA is
binary-wide — it would give Claude Code read access to `~/Library/Mail/`,
`~/Library/Messages/`, every other CloudStorage mount, etc. The bridge gives
read access to one specific folder pair, runs in a separate process with the
operator's TCC scope, and survives Claude-Code-update FDA resets.

**Mode = move (default)** = `rsync --remove-source-files`. The remote folder
becomes a one-shot conveyor belt rather than a mirror, preventing
re-ingestion when the downstream substrate collector archives the file out
of `local`. `mode: copy` is the escape hatch for operators who want to keep
the Drive copy as a phone-side backup.

## Files

| File | Change |
|------|--------|
| `scripts/bridge/__init__.py`           | new, module marker |
| `scripts/bridge/drive_sync.py`         | new, core `run()` + `sync_one()` + `BridgeResult` / `BridgeRunSummary` |
| `scripts/bridge/cli.py`                | new, argparse entry → `wiki bridge {sync,list}` |
| `wiki`                                 | new `cmd_bridge` + dispatch case + `help_bridge` |
| `scripts/core/config.py`               | `Personal.inbox_bridges: list[dict] = []` |
| `scripts/migrations/migrate_config_keys.py` | inject `personal.inbox_bridges: []` |
| `config.example.yaml`                  | documented stanza under `personal:` |
| `templates/AGENTS.example.md`          | inbox-bridge bullet in "Where to look next" |
| `templates/.launchd/com.llm-wiki.bridge.plist.template` | new, LaunchAgent template with placeholders |
| `docs/setup-bridge.md`                 | new, operator setup guide |
| `tests/test_bridge_drive_sync.py`      | new, 16 unit tests — validation, skip paths, rsync arg construction, mock subprocess error paths |
| `tests/test_migrate_config_keys.py`    | counter +1 (69 → 70); idempotent / no-change-when-current fixtures get `inbox_bridges: []` |

## Verified (REGEL #1)

- `pytest tests/test_bridge_drive_sync.py tests/test_migrate_config_keys.py -q` → 46 passed.
- Live-probed `bridge.drive_sync.run()` against a local mapping (`/tmp/bridge-probe/src` → `/tmp/bridge-probe/dst`):
  - `mode: copy` + `dry_run: True` → status `ok`, no files moved.
  - `mode: copy` + real run → both files appear under `dst/`, `src/` intact.
  - `mode: move` + real run → both files appear under `dst/`, `src/` empty (rsync `--remove-source-files` works as expected).
- `from core.config import CONFIG; CONFIG.personal.inbox_bridges` → `[]` (loads cleanly).

## NOT verified — operator-side gate

- Real rsync against the actual Google Drive path. Claude-Code Bash is itself
  TCC-blocked on `~/Library/CloudStorage/…` (`Operation not permitted` on
  `ls`, `find`, `python os.walk`, `mdfind`). That's the same constraint that
  motivates the bridge in the first place; verifying it requires the operator's
  shell.
- `wiki bridge sync` invoked via the bash dispatcher against a real vault.
  The engine repo is not itself a vault; `./wiki bridge --help` aborts with
  the require-vault gate. Bash dispatcher code mirrors `cmd_collect` /
  `cmd_produce` (verified-working pattern), but the operator-side first run
  is the integration check.
- LaunchAgent loaded under launchd. Template placeholders need operator
  substitution + `launchctl load`; the macOS Files-and-Folders prompt fires
  on first run.

## Operator verification path

On lxw, with a wiki vault active:

```bash
wiki bridge list                 # → "no inbox bridges configured" (until you add one)
# edit <vault>/.wiki/config.yaml, add the first mapping under personal.inbox_bridges
wiki bridge list                 # → mapping appears
wiki bridge sync --dry-run       # → rsync runs, no copy; status `ok` per mapping
wiki bridge sync                 # → files moved into local mirror
ls <local-path>                  # → files present
ls "<remote-Drive-path>"         # → empty if mode=move
```

Then wire the collector:

```yaml
personal:
  screenshot_dir: "~/wiki-inbox-local/screenshots-tablet"   # if folder is screenshots
  # or
  picture_inbox:  "~/wiki-inbox-local/screenshots-tablet"   # if folder is camera photos
```

## Substrate-classification note

Operator's current Drive structure `wiki-inbox/pictures/screenshots-tablet/`
contains Android-tablet screenshots (`Screenshot_YYYYMMDD_HHMMSS_<App>.jpg`),
which match the **screenshots** collector's prompt shape (app / project /
key_text), not the **pictures** collector (scene / objects / action). The
folder name is therefore slightly misleading. The bridge is substrate-agnostic
so it doesn't care, but the operator wiring step should point
`personal.screenshot_dir` at the mirror, not `picture_inbox`. Called out in
`docs/setup-bridge.md`.

## Out of scope for this slice (operator-direction TBD)

- Auto-invoke bridge as a pre-step on every `wiki collect`. Tempting but
  would slow every collect by N rsync calls (Drive can be slow). Easy to add
  if operator wants it; for now they script the combination themselves or
  rely on the LaunchAgent.
- A `wiki bridge install-launchagent` subcommand that templates the plist
  inline and runs `launchctl load`. Deferred — manual install via `cp` +
  edit + `launchctl load` is two operator steps with clear errors when
  wrong; an automated installer mostly trades clarity for convenience.
- Bridge-side dedup (content-hash state file). Not needed under `mode: move`
  because the remote is drained; not needed under `mode: copy` because the
  downstream collector's archive-as-dedup carries the responsibility.
- Two-way sync. Not in the use case (phone → vault is the only direction).

## Why this is ad-hoc and not a new milestone

Operator-chosen via the scope-form question. Bridge is one self-contained
component (~250 LOC including CLI), substrate-agnostic, no cross-cutting
schema changes, no milestone-shaped multi-slice arc. Adding it as M026 would
have manufactured ceremony for a single rsync wrapper. Standard ad-hoc
artifact format follows the prior 5 AD-HOC summaries in this directory.
