"""The `wiki` command catalogue — the single source of truth for what subcommands exist,
how they run, and how they show up in `wiki help` and the interactive menu.

`COMMANDS` is the table (C06: it replaced four hand-synced catalogues — a header comment
printed by `wiki help`, per-command heredocs, each script's argparse, and `menu.py`'s
hand-curated list). `cli` dispatches it and renders `wiki help` from it; the per-command
help texts live in `cli_help`; `menu.py`'s coverage is pinned against this table by a
test. `AUTH_SERVICES` is the OAuth registry `wiki auth <service> <account-id>` dispatches
over.
"""

from __future__ import annotations

from dataclasses import dataclass

from cli_help import (
    H_AGENT,
    H_ANALYZE,
    H_AUTH,
    H_BACKFILL,
    H_BRIDGE,
    H_COLLECT,
    H_COMPILE,
    H_CONFIG,
    H_CORRECT,
    H_CURIOSITY,
    H_DEDUP,
    H_DOCTOR,
    H_DREAM,
    H_DREAM_ENTITY,
    H_FLUSH,
    H_HEALTH_TRENDS,
    H_HOOKS,
    H_INDEX,
    H_INGEST_HTML,
    H_INGEST_YOUTUBE,
    H_INSTALL_SHORTCUT,
    H_LINKS,
    H_LINT,
    H_MENU,
    H_PIN,
    H_PREPROCESS,
    H_PROCESS_INBOX,
    H_PRODUCE,
    H_PUBLISH,
    H_QUERY,
    H_RECONCILE,
    H_REINDEX,
    H_REVIEW_WIKI,
    H_SEED,
    H_SETUP,
    H_SKILLS,
    H_STATS,
    H_STATUS,
    H_STUDY,
    H_SUGGESTIONS,
    H_TAKE,
    H_TRIAGE,
    H_UPDATE,
    H_USAGE,
    H_VERSION,
)

# ── Command spec ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SubRoute:
    """A first-arg-selected alternate handler for one command.

    `wiki correct apply …` and `wiki backfill picture-metadata …` route to a
    different script than the command's default handler; a SubRoute captures
    that (its `key` is consumed, remaining args pass through, after `args` — so
    `wiki dream list-candidates` runs `dream.py list-candidates`). A `None` banner is
    a machine-readable route (`wiki menu --json`): the payload alone on stdout."""

    key: str
    script: str
    banner: str | None
    subtitle: str | None = None
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandSpec:
    """One `wiki <name>` subcommand.

    kind:
      "py"       dispatched here — run `handler` as a child process.
      "bash"     dispatched by the `wiki` bash layer (bootstrap / genuinely-bash
                 commands); listed here only so help + menu stay complete.
      "auth"     the OAuth registry front-door (`wiki auth <service> <id>`).
      "alias"    another spelling: `alias_of` + the rest of argv is dispatched instead
                 (`wiki gmail-auth x` → `wiki auth gmail x`).
    """

    name: str
    group: str
    summary: str
    kind: str = "py"
    handler: str | None = None  # script path relative to scripts/
    banner: bool = True
    banner_subtitle: str | None = None
    refresh_after: bool = False  # refresh dashboards once, locked, after
    needs_vault: bool = True  # informational; the bash guard enforces it
    show_help_on_empty: bool = False  # bare `wiki <name>` prints help
    empty_help_exit: int = 0  # exit code for the bare-help case
    menu: bool = False  # expected to be reachable from menu.py
    help_text: str | None = None  # rich per-command help (was a bash heredoc)
    subroutes: tuple[SubRoute, ...] = ()
    takes_args: bool = True  # False: a word no subroute names is refused, not passed on
    handler_args: tuple[str, ...] = ()  # put before argv for `handler` (dream-entity → entity)
    default_route: str | None = None  # route key for no args or a leading flag (dream → sweep)
    alias_of: tuple[str, ...] = ()  # kind "alias": the argv this name stands for


# ── The catalog ─────────────────────────────────────────────────────────
# Order within a group is the render order in `wiki help`.

