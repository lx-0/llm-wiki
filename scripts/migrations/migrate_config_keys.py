"""Migrate renamed / removed config.yaml keys to current engine schema.

The engine's config loader falls back to dataclass defaults for any key it
doesn't recognise — so a *renamed* key in an operator's `config.yaml` is
silently ignored and the operator's customisation stops applying without a
warning. This one-shot migration renames the stale keys in place (preserving
the operator's values) and drops keys for removed features.

Key changes covered (chronological):
  piggybacks.follow_requests   → piggybacks.curiosity_followup   (curiosity rework)
  piggybacks.scan_screenshots  → piggybacks.screenshots          (Collector port 2026-05-14)
  piggybacks.email_incremental → piggybacks.email                (M002 — kept for old vaults)
  piggybacks.sync_memories     → (removed — sync-memories deleted 2026-05-13)

Idempotent: a config already on the current schema produces no change.

Usage:
    uv run python scripts/migrations/migrate_config_keys.py --vault PATH            # preview
    uv run python scripts/migrations/migrate_config_keys.py --vault PATH --apply    # write
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("migrate-config-keys")

# old_key → new_key (rename, value preserved). new_key=None → drop the block.
PIGGYBACK_RENAMES: dict[str, str | None] = {
    "follow_requests": "curiosity_followup",
    "scan_screenshots": "screenshots",
    "email_incremental": "email",
    "sync_memories": None,  # feature removed 2026-05-13
}


def migrate_piggybacks(piggybacks: dict) -> tuple[dict, list[str]]:
    """Return (new_piggybacks_dict, list_of_change_descriptions)."""
    changes: list[str] = []
    out = dict(piggybacks)  # shallow copy — preserve key order as much as possible

    for old_key, new_key in PIGGYBACK_RENAMES.items():
        if old_key not in out:
            continue
        old_value = out.pop(old_key)
        if new_key is None:
            changes.append(f"dropped piggybacks.{old_key} (feature removed)")
            continue
        if new_key in out:
            # Both old and new present — new wins, old discarded (operator
            # already migrated this one; the stale key is just cruft).
            changes.append(f"dropped stale piggybacks.{old_key} (piggybacks.{new_key} already set)")
        else:
            out[new_key] = old_value
            changes.append(f"renamed piggybacks.{old_key} → piggybacks.{new_key}")

    return out, changes


def migrate_config(config_path: Path) -> tuple[str | None, list[str]]:
    """Return (new_yaml_text_or_None, changes). None text → no change needed."""
    if not config_path.exists():
        log.error("config.yaml not found: %s", config_path)
        return None, []

    raw = config_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}

    if "piggybacks" not in data or not isinstance(data["piggybacks"], dict):
        log.info("No piggybacks block — nothing to migrate.")
        return None, []

    new_piggybacks, changes = migrate_piggybacks(data["piggybacks"])
    if not changes:
        return None, []

    data["piggybacks"] = new_piggybacks
    # PyYAML round-trip drops comments — config.yaml is operator-owned and
    # already documents this trade-off (see wiki config CLI note).
    new_text = yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return new_text, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--vault", type=str, required=True,
                        help="Path to the vault root (config.yaml lives at <vault>/.wiki/config.yaml)")
    parser.add_argument("--apply", action="store_true",
                        help="Write the migrated config (default: preview only)")
    args = parser.parse_args()

    vault = Path(args.vault).expanduser()
    config_path = vault / ".wiki" / "config.yaml"

    new_text, changes = migrate_config(config_path)

    if not changes:
        log.info("config.yaml is already on the current key schema — no change.")
        return 0

    log.info("Changes for %s:", config_path)
    for c in changes:
        log.info("  - %s", c)

    if not args.apply:
        log.info("Preview only. Re-run with --apply to write.")
        return 0

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = config_path.with_suffix(config_path.suffix + f".bak.{ts}")
    shutil.copy2(config_path, backup)
    log.info("Backed up → %s", backup.name)

    config_path.write_text(new_text, encoding="utf-8")
    log.info("Wrote migrated config.yaml (%d change(s)).", len(changes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
