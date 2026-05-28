# Inbox bridge setup

The inbox bridge (`scripts/bridge/drive_sync.py`) mirrors files from
network-mounted or sandbox-restricted paths into local paths the
substrate collectors then folder-watch as their `<substrate>_inbox`.

It exists because macOS TCC blocks Claude-Code-spawned subprocesses
from reading `~/Library/CloudStorage/…` (Google Drive, iCloud Drive,
Dropbox, OneDrive). Pointing a collector directly at a Drive-mounted
folder works fine from the operator's shell but silently fails from a
piggyback fired by a SessionEnd hook. The bridge runs as the user
(manually or via a LaunchAgent) where TCC is satisfied, and pre-mirrors
the source into a stable local path the collector can read freely.

The bridge is **substrate-agnostic**. One mapping = one folder pair.
The operator wires each mapping's `local` into the matching
`*_inbox` key separately.

## 1. Choose a local mirror root

Anywhere outside `~/Library/`, `~/Documents/`, and `~/Desktop/` is safe
from macOS TCC. A flat layout under `~/wiki-inbox-local/` is clean:

```bash
mkdir -p ~/wiki-inbox-local
```

Sub-folders are created on demand by the bridge.

## 2. Configure mappings in `config.yaml`

Each mapping is a `{remote, local, mode?, enabled?, name?}` dict:

```yaml
personal:
  inbox_bridges:
    - name:   screenshots-tablet
      remote: "/Users/alex/Library/CloudStorage/GoogleDrive-you@gmail.com/My Drive/wiki-inbox/pictures/screenshots-tablet"
      local:  "~/wiki-inbox-local/screenshots-tablet"
      mode:   move

    - name:   phone-voice-memos
      remote: "/Users/alex/Library/CloudStorage/GoogleDrive-you@gmail.com/My Drive/wiki-inbox/voice"
      local:  "~/wiki-inbox-local/voice"
      mode:   move
```

| field | required | default | meaning |
|-------|----------|---------|---------|
| `remote`  | yes | — | absolute path (~-expansion supported); missing → skip with WARNING |
| `local`   | yes | — | absolute path; auto-created on first sync |
| `mode`    | no  | `move` | `move` runs `rsync --remove-source-files` (drains the remote); `copy` leaves the remote intact |
| `enabled` | no  | `true` | flip to `false` to disable one mapping without removing the block |
| `name`    | no  | basename(`local`) | label used in CLI output and logs |

### Move vs copy

`mode: move` makes the remote folder a **one-shot conveyor belt** —
files dropped on the phone are pulled exactly once, then disappear
from the Drive folder. This prevents re-ingestion when the downstream
substrate collector archives the file out of `local` (collector archive
moves leave the file gone from `local`; without move-mode, the next
bridge run would re-pull the original from Drive, and the cycle would
never terminate).

If you want to keep the Drive copy as a phone-side backup, use
`mode: copy` and periodically clear the Drive folder by hand.

## 3. Wire each mapping into the right collector

The bridge does **not** know about substrates. You point the matching
collector's inbox key at the mirror path:

```yaml
personal:
  picture_inbox: "~/wiki-inbox-local/screenshots-tablet"  # ← bridge target
  voice_inbox:   "~/wiki-inbox-local/voice"               # ← bridge target
```

> Note on substrate classification: the example folder name above is
> `screenshots-tablet`, but Android-style screenshots
> (`Screenshot_YYYYMMDD_HHMMSS_<app>.jpg`) match the **screenshots**
> collector's prompt shape (app / project / key_text), not the
> **pictures** collector (scene / objects / action). The screenshots
> collector reads from `personal.screenshot_dir` — point that key at
> the mirror, not `picture_inbox`.

## 4. Run it

Manually:

```bash
wiki bridge sync             # mirror all configured mappings
wiki bridge sync --dry-run   # preview rsync output, no copy / no move
wiki bridge list             # show configured mappings
```

Exit code: `0` if every mapping returned `ok` or `skipped`, `1` if any
returned `failed`. Logs go to `<vault>/.wiki/logs/bridge.log`.

## 5. Automate with a LaunchAgent (optional)

The template at
`templates/.launchd/com.llm-wiki.bridge.plist.template` runs
`wiki bridge sync` on a schedule (default every 30 minutes). The
template comments cover the install steps; the short version:

```bash
# Pick your paths and substitute the placeholders, then:
cp templates/.launchd/com.llm-wiki.bridge.plist.template \
   ~/Library/LaunchAgents/com.llm-wiki.bridge.plist
# Edit the file inline to replace __WIKI_BINARY__ / __WIKI_DIR__ / __LOG_DIR__
launchctl load ~/Library/LaunchAgents/com.llm-wiki.bridge.plist
launchctl list | grep com.llm-wiki.bridge
tail -f <your LOG_DIR>/bridge.stderr
```

The first time launchd fires the bridge, macOS may surface a one-shot
Files-and-Folders prompt on the CloudStorage path. Approve in
**System Settings → Privacy & Security**.

## Troubleshooting

| symptom | cause | fix |
|---------|-------|-----|
| `remote_missing: …` in CLI output | Drive offline OR TCC denied this caller OR typo | open the path in Finder; if Finder shows it but the bridge can't, the calling process needs TCC (LaunchAgent prompt, or grant Terminal Full Disk Access) |
| `rsync_exit_23` | partial transfer; some files unreadable | run `wiki bridge sync --dry-run` and inspect — usually a single locked Drive file blocks the batch |
| `rsync_not_found` | no `rsync` on `$PATH` | macOS ships `/usr/bin/rsync` (Apple openrsync); the bridge falls back to it. If you've stripped PATH for the launchd context, set `EnvironmentVariables.PATH` in the plist. |
| files re-appear in `local` after collector archives them | mode is `copy`, Drive still has the source | switch to `mode: move` |
| Drive folder grows but `local` stays empty | bridge has not run yet, OR the LaunchAgent is loaded but TCC blocked | check `<vault>/.wiki/logs/bridge.log` |
