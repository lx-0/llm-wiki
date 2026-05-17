# stg-glob-pattern — versioned folder names in `stg_backup_dir`

The Simple Tab Groups Firefox add-on writes JSON backups to a folder whose name embeds the current Firefox major version, e.g. `~/Downloads/STG-backups-FF-149.0.2` → `~/Downloads/STG-backups-FF-150.0.1`. Operator currently pins the literal path in `<vault>/.wiki/config.yaml` and updates it manually on each FF major version bump (~3-6 bumps/year).

Surfaced 2026-05-16 during the lxw config audit.

## Proposal

Extend `scripts/collectors/scan_tabs.py:35-46` (and the parallel `scan_browser.py:48`) to recognize a glob pattern in `personal.stg_backup_dir`. When the configured value contains `*`, expand it via `Path(parent).glob(pattern)`, filter to directories, pick the newest by mtime. Treat that as the effective backup dir for the rest of the run.

**Config shape (operator-facing):**

```yaml
personal:
  stg_backup_dir: ~/Downloads/STG-backups-FF-*
```

**Implementation sketch (~20 LOC):**

```python
def _resolve_stg_backup_dir(raw: str) -> Path | None:
    p = Path(raw).expanduser()
    if "*" not in str(p):
        return p if p.exists() else None
    parent = p.parent
    pattern = p.name
    if not parent.exists():
        return None
    candidates = [d for d in parent.glob(pattern) if d.is_dir()]
    return max(candidates, key=lambda d: d.stat().st_mtime, default=None)
```

Call once at module init (replace `DEFAULT_BACKUP_DIR = Path(_STG_RAW).expanduser() if _STG_RAW else Path()`). Same helper used in both `scan_tabs.py` and `scan_browser.py` — extract to `core/utils.py` if both consume it.

## Edge cases

- Glob matches nothing → return None, collector reports "stg_backup_dir not found" (existing path).
- Glob matches multiple dirs from different FF versions → newest mtime wins (assumes STG keeps writing into the active FF profile's dir).
- Operator wants to pin a specific version → uses literal path, glob branch never fires. Backward-compatible.

## Don't do this

- Auto-detect FF version from system and template into the path. Brittle, multiple FF channels (Developer, Nightly, Release).
- Symlink hack (`STG-backups-current` → versioned dir). Operator-maintenance cost ~same as updating config; doesn't auto-heal on FF update.

## Effort

~half a day including tests + doc + the parallel `scan_browser.py` call site.

## References

- `scripts/collectors/scan_tabs.py:35-46`
- `scripts/collectors/scan_browser.py:48,522`
- `scripts/core/config.py:456`
- Memory: [[project-lxw-config-audit-2026-05-16]]
