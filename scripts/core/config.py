"""Single source of truth for tunable wiki-system parameters.

Reads `<vault>/.wiki/config.yaml` once at import time. Falls back to dataclass
defaults when the file or individual keys are missing. Module-level
singleton `CONFIG` is the API — import it from any script.

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

import sys
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# config.py is both a package member (`from core.config import CONFIG`) AND a
# direct CLI (`wiki config` → `python scripts/core/config.py`). The bootstrap
# makes `from core.paths import …` resolve in the __main__ case too — relative
# `from .paths import` would raise "no known parent package" when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.paths import CONFIG_FILE, DOTENV_FILE  # noqa: E402

# ── .env bootstrap ─────────────────────────────────────────────────────
# Loaded once at import time, before CONFIG is built. Idempotent (load_dotenv
# is itself idempotent). override=False — a shell export already in the env
# wins; .env is the fallback, not the authority. Missing file: graceful
# no-op (fresh-install vaults ship only `.env.example`).
load_dotenv(DOTENV_FILE, override=False)


@dataclass
class Scheduling:
    compile_after_hour: int = 18
    dedup_window_seconds: int = 60
    # IANA timezone name used for human-friendly local-time decisions
    # (compile_after_hour cutoff, daily-log filename, "reviewed" timestamps).
    # Default UTC keeps installs portable; override per-instance via config.yaml.
    timezone: str = "UTC"


@dataclass
class PiggybackTask:
    enabled: bool = True
    cooldown_hours: int = 24
    max_per_run: int | None = None


@dataclass
class Models:
    compile_model: str = "claude-opus-4-7"
    # Compile fallback for sources >= CONFIG.limits.compile_large_source_chars.
    # The standard 200K-token Opus window dies silently (exit-1, empty stderr)
    # on 100+ KB transcripts even with max_turns capped — Read-tool fan-out into
    # knowledge/ articles plus the source itself blow past the window mid-stream.
    # The 1M variant absorbs both. Set to "" to disable the auto-upgrade and
    # stay on `compile_model` regardless of source size.
    compile_large_source_model: str = "claude-opus-4-7[1m]"
    ollama_url: str = "http://localhost:11434"
    vision_model: str = "gemma4:e4b"
    # Curiosity gap-detection. Needs *both* schema-honoring AND enough context
    # to fit the curiosity prompt (compact index + source + folder listing).
    # Decision matrix (skills/local-llm 2026-05-04 + 2026-05-15 probe):
    #   - gemma4:e4b → MT 9.16, 128k ctx, BUT ignores Ollama JSON-Schema entirely
    #     (invents `reasoning`/`suggested_action` field names). 6-week stillstand.
    #   - phi4:14b   → MT 9.26, but only **16k** ctx. lxw curiosity prompt is
    #     ~22-25k tokens (64 KB compact index dominates) → silent truncation,
    #     model reasons on a fragment, hallucinates topics from random index rows.
    #   - llama3.1:8b → MT 9.14, **128k** ctx, schema-honors ✓ (verified probe).
    #     Quality near-tie with phi4 without the context cliff. Right pick.
    curiosity_model: str = "llama3.1:8b"
    classify_model: str = "gemma4:e4b"


@dataclass
class Limits:
    compile_max_files: int = 30
    compile_max_consecutive_failures: int = 3
    flush_max_retries: int = 3
    flush_retry_delay_seconds: int = 30
    screenshot_resize_width: int = 512
    screenshot_timeout_seconds: int = 60
    curiosity_max_gaps: int = 3
    curiosity_min_source_chars: int = 500
    curiosity_timeout_s: int = 240         # ollama chat_schema timeout for curiosity gap-detection
                                           # (gemma4:e4b on long YT-notes regularly hits >90s)
    # Pre-flight cap for the curiosity-pass prompt (Ollama side, not Claude).
    # llama3.1:8b has 128k context (~430K chars at German density); we leave
    # headroom for the model's own response + cache. If the compact index
    # outgrows this, the producer truncates the index portion in-place
    # rather than aborting — curiosity is a nice-to-have, keep the loop
    # alive with reduced coverage. Symptom-on-overflow without this guard
    # is model-specific: 16k-window models (phi4) silently truncate and
    # hallucinate; 128k-window models eventually OOM-stall on Ollama side.
    curiosity_max_prompt_chars: int = 250_000
    # Curiosity quality gates (2026-05-15 quality arc).
    # `curiosity_source_globs`: only run curiosity on sources matching one
    # of these fnmatch patterns. Memories / knowledge / hard-facts get
    # skipped — they're cognitive self-notes with no email-side context.
    # Operator can override (e.g. empty list = run on everything).
    curiosity_source_globs: list[str] = field(default_factory=lambda: [
        "raw/transcripts/*",
        "raw/articles/*",
        "raw/notes/*",
        "daily/*",
    ])
    # `curiosity_folder_confidence_min`: integer 1-5 self-reported by the
    # LLM per gap. Below this threshold the producer drops the gap with
    # `folder_low_confidence`. Forces the model to hedge openly instead
    # of defaulting to a generic catch-all folder.
    curiosity_folder_confidence_min: int = 3
    # `curiosity_quote_min_anchor_tokens`: the source_quote gate accepts the
    # quote if ANY contiguous N-token window from the (normalised) quote
    # appears in the (normalised) source excerpt. Strict whole-quote
    # substring is too brittle — LLMs routinely add interpretive
    # prefix/suffix or paraphrase the edges while keeping a verbatim core.
    # Token-window anchor is verifiable AND tolerant of those cosmetic
    # edits. 5 is a healthy minimum — a 5-word phrase rarely matches by
    # accident, so a model that returns a 5+ token verbatim block is
    # genuinely citing the source.
    curiosity_quote_min_anchor_tokens: int = 5
    sparse_threshold_words: int = 200
    # YouTube ingest (scan-youtube.py — see also CONFIG.piggybacks.scan_youtube)
    youtube_max_frames: int = 30          # Tier-3 visual: cap frames per video
    youtube_max_duration_s: int = 10800   # Tier-3: skip videos longer than this (3h default)
    youtube_frame_resize_width: int = 512  # ffmpeg downscale before vision model
    youtube_vision_timeout_s: int = 90    # per-frame ollama call timeout
    youtube_aggregate_timeout_s: int = 300  # final synthesis call timeout
    # Jamie ingest (collectors/jamie.py — see also CONFIG.piggybacks.jamie).
    # Multi-tenant: per-account jamie block under personal.accounts.<id>.jamie
    # (kind: jamie-api, api_key_env, key_type, since, max_per_run).
    jamie_request_timeout_s: int = 30     # per-HTTP-call timeout against api.meetjamie.ai
    jamie_max_per_run: int = 50           # default cap per account (overridable via the per-account jamie sub-block)
    # Google Meet ingest (collectors/gmeet.py — see also CONFIG.piggybacks.gmeet).
    # Multi-tenant: per-account gmeet block under personal.accounts.<id>.gmeet
    # (kind: gmeet-api, drive_folder_id, drive_folder_name, since, max_per_run).
    gmeet_request_timeout_s: int = 30     # per-HTTP-call timeout against the Drive API
    gmeet_max_per_run: int = 50           # default cap; per-account override is the gmeet sub-block's max_per_run
    # Claude Agent SDK per-message buffer (stream-json line buffer). SDK default is
    # 1 MB; trips on tool-result messages carrying knowledge/index.md (~300 KB raw,
    # ~600 KB JSON-escaped) or Write/Edit calls on large articles, with a confusing
    # `Failed to decode JSON: ... exceeded maximum buffer size of 1048576 bytes`
    # exception. Bumped to 50 MB by default — safe headroom for any realistic
    # single-message scenario without hiding real runaway responses.
    sdk_max_buffer_size_mb: int = 50
    # Pre-flight cap for `wiki query` prompts. A query embeds the compact
    # index + hard facts; once the knowledge base outgrows the model's
    # context window the SDK dies with an opaque exit-1 / empty-stderr
    # `kind=unknown`. Tripping this limit first turns that into a clear
    # operator message. 500K chars ≈ 167K tokens at German density —
    # inside a 200K-token window with headroom for the response.
    query_max_prompt_chars: int = 500_000
    # Pre-flight cap for `wiki compile` prompts. Embeds compact index +
    # AGENTS.md + facts + raw source. Same overflow class as query, but
    # the source content varies wildly (small daily notes vs 100+ KB
    # gmeet transcripts) — the budget guard catches outliers before they
    # cost 13 minutes of opaque kind=unknown silence. 400K chars ≈ 110K
    # tokens initial; the remaining ~90K tokens absorb tool-turn growth.
    compile_max_prompt_chars: int = 400_000
    # Tool-turn ceiling per compile run. 30 was generous enough to let
    # the model loop on a huge source until it hit the context window
    # (see KNOWLEDGE.md: gmeet 138 KB transcript). 12 is what lint.py /
    # suggestions/ already run with and matches the actual depth of
    # legitimate compiles (read index → grep → read 2-4 articles → write).
    compile_max_turns: int = 12
    # Threshold above which a source counts as "large" — surfaces one
    # extra INFO line so the operator can see *which* file was big when
    # the SDK call slows down. Pure logging signal, no behavior change.
    compile_large_source_chars: int = 50_000
    # Retry once with `compile_large_source_model` (the 1M-context Opus
    # variant) when a compile call returns kind=unknown — the silent
    # exit-1 / empty-stderr signature of mid-stream context overflow from
    # tool-turn fan-out into knowledge/ articles. The 50 KB source-size
    # threshold catches deterministic overflows; this retry catches the
    # stochastic ones on small sources where the same file succeeds 70%
    # of the time and fails 30%. Off-switch for operators who would
    # rather see the failure than pay the 1M-variant premium.
    compile_retry_long_context_on_unknown: bool = True


@dataclass
class Features:
    curiosity_loop: bool = True
    vision_screenshots: bool = True
    procmail_execution: bool = True
    # Pre-compile sweep of <vault>/Clippings/*.md into <vault>/raw/articles/
    # so Obsidian Web Clipper output reaches the source-glob. Cheap no-op when
    # Clippings/ is empty or absent. Set false if you reconfigure the Web
    # Clipper extension to drop directly into raw/articles/.
    clippings_sweep: bool = True


@dataclass
class GraphView:
    mode: str = "knowledge-only"
    custom_search: str = ""
    # Tag names treated as "domain anchors" for graph-view coloring and
    # qa-schema lint. Notes carrying at least one of these get a meaningful
    # color in the graph; notes without any fall into the grey fallback.
    # Empty list = use the engine default (see scripts/lint.py
    # _DEFAULT_DOMAIN_TAGS). Override per vault in config.yaml:
    #   graph_view:
    #     domain_tags: [fleet, openclaw, my-product]
    domain_tags: list[str] = field(default_factory=list)


@dataclass
class Skills:
    """Engine-skill distribution preferences (see `wiki skills`)."""

    # When true, `wiki skills install` / `wiki skills sync` also link
    # global-eligible skills (currently: use-llm-wiki) into ~/.claude/skills/
    # and register this vault in ~/.config/llm-wiki/vaults, so agents working
    # in *any* project can discover and query this wiki. Opt-in — default
    # false keeps the install vault-local (the other bundled skills are always
    # vault-local; they operate inside a vault).
    global_install: bool = False


# Note (2026-05-15, multi-tenant policy): both `gmeet` and `jamie` are
# account-bound — their config lives per-account under
# `personal.accounts.<id>.{gmeet,jamie}` with `kind: gmeet-api` / `jamie-api`,
# mirroring the email Reader/Filter sub-block pattern.
# `collectors/{gmeet,jamie}.py:_resolve_*_accounts()` read the dispatch.


@dataclass
class Personal:
    """Per-instance data that must NOT be committed.

    Defaults are empty so prompts/schema render cleanly even on a fresh
    install. Populate via local config.yaml.
    """
    # default account; used as fallback in compile.py and for prompt rendering
    primary_account: str = ""
    # account-id -> per-account dict. Schema (M002+):
    #   email   (str)               sender identity; required
    #   label   (str, optional)     display label in reports
    #   reader  (dict, optional)    {kind: thunderbird-mbox|gmail-api|…, <kind-specific keys>}
    #   filter  (dict, optional)    {kind: thunderbird-msgfilter|all-inkl-procmail|gmail-api|…, …}
    # See [CONTEXT.md § Account.kind] and [scripts/adapters/mailbox/__init__.py]
    # for the full kind-table. resolve_reader / resolve_filter dispatch on
    # reader.kind / filter.kind respectively. Unknown kinds are silently
    # skipped (graceful agnostic).
    #
    # Legacy top-level fields (mbox_paths, filter_paths, imap_host,
    # imap_user_env, imap_pass_env, has_procmail) are NO LONGER ACCEPTED
    # — load() raises ConfigError pointing at the migration template.
    accounts: dict[str, dict] = field(default_factory=dict)
    # ordered list of {path, desc} dicts; drives both compile_curiosity.md
    # listing AND compile.py's schema enum (single source of truth)
    email_folders: list[dict] = field(default_factory=list)
    # Optional subset of email_folder paths considered by the curiosity loop.
    # Empty list (default) = use all email_folders. Operator-curated allowlist
    # lets you exclude generic catch-alls (e.g. "INBOX/COMPANY/00 COMPANY")
    # that the LLM otherwise picks as a fallback when no specific folder fits.
    # Paths in this list must match a `path:` entry in email_folders; unknown
    # paths are dropped silently with a one-time WARNING on load.
    curiosity_folders: list[str] = field(default_factory=list)
    # short list of project / product names rendered into
    # scan_screenshots_vision.md as concrete examples
    project_examples: list[str] = field(default_factory=list)
    # Substring keywords that mark calendar events as work-relevant in
    # scan-calendar.py (customer/partner/team names).
    calendar_work_keywords: list[str] = field(default_factory=list)
    # Substring keywords whose presence in a calendar event title marks it as a
    # holiday / observance to skip during scan-calendar.py. Locale-specific
    # (e.g. ["Christmas", "Easter"] for English; ["Weihnacht", "Ostern"] for
    # German). Empty list = no skipping.
    calendar_skip_keywords: list[str] = field(default_factory=list)
    # Mapping of category-label -> list of substring keywords used by
    # scan-calendar.py to bucket events. First match wins, so put more
    # specific categories before generic ones in your config.yaml.
    # Example:
    #   calendar_categories:
    #     "Workshops": ["workshop", "training"]
    #     "Concerts":  ["concert", "festival"]
    calendar_categories: dict[str, list[str]] = field(default_factory=dict)
    # Output language for the calendar scan report. "en" or "de".
    calendar_report_language: str = "en"
    # Path to local Thunderbird profile directory (mbox + filter roots live here).
    # Empty string disables the email Collector's thunderbird-mbox adapter
    # and the scan-calendar legacy CLI (both consume the Thunderbird profile).
    thunderbird_profile: str = ""
    # Path to a local Firefox profile directory (e.g. ~/Library/Application
    # Support/Firefox/Profiles/<id>.default-release on macOS, or
    # ~/.mozilla/firefox/<id>.default-release on Linux). Empty string disables
    # the Firefox half of scan-browser.py.
    firefox_profile: str = ""
    # Path to a Simple Tab Groups (STG) backup directory (where the extension
    # writes its periodic *.json snapshots). Empty string disables STG-import
    # paths in scan-tabs.py / scan-browser.py.
    stg_backup_dir: str = ""
    # Path to a directory the operator dumps dictation transcripts into
    # (any tool that writes .txt or .md works — OpenWhispr is the default
    # recommendation; FluidVoice / macOS dictation / Hammerspoon snippets
    # also work). Empty string disables collectors/voice.py.
    voice_inbox: str = ""
    # Jamie AI + Google Meet integrations are multi-tenant via per-account
    # `jamie:` / `gmeet:` sub-blocks under `personal.accounts.<id>` (kinds:
    # `jamie-api`, `gmeet-api`). No flat dataclass — resolved at run time by
    # `collectors/{jamie,gmeet}.py:_resolve_*_accounts()`.


# Default piggyback set — script names match flush.py's PIGGYBACK_TASKS keys.
def _default_piggybacks() -> dict[str, PiggybackTask]:
    return {
        "email_incremental": PiggybackTask(cooldown_hours=24),
        "lint_structural": PiggybackTask(cooldown_hours=24),
        "review_wiki": PiggybackTask(cooldown_hours=168),
        "optimize_claude_md": PiggybackTask(cooldown_hours=24),
        "screenshots": PiggybackTask(cooldown_hours=24, max_per_run=50),
        "curiosity_followup": PiggybackTask(cooldown_hours=24),
        "jamie": PiggybackTask(cooldown_hours=6, max_per_run=20),
        "gmeet": PiggybackTask(cooldown_hours=6, max_per_run=20),
        "voice": PiggybackTask(cooldown_hours=1),
        "retry_failed_flushes": PiggybackTask(cooldown_hours=24, max_per_run=5),
    }


@dataclass
class WikiConfig:
    scheduling: Scheduling = field(default_factory=Scheduling)
    piggybacks: dict[str, PiggybackTask] = field(default_factory=_default_piggybacks)
    models: Models = field(default_factory=Models)
    limits: Limits = field(default_factory=Limits)
    features: Features = field(default_factory=Features)
    graph_view: GraphView = field(default_factory=GraphView)
    skills: Skills = field(default_factory=Skills)
    personal: Personal = field(default_factory=Personal)


def _merge_dataclass(default: Any, override: dict[str, Any]) -> Any:
    """Apply dict overrides onto a dataclass instance, recursively for nested dataclasses."""
    if not is_dataclass(default) or not isinstance(override, dict):
        return default
    kwargs: dict[str, Any] = {}
    for f in fields(default):
        current = getattr(default, f.name)
        if f.name not in override:
            kwargs[f.name] = current
            continue
        raw = override[f.name]
        if is_dataclass(current):
            kwargs[f.name] = _merge_dataclass(current, raw or {})
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
            merged[name] = _merge_dataclass(base, raw)
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
    for aid, fields in offenders:
        lines.append(f"  - personal.accounts.{aid}: legacy keys {fields}")
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


def load() -> WikiConfig:
    cfg = WikiConfig()
    if not CONFIG_FILE.exists():
        return cfg
    try:
        raw = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        # Fall back silently to defaults — scripts log this at usage site.
        return cfg
    if not isinstance(raw, dict):
        return cfg
    _validate_accounts_schema(raw.get("personal") or {})
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
    """Coerce a string CLI input toward the type currently in the config."""
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


_CONFIG_BACKUP_DIR_NAME = "config-backups"
_CONFIG_BACKUP_KEEP_LAST = 10


def _backup_dir() -> Path:
    """Where round-robin config backups live: `<.wiki>/state/config-backups/`."""
    # CONFIG_FILE (from paths.py) = <wiki>/config.yaml → its parent is <wiki>.
    wiki_dir = CONFIG_FILE.parent
    return wiki_dir / "state" / _CONFIG_BACKUP_DIR_NAME


def _backup_config_before_write() -> Path | None:
    """Round-robin backup: snapshot the current config to a timestamped file.

    Keeps the last `_CONFIG_BACKUP_KEEP_LAST` snapshots, prunes older.
    Returns the backup path on success, None when there's nothing to back up.
    Failures are logged but don't abort the calling save (defensive — losing
    a backup is better than blocking a config write).
    """
    if not CONFIG_FILE.exists():
        return None
    try:
        bdir = _backup_dir()
        bdir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = bdir / f"config-{ts}.yaml"
        # Avoid overwrite within same second — append micro-suffix.
        if out.exists():
            out = bdir / f"config-{ts}-{datetime.now(timezone.utc).microsecond:06d}.yaml"
        out.write_bytes(CONFIG_FILE.read_bytes())

        # Prune oldest beyond keep-count.
        existing = sorted(bdir.glob("config-*.yaml"))
        if len(existing) > _CONFIG_BACKUP_KEEP_LAST:
            for stale in existing[: -_CONFIG_BACKUP_KEEP_LAST]:
                try:
                    stale.unlink()
                except OSError:
                    pass
        return out
    except OSError:
        return None


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
