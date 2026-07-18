"""Runtime config singleton — loads `<vault>/.wiki/config.yaml` onto the schema.

The dataclasses (every knob's name, type, and default) live in the
side-effect-free `core.config_schema`; this module owns the side-effect side:
it reads the vault's `config.yaml` once at import time, merges it onto the
schema defaults, and exposes the result as the module-level singleton
`CONFIG` — import it from any script.

Usage:
    from core.config import CONFIG
    if CONFIG.features.curiosity_loop:
        ...
    timeout = CONFIG.limits.screenshot_timeout_seconds

Run this file directly to dump the loaded config (useful for debugging):
    uv run python scripts/core/config.py

Side effect on import: loads `<vault>/.claude/.env` via python-dotenv (so
every script that imports CONFIG gets secret env vars without manual shell
export) and derives `TIMEZONE` from `CONFIG.scheduling.timezone`. Pure path
constants live in `core/paths.py`; the datetime helpers in `core/utils.py`.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# config.py is both a package member (`from core.config import CONFIG`) AND a
# direct CLI (`wiki config` → `python scripts/core/config.py`). The bootstrap
# makes `from core.paths import …` resolve in the __main__ case too — relative
# `from .paths import` would raise "no known parent package" when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config_backup import backup_config_file  # noqa: E402
from core.paths import CONFIG_FILE, DOTENV_FILE  # noqa: E402

log = logging.getLogger(__name__)

# ── .env bootstrap ─────────────────────────────────────────────────────
# Loaded once at import time, before CONFIG is built. Idempotent (load_dotenv
# is itself idempotent). override=False — a shell export already in the env
# wins; .env is the fallback, not the authority. Missing file: graceful
# no-op (fresh-install vaults ship only `.env.example`).
load_dotenv(DOTENV_FILE, override=False)


# ── Schema re-export ──────────────────────────────────────────────────
# The dataclasses (every knob's name/type/default) live in the side-effect-
# free `core.config_schema` module so the migration + docs generator can
# import them without triggering this module's load()/dotenv side effects.
# Re-exported here so `from core.config import WikiConfig` keeps working.
from core.config_schema import (  # noqa: E402,F401
    DreamPriority,
    Features,
    GraphView,
    Limits,
    Models,
    Personal,
    PiggybackTask,
    Scheduling,
    Skills,
    WikiConfig,
    _default_piggybacks,
)


_HINTS_CACHE: dict[type, dict[str, Any]] = {}


def _annotation_for(dc: Any, field_name: str) -> Any:
    """Resolved type annotation for a dataclass field (cached per class).

    Returns None when the annotation can't be resolved — callers treat that
    as "accept anything" (the pre-typecheck legacy behavior).
    """
    import typing

    cls = type(dc)
    hints = _HINTS_CACHE.get(cls)
    if hints is None:
        try:
            hints = typing.get_type_hints(cls)
        except Exception:  # unresolvable forward ref — never block a load
            hints = {}
        _HINTS_CACHE[cls] = hints
    return hints.get(field_name)


def _type_compatible(hint: Any, raw: Any) -> bool:
    """Is a YAML-parsed override value assignable to a field of type `hint`?

    YAML-pragmatic rules: int satisfies float, list satisfies tuple (YAML has
    no tuple form), bool never satisfies int (True == 1 trap), unions accept
    any member. Unresolvable hints accept everything.
    """
    import types
    import typing

    if hint is None:
        return True
    origin = typing.get_origin(hint)
    if origin in (types.UnionType, typing.Union):
        return any(_type_compatible(arg, raw) for arg in typing.get_args(hint))
    if hint is type(None):
        return raw is None
    base = origin if origin is not None else hint
    if base is float:
        return isinstance(raw, (int, float)) and not isinstance(raw, bool)
    if base is int:
        return isinstance(raw, int) and not isinstance(raw, bool)
    if base is bool:
        return isinstance(raw, bool)
    if base is tuple:
        return isinstance(raw, (list, tuple))
    if isinstance(base, type):
        return isinstance(raw, base)
    return True


def _merge_dataclass(default: Any, override: dict[str, Any], *, path: str = "") -> Any:
    """Apply dict overrides onto a dataclass instance, recursively for nested dataclasses.

    Type-checked per field: an override whose YAML type doesn't fit the
    schema annotation is logged (WARNING, with its dotted key path) and the
    engine default is kept — a silently-wrong value used to propagate as-is
    and surface later as an unrelated runtime crash or, worse, as a knob the
    operator tuned that "does nothing".
    """
    if not is_dataclass(default) or not isinstance(override, dict):
        return default
    kwargs: dict[str, Any] = {}
    for f in fields(default):
        current = getattr(default, f.name)
        key_path = f"{path}.{f.name}" if path else f.name
        if f.name not in override:
            kwargs[f.name] = current
            continue
        raw = override[f.name]
        if is_dataclass(current):
            kwargs[f.name] = _merge_dataclass(current, raw or {}, path=key_path)
        elif not _type_compatible(_annotation_for(default, f.name), raw):
            log.warning(
                "config.yaml: %s = %r (%s) does not fit the schema type — "
                "keeping the engine default %r",
                key_path, raw, type(raw).__name__, current,
            )
            kwargs[f.name] = current
        else:
            kwargs[f.name] = raw
    return type(default)(**kwargs)


def _merge_piggybacks(
    defaults: dict[str, PiggybackTask], override: dict[str, Any] | None
) -> dict[str, PiggybackTask]:
    if not override:
        return defaults
    merged = dict(defaults)
    for name, raw in override.items():
        base = merged.get(name, PiggybackTask())
        if isinstance(raw, dict):
            merged[name] = _merge_dataclass(base, raw, path=f"piggybacks.{name}")
    return merged


class ConfigError(ValueError):
    """Raised when config.yaml has a structural problem the operator must fix."""


_LEGACY_ACCOUNT_FIELDS = {
    "mbox_paths",
    "filter_paths",
    "imap_host",
    "imap_user_env",
    "imap_pass_env",
    "has_procmail",
}


def _validate_accounts_schema(personal_raw: dict) -> None:
    """Reject the M001-era flat-account schema.

    M002 moved per-backend keys (mbox_paths, has_procmail, …) into
    nested `reader:` / `filter:` blocks. This function raises ConfigError
    pointing at the migration template if the legacy shape is detected.
    """
    accounts = (personal_raw or {}).get("accounts") or {}
    if not isinstance(accounts, dict):
        return
    offenders: list[tuple[str, list[str]]] = []
    for aid, body in accounts.items():
        if not isinstance(body, dict):
            continue
        legacy = sorted(_LEGACY_ACCOUNT_FIELDS & set(body))
        if legacy:
            offenders.append((aid, legacy))
    if not offenders:
        return

    lines = [
        "config.yaml uses the legacy account schema (pre-M002).",
        "Migrate each offending account to the nested reader/filter shape.",
        "",
        "Detected:",
    ]
    for aid, legacy_keys in offenders:
        lines.append(f"  - personal.accounts.{aid}: legacy keys {legacy_keys}")
    lines += [
        "",
        "Migration template (replace the flat keys per account):",
        "",
        "  personal:",
        "    accounts:",
        "      <id>:",
        "        email: <addr>",
        "        reader:",
        "          kind: thunderbird-mbox        # or gmail-api, etc.",
        "          mbox_paths: [INBOX.mbox, ...]",
        "        filter:",
        "          kind: all-inkl-procmail       # or thunderbird-msgfilter | gmail-api",
        "          imap_pass_env: <ENV_VAR_NAME>",
        "",
        "Full kind-table: CONTEXT.md § Account.kind.",
    ]
    raise ConfigError("\n".join(lines))


_WATCHED_FOLDER_KINDS = {"local", "smb"}


def _validate_watched_folders_schema(personal_raw: dict) -> None:
    """Validate personal.watched_folders entries (M027-S01).

    Each entry needs a non-empty `id` and `kind in {local, smb}`; `local`
    requires `path`, `smb` requires `share`. Raises ConfigError listing every
    offending entry. Validation only — no filesystem / SMB access here.
    """
    folders = (personal_raw or {}).get("watched_folders") or []
    if not isinstance(folders, list):
        raise ConfigError(
            "personal.watched_folders must be a list of "
            "{id, kind, path|share} entries."
        )
    offenders: list[str] = []
    for i, entry in enumerate(folders):
        if not isinstance(entry, dict):
            offenders.append(f"  - entry #{i}: not a mapping")
            continue
        fid = entry.get("id")
        label = fid if isinstance(fid, str) and fid.strip() else f"#{i}"
        if not isinstance(fid, str) or not fid.strip():
            offenders.append(f"  - entry {label}: missing required `id`")
            continue
        kind = entry.get("kind")
        if kind not in _WATCHED_FOLDER_KINDS:
            offenders.append(
                f"  - entry {label}: `kind` must be one of "
                f"{sorted(_WATCHED_FOLDER_KINDS)}, got {kind!r}"
            )
            continue
        if kind == "local" and not entry.get("path"):
            offenders.append(f"  - entry {label}: kind=local requires `path`")
        if kind == "smb" and not entry.get("share"):
            offenders.append(f"  - entry {label}: kind=smb requires `share`")
        # Optional per-root sensitivity tag (M027-S05, Q3 full build):
        # free operator vocabulary, stamped into answer artifacts and
        # propagated by compile. Marking only — the walk is the gate.
        sens = entry.get("sensitivity")
        if sens is not None and (not isinstance(sens, str) or not sens.strip()):
            offenders.append(
                f"  - entry {label}: `sensitivity` must be a non-empty "
                f"string when present, got {sens!r}"
            )
    if not offenders:
        return
    raise ConfigError(
        "\n".join(["personal.watched_folders has invalid entries:", ""] + offenders)
    )


def load() -> WikiConfig:
    cfg = WikiConfig()
    if not CONFIG_FILE.exists():
        return cfg
    try:
        raw = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        # Loud fallback: a parse error means EVERY operator override is being
        # ignored and the whole install silently runs on factory defaults —
        # historically this was a silent `return cfg` and near-impossible to
        # notice. logging's last-resort handler prints ERROR to stderr even
        # before any script configures logging.
        log.error(
            "config.yaml at %s is not valid YAML — ALL operator overrides are "
            "ignored; the engine runs on factory defaults until this is fixed: %s",
            CONFIG_FILE, e,
        )
        return cfg
    if not isinstance(raw, dict):
        log.error(
            "config.yaml at %s does not parse to a mapping (got %s) — ALL "
            "operator overrides are ignored; the engine runs on factory defaults.",
            CONFIG_FILE, type(raw).__name__,
        )
        return cfg
    _validate_accounts_schema(raw.get("personal") or {})
    _validate_watched_folders_schema(raw.get("personal") or {})
    cfg.scheduling = _merge_dataclass(cfg.scheduling, raw.get("scheduling") or {})
    cfg.piggybacks = _merge_piggybacks(cfg.piggybacks, raw.get("piggybacks"))
    cfg.models = _merge_dataclass(cfg.models, raw.get("models") or {})
    cfg.limits = _merge_dataclass(cfg.limits, raw.get("limits") or {})
    cfg.features = _merge_dataclass(cfg.features, raw.get("features") or {})
    cfg.graph_view = _merge_dataclass(cfg.graph_view, raw.get("graph_view") or {})
    cfg.skills = _merge_dataclass(cfg.skills, raw.get("skills") or {})
    cfg.personal = _merge_dataclass(cfg.personal, raw.get("personal") or {})
    return cfg


CONFIG: WikiConfig = load()


# ── Compile substrate scope policy ────────────────────────────────────
#
# Directories that the compile pipeline (substrate-walker AND
# compile-agent prompt scope) MUST NOT touch — as either Read or Write.
# Single source of truth referenced by every compile-walker so the
# air-gap policy lives in one place.
#
# `reports/` is hard-excluded per M019 DECISIONS.md (2026-05-17): the
# operator-self-reports surface must never flow back into compile, else
# a self-observation-bias feedback loop forms. The other entries are
# infrastructure paths that compile has never touched but listing them
# explicitly catches the case of a future walker that sweeps vault-root
# `*.md` blindly.
#
# Path-form is "<segment>/" with trailing slash — matched against the
# first path segment of a substrate-relative rel_path via startswith().
# `compile_main_system.md` SCOPE block lists the same set verbatim;
# operator-prompts and prompts must stay in sync.
COMPILE_SUBSTRATE_EXCLUDED_PREFIXES: tuple[str, ...] = (
    "reports/",
    ".wiki/",
    ".ytstack/",
    ".obsidian/",
    ".git/",
    ".claude/",
    "templates/",
)


# ── CLI helpers (used by the bash `wiki` entry point) ────────────────

def _walk(cfg: WikiConfig, parts: list[str]) -> object:
    """Walk a dot-notation path through the loaded WikiConfig."""
    obj: object = cfg
    for part in parts:
        if is_dataclass(obj) and not isinstance(obj, type):
            if part not in {f.name for f in fields(obj)}:
                raise KeyError(f"Unknown key: {'.'.join(parts)}")
            obj = getattr(obj, part)
        elif isinstance(obj, dict):
            if part not in obj:
                raise KeyError(f"Unknown key: {'.'.join(parts)}")
            obj = obj[part]
        else:
            raise KeyError(f"Cannot descend into {'.'.join(parts)} at {part!r}")
    return obj


def _coerce(value: str, hint: object) -> object:
    """Coerce a string CLI input toward the type currently in the config.

    Refuses list/dict/tuple targets outright: the old fall-through silently
    wrote the raw string over a structured value (`wiki config set
    limits.intent_source_globs foo` → globs replaced by the string "foo"),
    which the loader then dropped as a type mismatch — a two-step silent
    misconfig. Structured keys are edited in config.yaml directly.
    """
    if isinstance(hint, (list, tuple, dict)):
        raise ValueError(
            f"Refusing to set a {type(hint).__name__}-valued key from the CLI — "
            "edit config.yaml directly (YAML list/mapping syntax)."
        )
    if isinstance(hint, bool):
        if value.lower() in {"true", "1", "yes", "y", "on"}:
            return True
        if value.lower() in {"false", "0", "no", "n", "off"}:
            return False
        raise ValueError(f"Cannot parse {value!r} as bool")
    if isinstance(hint, int) and not isinstance(hint, bool):
        return int(value)
    if isinstance(hint, float):
        return float(value)
    if hint is None:
        # Try int → float → string
        for caster in (int, float):
            try:
                return caster(value)
            except ValueError:
                continue
    return value


def _enumerate_keys(prefix: str, obj: object) -> list[str]:
    keys: list[str] = []
    if is_dataclass(obj) and not isinstance(obj, type):
        for f in fields(obj):
            child = getattr(obj, f.name)
            sub = f"{prefix}.{f.name}" if prefix else f.name
            if is_dataclass(child) and not isinstance(child, type):
                keys.extend(_enumerate_keys(sub, child))
            elif isinstance(child, dict):
                # piggybacks: dict[str, PiggybackTask]
                for k, v in child.items():
                    keys.extend(_enumerate_keys(f"{sub}.{k}", v))
            else:
                keys.append(sub)
    return keys


_CONFIG_BACKUP_KEEP_LAST = 10


def _backup_config_before_write() -> Path | None:
    """Round-robin backup of CONFIG_FILE via the shared `core.config_backup` helper.

    One helper serves both write paths (this module's `wiki config set` and
    the standalone `migrations/migrate_config_keys.py`), so location, naming,
    and keep-count can never drift apart again.
    """
    return backup_config_file(CONFIG_FILE, keep_last=_CONFIG_BACKUP_KEEP_LAST)


def _set_in_yaml(key: str, value: object) -> None:
    """Update or insert key in the YAML file. Falls back to a fresh file when missing.

    Note: PyYAML drops comments on round-trip. Header banner is re-emitted
    so the YAML stays human-friendly.

    Side effect: every write is preceded by a round-robin backup of the
    current config (last `_CONFIG_BACKUP_KEEP_LAST` snapshots kept).
    """
    parts = key.split(".")
    if CONFIG_FILE.exists():
        try:
            raw = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                raw = {}
        except yaml.YAMLError as e:
            raise SystemExit(f"Existing {CONFIG_FILE} is not valid YAML: {e}")
    else:
        raw = {}

    cursor = raw
    for part in parts[:-1]:
        existing = cursor.get(part)
        if not isinstance(existing, dict):
            cursor[part] = {}
        cursor = cursor[part]
    cursor[parts[-1]] = value

    # Round-robin backup before overwriting.
    _backup_config_before_write()

    header = (
        "# Wiki Config — single source of truth for tunable parameters.\n"
        "# Defaults live in .wiki/scripts/core/config.py; only overrides need\n"
        "# to be in this file. Edit by hand or via `./.wiki/wiki config set …`.\n"
        "# Note: comments not present here are dropped on programmatic writes.\n"
        "# Round-robin backups in .wiki/state/config-backups/ (last 10 saves).\n\n"
    )
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        header + yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _cli() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Wiki config introspection / mutation")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("show", help="Print full resolved config (default)")
    g = sub.add_parser("get", help="Print one key (dot-notation, e.g. models.compile_model)")
    g.add_argument("key")
    s = sub.add_parser("set", help="Set a key and write back to config.yaml")
    s.add_argument("key")
    s.add_argument("value")
    sub.add_parser("keys", help="List all settable keys (dot-notation)")
    sub.add_parser("path", help="Print the config file path")
    args = p.parse_args()

    if args.cmd in (None, "show"):
        import json
        print(f"# {CONFIG_FILE} (exists={CONFIG_FILE.exists()})")
        print(json.dumps(asdict(CONFIG), indent=2, default=str))
        return 0

    if args.cmd == "path":
        print(CONFIG_FILE)
        return 0

    if args.cmd == "keys":
        for k in _enumerate_keys("", CONFIG):
            print(k)
        return 0

    if args.cmd == "get":
        try:
            val = _walk(CONFIG, args.key.split("."))
        except KeyError as e:
            print(e, file=__import__("sys").stderr)
            return 1
        if is_dataclass(val) and not isinstance(val, type):
            import json
            print(json.dumps(asdict(val), indent=2, default=str))
        else:
            print(val)
        return 0

    if args.cmd == "set":
        try:
            current = _walk(CONFIG, args.key.split("."))
        except KeyError as e:
            print(e, file=__import__("sys").stderr)
            return 1
        if is_dataclass(current) and not isinstance(current, type):
            print(
                f"Refusing to set {args.key!r} — it's a section, not a leaf. "
                f"Set individual fields under it instead.",
                file=__import__("sys").stderr,
            )
            return 1
        try:
            coerced = _coerce(args.value, current)
        except ValueError as e:
            print(e, file=__import__("sys").stderr)
            return 1
        _set_in_yaml(args.key, coerced)
        print(f"set {args.key} = {coerced!r}")
        return 0

    return 0


# ── Timezone ───────────────────────────────────────────────────────────
# Derived from CONFIG.scheduling.timezone (default "UTC"; override via
# config.yaml). Lives here — not in paths.py — because it's CONFIG-derived,
# not a pure path constant. flush_pipeline.py + others import it from here.
TIMEZONE = CONFIG.scheduling.timezone


if __name__ == "__main__":
    raise SystemExit(_cli())
