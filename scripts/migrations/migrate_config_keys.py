"""Migrate renamed / removed / added config.yaml keys to current engine schema.

The engine's config loader falls back to dataclass defaults for any key it
doesn't recognise — so a *renamed* key in an operator's `config.yaml` is
silently ignored and the operator's customisation stops applying without a
warning, and a *new* key never appears in the operator's file at all so they
don't see that it's tunable. This one-shot migration renames stale keys in
place (preserving operator values), drops keys for removed features, injects
new keys under their parent block with the engine default, and prunes orphan
keys whose backing dataclass entry was deleted (otherwise they linger as
silent YAML cruft forever).

Key changes covered (chronological):
  piggybacks.follow_requests              → piggybacks.curiosity_followup   (curiosity rework)
  piggybacks.scan_screenshots             → piggybacks.screenshots          (Collector port 2026-05-14)
  piggybacks.email_incremental            → piggybacks.email                (M002 — kept for old vaults)
  piggybacks.sync_memories                → (removed — sync-memories deleted 2026-05-13)
  limits.compile_force_long_context_types     (added 2026-05-15, default ["daily-digest"])
  limits.compile_skip_on_long_context_unknown (added 2026-05-15, default True)
  limits.calendar_request_timeout_s       (added 2026-05-15 M006, default 30)
  limits.calendar_max_per_run             (added 2026-05-15 M006, default 500)
  limits.calendar_backfill_days           (added 2026-05-15 M006, default 90)
  limits.calendar_future_days             (added 2026-05-15 M006, default 7)
  piggybacks.calendar                     (added 2026-05-15 M006, cooldown 6h, max_per_run 500)
  personal.calendar_work_keywords         → (dropped 2026-05-15 M006, scan_calendar-only legacy field)
  personal.calendar_categories            → (dropped 2026-05-15 M006, scan_calendar-only legacy field)
  personal.calendar_report_language       → (dropped 2026-05-15 M006, scan_calendar-only legacy field)
  limits.compile_force_long_context_types ← list-extend with "calendar-rollup" (2026-05-16, M006 hardening)
  limits.compile_max_turns_long_context   (added 2026-05-16, default 30 — fixes max_turns trap on dense fan-out substrates)
  limits.compile_max_cost_per_file_usd    (added 2026-05-16, default 1.0 — per-file budget guard, aborts batch on overrun)
  limits.compile_skip_substrate_types     (added 2026-05-16, default [] — substrate-skip-list for batch mode)
  limits.compile_force_long_context_types ← list-prune calendar-rollup AND daily-digest (2026-05-16 P2, dedicated prompts shipped)
  limits.compile_skip_substrate_types     ← list-prune calendar-rollup (2026-05-16 P2, compile_calendar.md ships)

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

# Keys introduced in newer engine versions that should be injected into the
# operator's config so they're visible/tunable. Structure: parent block name
# → {key: default_value}. Missing parent blocks are created. Keys already
# present (even with a different value) are left untouched.
KEY_ADDITIONS: dict[str, dict[str, object]] = {
    "limits": {
        # Empty by default since 2026-05-16 P2: daily-digest and
        # calendar-rollup moved to dedicated lean prompts in
        # SUBSTRATE_PROMPTS (compile.py). No remaining substrate
        # legitimately needs [1m] up-front; the 50 KB size-threshold
        # is the right escape hatch for large sources.
        "compile_force_long_context_types": [],
        # Treat kind=unknown failures with no further retry path (small
        # source OR already on [1m]) as skips instead of hard failures.
        # Preserves the consecutive-failure budget so the batch survives
        # a structurally-unprocessable file.
        "compile_skip_on_long_context_unknown": True,
        # Google Calendar collector (M006, 2026-05-15). Per-HTTP-call timeout
        # against calendar.googleapis.com / per-calendar event cap / past +
        # future windows in days. Match the dataclass defaults in
        # `scripts/core/config.py:Limits.calendar_*`.
        "calendar_request_timeout_s": 30,
        "calendar_max_per_run": 500,
        "calendar_backfill_days": 90,
        "calendar_future_days": 7,
        # Higher max_turns for force-long-context substrates (2026-05-16).
        # Default 12 ran out partway through dense calendar-rollup days
        # with 6+ attendees, hit `subtype=error_max_turns` and burned
        # ~$3-4/attempt at [1m] pricing. 30 covers the realistic depth.
        "compile_max_turns_long_context": 30,
        # Per-file cost guard (USD); abort batch on overrun. Defense
        # against substrate-prompt-mismatch loops that burn $5-10/file
        # silently. See KNOWLEDGE.md "calendar-rollup max_turns trap".
        "compile_max_cost_per_file_usd": 2.0,
        # Substrate-skip-list for batch mode (frontmatter `type:` values).
        # Empty default since 2026-05-16 P2 landed (calendar-rollup
        # moved out of the skip-list once compile_calendar.md prompt
        # shipped). Last-resort escape hatch for substrate types with
        # no good prompt yet.
        "compile_skip_substrate_types": [],
    },
    "piggybacks": {
        # M006 calendar collector — mirrors gmeet / jamie 6 h cadence.
        # Per-account override lives in personal.accounts.<id>.calendar; the
        # piggyback block here is the cooldown / batch-cap, not the auth
        # state. An account without a kind=google-calendar sub-block silently
        # skips the run.
        "calendar": {"enabled": True, "cooldown_hours": 6, "max_per_run": 500},
    },
}

# Elements to add to existing list-valued config entries. Used when an
# engine update widens a list default (e.g. a new substrate type added to
# `compile_force_long_context_types`). KEY_ADDITIONS only injects MISSING
# keys, so an operator who already pinned the list to the old default
# wouldn't otherwise pick up the new element. Structure: dotted parent.key
# path → list of elements to ensure are present. Idempotent: existing
# elements are left untouched. Missing parent block / missing key falls
# through to KEY_ADDITIONS for first-time injection.
LIST_ADDITIONS: dict[str, list[object]] = {
    # No active list-additions right now. The 2026-05-16-morning entry
    # adding `calendar-rollup` to `compile_force_long_context_types`
    # was reverted later the same day after substrate-aware prompt
    # dispatch landed — see LIST_REMOVALS for the cleanup migration.
}

# Elements to REMOVE from existing list-valued config entries. The
# inverse of LIST_ADDITIONS — used when a list default narrows or an
# entry's old position is no longer correct (e.g. a substrate type
# moves out of compile_force_long_context_types because it got a
# dedicated lean prompt). Structure: dotted parent.key path → list of
# elements to ensure are NOT present. Idempotent.
LIST_REMOVALS: dict[str, list[object]] = {
    # 2026-05-16 — substrate-aware prompt dispatch landed
    # (SUBSTRATE_PROMPTS in compile.py). Both daily-digest and
    # calendar-rollup now have dedicated lean prompts that don't
    # need [1m] up-front; the size-threshold escape hatch handles
    # genuinely large sources. Clean these out of operator configs
    # that picked them up during the brief P1 hotfix window.
    "limits.compile_force_long_context_types": ["daily-digest", "calendar-rollup"],
    # The P1 hotfix added calendar-rollup here to stop the burn;
    # P2 ships the actual fix (compile_calendar.md), so the skip is
    # no longer needed. Calendar files compile via the dedicated
    # prompt under an 8-turn budget at <$0.10/file.
    "limits.compile_skip_substrate_types": ["calendar-rollup"],
}

# Fields whose backing dataclass entry was removed; their leftover entries
# in operator configs are silently ignored on load but linger as YAML cruft
# until pruned. Structure: parent block name → set of orphan field names.
KEY_DROPS: dict[str, set[str]] = {
    "personal": {
        # Removed 2026-05-15 (M006) — calendar moved off Thunderbird-SQLite
        # to Google Calendar v3. These three were scan_calendar-only knobs
        # (year-counts report bucketing, work-keyword highlighting, output
        # language). `calendar_skip_keywords` is KEPT — the new collector
        # still consumes it for holiday-title filtering.
        "calendar_work_keywords",
        "calendar_categories",
        "calendar_report_language",
    },
}


def migrate_additions(data: dict) -> list[str]:
    """Inject missing keys from KEY_ADDITIONS under their parent block.

    Mutates `data` in place. Returns a list of human-readable change strings.
    """
    changes: list[str] = []
    for parent, keys in KEY_ADDITIONS.items():
        block = data.get(parent)
        if block is None:
            block = {}
            data[parent] = block
            changes.append(f"created empty {parent}: block")
        if not isinstance(block, dict):
            # Operator has something non-dict under this key — don't clobber.
            continue
        for key, default in keys.items():
            if key in block:
                continue
            block[key] = default
            changes.append(f"added {parent}.{key} = {default!r}")
    return changes


def migrate_list_additions(data: dict) -> list[str]:
    """Append missing elements to existing list-valued config entries.

    Only acts when the parent block AND the target key already exist as a
    list. Missing keys are left for KEY_ADDITIONS to inject with the engine
    default. Mutates `data` in place. Returns human-readable change strings.
    """
    changes: list[str] = []
    for path, additions in LIST_ADDITIONS.items():
        parent_name, _, key = path.partition(".")
        if not key:
            continue
        block = data.get(parent_name)
        if not isinstance(block, dict):
            continue
        existing = block.get(key)
        if not isinstance(existing, list):
            continue
        # Copy before mutating: migrate_additions assigns KEY_ADDITIONS
        # defaults by reference, so an in-place append here would mutate
        # the module-level default and leak into the next migrate_config
        # call (visible across pytest collection runs).
        new_list = list(existing)
        run_changes: list[str] = []
        for item in additions:
            if item in new_list:
                continue
            new_list.append(item)
            run_changes.append(f"appended {item!r} to {path}")
        if run_changes:
            block[key] = new_list
            changes.extend(run_changes)
    return changes


def migrate_list_removals(data: dict) -> list[str]:
    """Remove specified elements from existing list-valued config entries.

    Inverse of migrate_list_additions. Only acts when parent block AND
    target key exist as a list. Missing parent/key is a no-op. Mutates
    `data` in place; returns human-readable change strings.
    """
    changes: list[str] = []
    for path, removals in LIST_REMOVALS.items():
        parent_name, _, key = path.partition(".")
        if not key:
            continue
        block = data.get(parent_name)
        if not isinstance(block, dict):
            continue
        existing = block.get(key)
        if not isinstance(existing, list):
            continue
        # Copy before mutating — same module-level-default-leak concern
        # as migrate_list_additions.
        new_list = list(existing)
        run_changes: list[str] = []
        for item in removals:
            while item in new_list:
                new_list.remove(item)
                run_changes.append(f"removed {item!r} from {path}")
        if run_changes:
            block[key] = new_list
            changes.extend(run_changes)
    return changes


def migrate_drops(data: dict) -> list[str]:
    """Remove orphan keys whose backing dataclass field is gone.

    Mutates `data` in place. Returns a list of human-readable change strings.
    """
    changes: list[str] = []
    for parent, orphans in KEY_DROPS.items():
        block = data.get(parent)
        if not isinstance(block, dict):
            continue
        for field in sorted(orphans):
            if field in block:
                block.pop(field)
                changes.append(f"dropped orphan {parent}.{field} (dataclass field removed)")
    return changes


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

    changes: list[str] = []

    # Piggyback renames / removals (only if the operator has a piggybacks
    # block at all — fresh installs and pre-piggyback configs skip this).
    if isinstance(data.get("piggybacks"), dict):
        new_piggybacks, pb_changes = migrate_piggybacks(data["piggybacks"])
        if pb_changes:
            data["piggybacks"] = new_piggybacks
            changes.extend(pb_changes)

    # Key additions — backfill new knobs under their parent block so they're
    # visible to the operator. Runs unconditionally; entries already present
    # are left untouched.
    changes.extend(migrate_additions(data))

    # List-element additions — widen existing list-valued knobs (e.g. when
    # a new substrate type joins compile_force_long_context_types). Must
    # run after migrate_additions so a freshly-injected list also gets
    # any LIST_ADDITIONS for it (idempotent: already-present entries are
    # untouched).
    changes.extend(migrate_list_additions(data))

    # List-element removals — narrow list-valued knobs (e.g. when a
    # substrate type leaves the skip-list because its dedicated prompt
    # landed). Runs after additions so a freshly-injected list with the
    # NEW default gets pruned correctly if the operator's old config had
    # extra entries.
    changes.extend(migrate_list_removals(data))

    # Orphan-field drops — prune entries whose backing dataclass field is
    # gone, otherwise they live forever in operator YAML as silent cruft.
    changes.extend(migrate_drops(data))

    if not changes:
        return None, []

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