COMMANDS: tuple[CommandSpec, ...] = (
    # Home & status
    CommandSpec(
        "menu",
        "Home & status",
        "interactive home screen (--json for agents)",
        handler="menu.py",
        banner=False,
        needs_vault=False,
        help_text=H_MENU,
        subroutes=(SubRoute("--json", "menu_context.py", banner=None),),
        takes_args=False,
    ),
    CommandSpec(
        "status",
        "Home & status",
        "config + hooks + Ollama summary",
        handler="status_cli.py",
        menu=True,
        takes_args=False,
        help_text=H_STATUS,
    ),
    CommandSpec(
        "doctor",
        "Home & status",
        "vault-health audit (--quick / --json)",
        handler="doctor.py",
        banner=False,
        help_text=H_DOCTOR,
    ),
    CommandSpec(
        "stats",
        "Home & status",
        "read-only vault dashboard (what's in the vault)",
        handler="health.py",
        banner=False,
        help_text=H_STATS,
    ),
    CommandSpec(
        "version",
        "Home & status",
        "print installed git revision",
        handler="engine_version.py",
        banner=False,
        needs_vault=False,
        menu=True,
        help_text=H_VERSION,
    ),
    # Setup
    CommandSpec(
        "setup",
        "Setup",
        "first-time setup (config wizard + hooks)",
        handler="setup_cli.py",
        banner_subtitle="First-time setup: config wizard, then hook install.",
        menu=True,
        help_text=H_SETUP,
    ),
    CommandSpec(
        "config",
        "Setup",
        "interactive config editor (get/set/keys/…)",
        handler="config_cli.py",
        banner=False,
        menu=True,
        help_text=H_CONFIG,
    ),
    CommandSpec(
        "hooks",
        "Setup",
        "install/uninstall session hooks per agent",
        handler="hooks_cli.py",
        banner=False,  # the handler prints its own, so `wiki setup` gets it in-process
        menu=True,
        help_text=H_HOOKS,
    ),
    CommandSpec(
        "skills",
        "Setup",
        "wire engine skills into .claude/skills/",
        handler="skills_cli.py",
        banner=False,  # the handler prints its own (sync prints none: `wiki update` runs it)
        menu=True,
        help_text=H_SKILLS,
    ),
    CommandSpec(
        "install-shortcut",
        "Setup",
        "symlink ~/.local/bin/wiki -> this vault",
        handler="shortcut_cli.py",
        needs_vault=False,
        help_text=H_INSTALL_SHORTCUT,
    ),
    CommandSpec(
        "update",
        "Setup",
        "git pull --ff-only + sync deps/skills",
        # the second phase (`--post-pull <rev>`); the pull is the bash's until M034-S05-T03
        handler="update_cli.py",
        banner=False,
        menu=True,
        help_text=H_UPDATE,
    ),
    CommandSpec(
        "seed",
        "Setup",
        "re-apply engine templates to the vault",
        handler="seed_cli.py",
        banner=False,  # the handler prints its own: the mode line, or --extract-custom's
        menu=True,
        help_text=H_SEED,
    ),
    # Collect & ingest
    CommandSpec(
        "collect",
        "Collect & ingest",
        "run a Collector (--list to enumerate)",
        handler="collectors/cli.py",
        banner=False,
        menu=True,
        help_text=H_COLLECT,
    ),
    CommandSpec(
        "index",
        "Collect & ingest",
        "body-blind folder-index digests",
        handler="index_folders.py",
        help_text=H_INDEX,
    ),
    CommandSpec(
        "produce",
        "Collect & ingest",
        "run a Producer (post-compile extractor)",
        handler="producers/cli.py",
        banner=False,
        menu=True,
        help_text=H_PRODUCE,
    ),
    CommandSpec(
        "preprocess",
        "Collect & ingest",
        "run a Preprocessor (--list to enumerate)",
        handler="preprocessors/cli.py",
        banner=False,
        menu=True,
        help_text=H_PREPROCESS,
    ),
    CommandSpec(
        "process-inbox",
        "Collect & ingest",
        "classify inbox/ files via Ollama",
        handler="process_inbox.py",
        menu=True,
        help_text=H_PROCESS_INBOX,
    ),
    CommandSpec(
        "ingest-html",
        "Collect & ingest",
        "convert an HTML file or URL into raw/",
        handler="ingest_html.py",
        menu=True,
        help_text=H_INGEST_HTML,
    ),
    CommandSpec(
        "ingest-youtube",
        "Collect & ingest",
        "pull YouTube videos into raw/notes/",
        handler="ingest_youtube.py",
        menu=True,
        help_text=H_INGEST_YOUTUBE,
    ),
    CommandSpec(
        "bridge",
        "Collect & ingest",
        "rsync mirror for sandbox-restricted folders",
        handler="bridge/cli.py",
        banner=False,
        menu=True,
        help_text=H_BRIDGE,
    ),
    CommandSpec(
        "backfill",
        "Collect & ingest",
        "one-shot data-shape upgrades",
        handler=None,
        banner=False,
        show_help_on_empty=True,
        menu=True,
        help_text=H_BACKFILL,
        subroutes=(
            SubRoute(
                "picture-metadata", "backfill_picture_metadata.py", "wiki backfill picture-metadata"
            ),
            SubRoute(
                "voice-source-frontmatter",
                "backfill_voice_source_frontmatter.py",
                "wiki backfill voice-source-frontmatter",
            ),
            SubRoute(
                "tasks-to-workspace",
                "backfill_tasks_to_workspace.py",
                "wiki backfill tasks-to-workspace",
            ),
        ),
    ),
    CommandSpec(
        "auth",
        "Collect & ingest",
        "OAuth bootstrap (gmail/gmeet/calendar)",
        kind="auth",
        help_text=H_AUTH,
    ),
    CommandSpec(
        "gmail-auth",
        "Collect & ingest",
        "alias: wiki auth gmail <account-id>",
        kind="alias",
        menu=True,
        alias_of=("auth", "gmail"),
    ),
    CommandSpec(
        "gmeet-auth",
        "Collect & ingest",
        "alias: wiki auth gmeet <account-id>",
        kind="alias",
        menu=True,
        alias_of=("auth", "gmeet"),
    ),
    CommandSpec(
        "calendar-auth",
        "Collect & ingest",
        "alias: wiki auth calendar <account-id>",
        kind="alias",
        menu=True,
        alias_of=("auth", "calendar"),
    ),
    # Knowledge ops
    CommandSpec(
        "compile",
        "Knowledge ops",
        "compile changed (or all) sources into knowledge/",
        handler="compile.py",
        refresh_after=True,
        menu=True,
        help_text=H_COMPILE,
    ),
    CommandSpec(
        "dream",
        "Knowledge ops",
        "sweep all entity pages (oldest-overdue first)",
        menu=True,
        help_text=H_DREAM,
        # bare `wiki dream` and bare flags (`--dry-run --limit 3`) are a sweep; a word no
        # route names is refused (M034-S01-T06, the former bash case table)
        subroutes=(
            SubRoute("sweep", "dream.py", "wiki dream sweep", args=("sweep",)),
            SubRoute("--all-entities", "dream.py", "wiki dream sweep", args=("sweep",)),
            SubRoute(
                "list-candidates",
                "dream.py",
                "wiki dream list-candidates",
                args=("list-candidates",),
            ),
            SubRoute(
                "--list-candidates",
                "dream.py",
                "wiki dream list-candidates",
                args=("list-candidates",),
            ),
            SubRoute("web-research", "dream.py", "wiki dream web-research", args=("web-research",)),
            SubRoute(
                "--web-research-only",
                "dream.py",
                "wiki dream web-research",
                args=("web-research",),
            ),
        ),
        default_route="sweep",
        takes_args=False,
    ),
    CommandSpec(
        "dream-entity",
        "Knowledge ops",
        "re-synthesize ONE entity page by slug",
        handler="dream.py",
        handler_args=("entity",),
        show_help_on_empty=True,
        menu=True,
        help_text=H_DREAM_ENTITY,
    ),
    CommandSpec(
        "query",
        "Knowledge ops",
        "ask the knowledge base in natural language",
        handler="query.py",
        show_help_on_empty=True,
        menu=True,
        help_text=H_QUERY,
    ),
    CommandSpec(
        "lint",
        "Knowledge ops",
        "structural + LLM contradiction health check",
        handler="lint.py",
        refresh_after=True,
        menu=True,
        help_text=H_LINT,
    ),
    CommandSpec(
        "links",
        "Knowledge ops",
        "broken-wikilink report (--fix to rewrite)",
        handler="links_audit.py",
        help_text=H_LINKS,
    ),
    CommandSpec(
        "pin",
        "Knowledge ops",
        "pin an article into a Map-of-Content",
        handler="pin.py",
        banner=False,
        menu=True,
        help_text=H_PIN,
    ),
    CommandSpec(
        "publish",
        "Knowledge ops",
        "mirror the vault into meinkontext (--auth once, --dry-run, run)",
        handler="publish/cli.py",
        help_text=H_PUBLISH,
    ),
    CommandSpec(
        "reindex",
        "Knowledge ops",
        "reconcile index.md against the corpus (--dry-run)",
        handler="reindex.py",
        help_text=H_REINDEX,
    ),
    CommandSpec(
        "review-wiki",
        "Knowledge ops",
        "per-article quality scores (local LLM, free)",
        handler="review_wiki.py",
        menu=True,
        help_text=H_REVIEW_WIKI,
    ),
    CommandSpec(
        "health-trends",
        "Knowledge ops",
        "deterministic health-trend synthesis ($0)",
        handler="health_trends.py",
        menu=True,
        help_text=H_HEALTH_TRENDS,
    ),
    CommandSpec(
        "agent",
        "Knowledge ops",
        "run an agentic task (prompts/agents/<id>.md)",
        handler="agent_task.py",
        menu=True,
        help_text=H_AGENT,
    ),
    # Facts & takes
    CommandSpec(
        "correct",
        "Facts & takes",
        "record hard facts that override compiled content",
        handler="facts/correct.py",
        refresh_after=True,
        show_help_on_empty=True,
        empty_help_exit=1,
        menu=True,
        help_text=H_CORRECT,
        subroutes=(
            SubRoute(
                "apply",
                "facts/correct_apply.py",
                "wiki correct apply",
                "Agentic propagation — Claude Agent SDK over vault root.",
            ),
        ),
    ),
    CommandSpec(
        "take",
        "Facts & takes",
        "record third-party belief attribution (M011)",
        handler="facts/take.py",
        refresh_after=True,
        show_help_on_empty=True,
        empty_help_exit=1,
        menu=True,
        help_text=H_TAKE,
    ),
    CommandSpec(
        "dedup",
        "Facts & takes",
        "find + merge STT-noise duplicate entity pages",
        handler="dedup.py",
        refresh_after=True,
        menu=True,
        help_text=H_DEDUP,
    ),
    # Review & maintenance
    CommandSpec(
        "flush",
        "Review & maintenance",
        "extract a disposable context file to daily/",
        handler="flush.py",
        menu=True,
        help_text=H_FLUSH,
        show_help_on_empty=True,
        empty_help_exit=2,
    ),
    CommandSpec(
        "curiosity",
        "Review & maintenance",
        "review + run curiosity deep-scan requests",
        handler="curiosity/cli.py",
        menu=True,
        help_text=H_CURIOSITY,
    ),
    CommandSpec(
        "suggestions",
        "Review & maintenance",
        "review + execute optimization suggestions",
        handler="suggestions/cli.py",
        menu=True,
        help_text=H_SUGGESTIONS,
    ),
    CommandSpec(
        "reconcile",
        "Review & maintenance",
        "autonomous concept-consistency routine",
        handler="reconcile.py",
        menu=True,
        help_text=H_RECONCILE,
    ),
    CommandSpec(
        "triage",
        "Review & maintenance",
        "review + clear the intent inbox",
        handler="triage.py",
        banner=False,
        menu=True,
        help_text=H_TRIAGE,
    ),
    CommandSpec(
        "study",
        "Review & maintenance",
        "operator-self-reports surface (M019)",
        handler="study.py",
        menu=True,
        help_text=H_STUDY,
    ),
    CommandSpec(
        "analyze",
        "Review & maintenance",
        "operator-self-reports analyst layer",
        handler="analyze.py",
        menu=True,
        help_text=H_ANALYZE,
    ),
    CommandSpec(
        "usage",
        "Review & maintenance",
        "token-usage ledger (per provider/model)",
        handler="usage_report.py",
        menu=True,
        help_text=H_USAGE,
    ),
    # Help
    CommandSpec("help", "Help", "this message", kind="bash", needs_vault=False),
)

BY_NAME: dict[str, CommandSpec] = {c.name: c for c in COMMANDS}

# Render order for the grouped `wiki help` catalog.
_GROUP_ORDER = (
    "Home & status",
    "Setup",
    "Collect & ingest",
    "Knowledge ops",
    "Facts & takes",
    "Review & maintenance",
    "Help",
)


# ── OAuth registry ──────────────────────────────────────────────────────
# service -> (module, function). The account id is passed to the function as an
# argument (never interpolated into source), killing the python -c injection
# hazard the three bash bootstrap sites carried.
AUTH_SERVICES: dict[str, tuple[str, str]] = {
    "gmail": ("adapters.mailbox.gmail", "gmail_auth_bootstrap"),
    "gmeet": ("collectors.gmeet", "gmeet_auth_bootstrap"),
    "calendar": ("collectors.calendar_collector", "calendar_auth_bootstrap"),
}
