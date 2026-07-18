"""Table-driven dispatcher for the `wiki` CLI — the single source of truth
for what Python-backed subcommands exist, how they run, and how they show up
in `wiki help` and the interactive menu.

Why this module exists (architecture-deepening C06)
----------------------------------------------------
The `wiki` bash entry-point used to maintain the command catalog in four
hand-synced places (a header comment printed by `wiki help`, per-command
heredocs, each script's argparse, and `menu.py`'s hand-curated catalog). All
four drifted — `wiki help` was blind to 9 dispatcher-known commands. This
module inverts the ownership: the `CommandSpec` table below is the catalog.
`wiki help` renders from it (every command visible), the bash layer shrinks to
bootstrap + the genuinely-bash commands and delegates everything else here, and
`menu.py`'s coverage is pinned against this table by a test.

It also concentrates two policies the bash layer used to re-implement unsafely:

* Post-command dashboard refresh runs ONCE, through `flush.py`'s existing
  fcntl-locked implementation (imported, never reimplemented) — replacing eight
  copy-pasted, unlocked bash call sites that reopened the concurrent-regen
  window closed after the 2026-05-03 SessionEnd storm.
* OAuth bootstrap dispatches over an in-process registry with the account id
  passed as a function argument (`wiki auth <service> <account-id>`), replacing
  three `python -c` sites that interpolated operator-typed text into source.

Dispatch model
--------------
`main(argv)` looks up `argv[0]` in the table. A `py` command is run as a child
process (`sys.executable <script> <args…>`) — same isolation the old
`_run_script` bash helper gave, so a heavy script's asyncio loop / SDK state
never leaks into this dispatcher. `bash` commands are never dispatched here
(the bash layer owns them); they live in the table only so `wiki help` and the
menu can see them. `auth` routes to the OAuth registry.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
WIKI_DIR = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))


# ── stdout styling ──────────────────────────────────────────────────────
# `wiki help` + command banners go to stdout, so TTY-detect on stdout (the
# core.console C_* constants gate on stderr and would be wrong here). Non-TTY
# callers (pipes, hooks, desktop capturing stdout) get plain text.
_STDOUT_TTY = sys.stdout.isatty()
_BOLD = "\033[1m" if _STDOUT_TTY else ""
_DIM = "\033[2m" if _STDOUT_TTY else ""
_CYAN = "\033[36m" if _STDOUT_TTY else ""
_RESET = "\033[0m" if _STDOUT_TTY else ""


def _err(msg: str) -> None:
    prefix = "\033[31m✗ \033[0m" if sys.stderr.isatty() else "wiki: "
    print(f"{prefix}{msg}", file=sys.stderr)


def _banner(title: str, subtitle: str | None = None) -> None:
    """Match lib/common.sh:banner — bold title, optional dim subtitle, blank.

    Flush explicitly: when stdout is a pipe (desktop / hooks capture it) Python
    block-buffers, so without a flush the buffered banner would land AFTER the
    child process's output. bash's `printf` was unbuffered — preserve that."""
    print(f"{_BOLD}{title}{_RESET}")
    if subtitle:
        print(f"{_DIM}{subtitle}{_RESET}")
    print()
    sys.stdout.flush()


# ── Command spec ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SubRoute:
    """A first-arg-selected alternate handler for one command.

    `wiki correct apply …` and `wiki backfill picture-metadata …` route to a
    different script than the command's default handler; a SubRoute captures
    that (its `key` is consumed, remaining args pass through)."""

    key: str
    script: str
    banner: str
    subtitle: str | None = None


@dataclass(frozen=True)
class CommandSpec:
    """One `wiki <name>` subcommand.

    kind:
      "py"       dispatched here — run `handler` as a child process.
      "bash"     dispatched by the `wiki` bash layer (bootstrap / genuinely-bash
                 commands); listed here only so help + menu stay complete.
      "auth"     the OAuth registry front-door (`wiki auth <service> <id>`).
    """

    name: str
    group: str
    summary: str
    kind: str = "py"
    handler: str | None = None            # script path relative to scripts/
    banner: bool = True
    banner_subtitle: str | None = None
    refresh_after: bool = False           # refresh dashboards once, locked, after
    needs_vault: bool = True              # informational; the bash guard enforces it
    show_help_on_empty: bool = False      # bare `wiki <name>` prints help
    empty_help_exit: int = 0              # exit code for the bare-help case
    menu: bool = False                    # expected to be reachable from menu.py
    help_text: str | None = None          # rich per-command help (was a bash heredoc)
    subroutes: tuple[SubRoute, ...] = ()


# ── Per-command help (migrated verbatim from the former bash heredocs) ──
# Kept as data so `wiki <cmd> --help` stays as rich as before while the source
# of truth lives in one tested place. Section headers (ALL-CAPS lines) and the
# title line are bolded at render time.

H_COMPILE = """wiki compile — run the compiler against changed (or all) sources

USAGE
  wiki compile                       compile only sources whose hash changed since last run
  wiki compile --all                 force-recompile every source in raw/ + daily/
  wiki compile --file PATH           compile a single file (relative to vault root)
  wiki compile --max-files N         stop after N files (0 = unlimited)

NOTES
  Wraps scripts/compile.py. Runs Claude Agent SDK against your configured compile_model.
  LLM cost applies. Dashboard counts refresh automatically afterwards."""

H_FLUSH = """wiki flush — capture the current Claude Code session context to daily/

USAGE
  wiki flush                         manually trigger a flush (normally automatic via hooks)

NOTES
  Wraps scripts/flush.py. Reads recent session transcript, extracts a
  daily-log entry, appends to daily/YYYY-MM-DD.md. After 18:00 (or
  whatever scheduling.compile_after_hour is set to), triggers compile +
  piggyback tasks. Dashboard counts refresh automatically afterwards."""

H_LINT = """wiki lint — health-check the knowledge base

USAGE
  wiki lint                          full: structural + LLM contradiction check ($ cost)
  wiki lint --structural-only        cheap structural checks only (no LLM)

NOTES
  Wraps scripts/lint.py. Structural checks: broken_links, orphan_pages,
  orphan_sources, stale_articles, missing_backlinks, article_type, sparse_articles.
  Report saved to .wiki/reports/lint-YYYY-MM-DD.md. Dashboard counts refresh."""

H_LINKS = """wiki links — analyze (and optionally fix) broken wikilinks

USAGE
  wiki links                         categorized report (read-only)
  wiki links --fix                   interactively rewrite high-confidence dangling refs
  wiki links --fix --yes             non-interactive: apply bucket-tier corrections only

NOTES
  Wraps scripts/links_audit.py. Three classes: media embeds (asset missing),
  doc placeholders (examples, left alone), and dangling article refs. The fixer
  only rewrites dangling refs with a high-confidence correction — an exact
  basename in a different bucket (near-certain) or a very-close string match.
  Each is approved per-item; --yes auto-applies only the exact-basename tier.
  Missing-article refs are reported but never auto-fixed (create via
  compile/dream, or drop the link)."""

H_RECONCILE = """wiki reconcile — autonomous concept-consistency routine

USAGE
  wiki reconcile                     dry-run plan (default, no writes)
  wiki reconcile --apply             apply (requires features.concept_reconciliation)
  wiki reconcile --limit N           cap facts processed this run

NOTES
  Signal-driven: consumes lint.check_facts_violations and auto-reconciles
  knowledge/concepts/ articles against the hard facts they contradict, via a
  strict scope-locked correct_apply (per-fact + per-run cost caps,
  per-fact cooldown). Concept-concept contradictions + quality are
  PROPOSE-ONLY (left in wiki lint / the dashboard). Default OFF + dry-run;
  flip features.concept_reconciliation to enable --apply.
  Spec: .ytstack/backlog/concept-consistency-routine.md."""

H_HEALTH_TRENDS = """wiki health-trends — deterministic health-trend synthesis

USAGE
  wiki health-trends             regenerate the trends block in concepts/health.md
  wiki health-trends --dry-run   print the block, write nothing

NOTES
  Pure-Python ($0, no LLM): aggregates every numeric metric in
  raw/notes/health/** into monthly stats (range, all-time avg, recent avg,
  trend arrow), coverage-aware, and writes ONE sentinel-managed ## Trends
  block. The synthesis consumer per-day health stubs never had. Gated by
  features.health_trends (off -> dry-run). Spec:
  .ytstack/backlog/health-trend-synthesis.md."""

H_USAGE = """wiki usage — token-usage ledger (tokens per provider/model)

USAGE
  wiki usage                  last 7 days, per provider/model
  wiki usage --days N         last N days (0 = all)
  wiki usage --json           raw state/usage.json

NOTES
  Usage is tracked in TOKENS per (provider, model), never dollars — Claude runs
  on a subscription, Ollama is local. Recorded by every LLM call site into
  state/usage.json (see core/usage.py). Read-only."""

H_QUERY = """wiki query — ask the knowledge base in natural language

USAGE
  wiki query "WHAT did we decide about X?"
  wiki query "..." --brief           5-10 line bullet answer (cheapest mode)
  wiki query "..." --file-back       full answer + persist as knowledge/qa/<slug>.md
  wiki query "..." --file-back --force   overwrite an existing qa/ note

NOTES
  Wraps scripts/query.py. Reads knowledge/index.md, picks the
  relevant articles, answers via the configured query model. LLM cost applies.
  --brief and --file-back are mutually exclusive. --file-back refuses to
  overwrite an existing qa/ slug-match without --force."""

H_AGENT = """wiki agent — run an agentic task

USAGE
  wiki agent <id>                          run task defined in prompts/agents/<id>.md
  wiki agent <id> --dry-run                resolve + print spec without spawning
  wiki agent <id> --var key=value          substitute ${key} in the prompt body
  wiki agent --list                        list registered tasks

EXAMPLES
  wiki agent summarize-day                 # cheap Haiku run on today's daily/
  wiki agent summarize-day --dry-run
  wiki agent --list

NOTES
  Wraps scripts/agent_task.py. Spawns Claude Agent SDK with the model,
  allowed_tools, permission_mode, max_turns, and cwd declared in the task's
  frontmatter. Result text logged to .wiki/logs/agent-<id>-<ts>.log.
  On success the task's frontmatter gets last_run: <iso-ts> written back."""

H_CORRECT = """wiki correct — record hard facts that override LLM-compiled wiki content

USAGE
  wiki correct add "TITLE" "TRUTH"           add a hard fact (default --status=negation)
      [--status negation|disambiguation|clarification]
      [--term "exact substring" ...]         lint will grep these across knowledge/
      [--slug SLUG]                          override auto-derived slug
      [--force]                              overwrite if it already exists
  wiki correct list                          list all hard facts
  wiki correct remove SLUG                   delete a hard fact (.bak.<ts> kept)
  wiki correct edit SLUG                     open in $EDITOR (.bak.<ts> kept first)
  wiki correct apply SLUG [--dry-run]        agentic propagation across vault ($$$ — Claude SDK)
  wiki correct path SLUG                     print absolute path

EXAMPLES
  wiki correct add "Senkrechtstarter award (NOT won)" \\
      "We did NOT win the Senkrechtstarter award. Strike any article asserting otherwise." \\
      --status negation \\
      --term "senkrechtstarter award" --term "won the senkrechtstarter"

  wiki correct add "Township project = Fleet" \\
      "The active 'township' project is named Fleet. There is also an older project under the township-* namespace — never conflate them." \\
      --status disambiguation

NOTES
  Wraps scripts/facts/correct.py. Facts live in knowledge/facts/<slug>.md with
  type: fact frontmatter. Compile + query inject them as a Hard-facts block at
  highest authority. Lint surfaces violations of any negation_terms."""

H_DEDUP = """wiki dedup — find + merge transcription-noise duplicate entity pages

USAGE
  wiki dedup                         detect candidates, walk them interactively
  wiki dedup --suggest-only          print the candidate list, no merge loop
  wiki dedup --dry-run               walk + merge without writing anything
  wiki dedup --threshold 0.9         override fuzzy match floor (0..1)
  wiki dedup merge B --into A        standalone merge of a known pair
  wiki dedup merge B --into A --name "Correct Name"

WHAT IT DOES
  Wraps scripts/dedup.py. STT transcribers (Jamie, voice) garble names
  consistently — sephora-tunsch vs sefora-tunc, maytoni vs phantom
  mytony — splitting one entity across two pages. Detection is $0 +
  deterministic (difflib fuzzy + German-aware phonetic key + shared
  compiled_from). Every merge is operator-confirmed (never automatic):
  B's Timeline / Action Items / Open Threads + aliases + sources fold into A,
  every [[wikilink]] B->A is rewritten across knowledge/, B is backed up
  (.bak.<ts>) + deleted, and a canonical-name hard fact is recorded so
  lint flags any reappearance.

NOTES
  Operates on knowledge/{people,projects,areas}/. Cross-kind pairs are never
  proposed. Fuzzy floor: limits.dedup_fuzzy_threshold (default 0.85);
  phonetic + shared-source matches are proposed regardless. Spec:
  .ytstack/backlog/entity-dedup.md."""

H_TAKE = """wiki take — record third-party belief attribution (M011)

USAGE
  wiki take add "HOLDER" "BELIEF" --source PATH \\
      [--confidence low|medium|high] [--date YYYY-MM-DD] [--slug SLUG]
                                              append a take to knowledge/takes/<slug>.md
  wiki take list                              list all takes files
  wiki take show SLUG                         list every take recorded for one holder
  wiki take remove SLUG --line N              remove one line (1-based; use show first)
  wiki take remove SLUG --all                 delete the whole file (.bak.<ts> kept)
  wiki take path SLUG                         print absolute path

EXAMPLES
  wiki take add "Jane Doe" \\
      "GPT-5 commoditizes agent platforms within 12 months." \\
      --confidence high \\
      --source "raw/transcripts/jamie/2026-04-15--review--abc.md"

NOTES
  Wraps scripts/facts/take.py. Takes live in knowledge/takes/<slug>.md,
  one file per holder, append-only one-per-line. Operator's OWN positions
  still go through wiki correct into knowledge/facts/; wiki take
  is reserved for OTHER people's beliefs. Compile reads takes when
  distilling a type: person page; facts override, takes inform."""

H_PIN = """wiki pin — pin an article into a Map-of-Content (MOC)

USAGE
  wiki pin <article>                              interactive section picker
  wiki pin <article> --section "Active"           skip prompt, choose section
  wiki pin <article> --moc people                 override target MOC
  wiki pin <article> --summary "one-line note"    override annotation

NOTES
  <article> accepts a bare basename (alex), a vault-relative path
  (knowledge/people/alex.md), or an absolute path.

  Target MOC is auto-derived from the article's type: frontmatter:
    concept->concepts · connection->connections · person->people
    project->projects · qa->qa

  Idempotent: re-running on a file already pinned anywhere in the MOC is
  a no-op. New section names create a new H2 above the dataview block."""

H_REVIEW_WIKI = """wiki review-wiki — per-article quality scores via local LLM

USAGE
  wiki review-wiki                   sweep every article, score each one

NOTES
  Wraps scripts/review-wiki.py. Uses the local Ollama model — $0 cost.
  Output goes to .wiki/reports/review-YYYY-MM-DD.md. Runs as weekly piggyback
  by default; this command is for ad-hoc manual runs."""

H_PROCESS_INBOX = """wiki process-inbox — classify files dropped into <vault>/inbox/

USAGE
  wiki process-inbox                       classify + move, then compile
  wiki process-inbox --no-compile          classify + move only (no compile)
  wiki process-inbox --dry-run             show what would be moved without writing
  wiki process-inbox --model MODEL         override classifier model (default gemma3:4b)

WHAT IT DOES
  Walks <vault>/inbox/. For each file, calls a local Ollama model to
  classify it (article / paper / note / transcript / audio / memory / suggestion)
  and moves it into the matching raw/<type>/ subfolder. HTML files are
  delegated to scripts/ingest-html.py (text + visual). After the sweep,
  triggers wiki compile on the freshly-routed sources.

NOTES
  Wraps scripts/process-inbox.py. Free — uses local Ollama, no Claude API
  calls until the downstream compile step. Inbox is transient: the LLM owns
  classification, the operator just drops files. See PROCESS §1."""

H_INGEST_HTML = """wiki ingest-html — convert an HTML file or URL into raw/

USAGE
  wiki ingest-html PATH-OR-URL [flags]

FLAGS
  --mode {content,visual,both}    extraction mode (default content)
                                    content  html2text -> raw/articles/<slug>.md
                                    visual   Playwright screenshot -> Vision LLM -> raw/notes/
                                    both     run both pipelines back-to-back
  --dry-run                       show what would be written, don't touch disk

NOTES
  Wraps scripts/ingest-html.py. Visual mode needs Playwright + a local
  Vision-capable Ollama model; content mode runs offline. Also auto-invoked
  by wiki process-inbox for any .html files in the inbox."""

H_INGEST_YOUTUBE = """wiki ingest-youtube — pull YouTube videos into raw/notes/youtube/

USAGE
  wiki ingest-youtube --url URL [flags]              one video or one playlist
  wiki ingest-youtube --inbox PATH [flags]           a markdown file with URLs

FLAGS
  --tier {0,1,2,3}    ingest depth (default 1)
                        0  metadata only (yt-dlp)
                        1  + transcript (youtube-transcript-api / yt-dlp fallback)
                        2  + top comments (yt-dlp)
                        3  + visual analysis (gemma4:e4b @ kcma, ffmpeg frames, free)
  --limit N           cap playlist expansion / inbox-list to first N videos
  --dry-run           describe what would be written, don't touch disk
  --no-skip           re-ingest videos that already exist in raw/notes/youtube/

EXAMPLES
  wiki ingest-youtube --url "https://youtu.be/dQw4w9WgXcQ"
  wiki ingest-youtube --url "https://www.youtube.com/playlist?list=PLxxx" --tier 2 --limit 10
  wiki ingest-youtube --inbox raw/inbox/youtube.md --tier 1

NOTES
  Wraps scripts/collectors/scan_youtube.py. T0–T2 are free (no LLM). T3 (visual
  via gemma4@kcma or Gemini 2.5) is on the backlog — see
  .ytstack/backlog/youtube-intake.md."""

H_CURIOSITY = """wiki curiosity — review + run curiosity-loop deep-scan requests

USAGE
  wiki curiosity                                 interactive walk: accept/skip/reject each pending (default)
  wiki curiosity --list                          list all pending + done requests
  wiki curiosity --run-oldest                    run the oldest pending request (non-interactive)
  wiki curiosity --run <slug>                    run one request by slug substring
  wiki curiosity --run-all                       run every pending request
  wiki curiosity --dry-run                       walk without touching mailbox
  wiki curiosity --clear-done                    delete request files with status: done

WALK ACTIONS
  [a]ccept   dispatch the request (pull email bodies, write deep-scan)
  [A]ccept ALL  dispatch this + every remaining pending in one action
              (folder-deep-scans first list the files sent to the cloud
              provider + ask one bulk confirmation). Non-interactive
              equivalent: wiki curiosity --run-all.
  [s]kip     leave as pending — comes back next walk
  [r]eject   persist status=rejected; producer skips this slug forever
  [q]uit     end the walk

WHAT IT DOES
  After each compile, compile.py writes JSON gap-requests into
  raw/requests/ (curiosity producer). This command is the consumer:
  reads one request, resolves the account's MailboxReader, calls scan_deep
  to pull full message bodies, renders one markdown report into
  raw/notes/email/deep-<slug>.md. The next compile distills it.

BACKENDS
  email-deep-scan -> scripts/curiosity/backends/email.py (Thunderbird mbox,
  Gmail API, All-Inkl IMAP via the existing Mailbox adapters).

NOTES
  Wraps scripts/curiosity/cli.py. See PROCESS §7."""

H_SUGGESTIONS = """wiki suggestions — review + execute optimization suggestions

USAGE
  wiki suggestions --list                          list all suggestion files + action statuses
  wiki suggestions --review <suggestion-id>        interactive review of one suggestion
  wiki suggestions --approve <suggestion-id> N     approve action #N
  wiki suggestions --reject <suggestion-id> N      reject action #N
  wiki suggestions --dry-run                       preview approved actions
  wiki suggestions                                 execute approved actions

WHAT IT DOES
  The compiler emits YAML proposals into raw/suggestions/ after each
  email-source compile (filter rules, mail moves, tag applications). This
  command is the per-action approval + execution surface.

BACKENDS
  IMAP move/tag/set-flags actions dispatch to suggestions/backends/imap.py.
  Account credentials come from <vault>/.claude/.env per
  personal.accounts.<id>.reader.imap_user_env / imap_pass_env.

NOTES
  Wraps scripts/suggestions/cli.py. See PROCESS §8."""

H_COLLECT = """wiki collect — run a Collector (substrate-shaped raw/ writer)

USAGE
  wiki collect --list                  list registered Collectors
  wiki collect <name> [flags]          run one Collector

FLAGS
  --dry-run                            log what would happen, don't write to disk
  --incremental                        only scan deltas (when supported)
  --account ID                         restrict to one account (substrates with accounts)

EXAMPLES
  wiki collect --list                  show all registered collectors with their SPEC
  wiki collect email                   full email scan across all configured accounts
  wiki collect email --account work    one account only
  wiki collect email --dry-run         no-op preview"""

H_INDEX = """wiki index — body-blind folder-index digests for watched local roots

USAGE
  wiki index                 sync every kind=local personal.watched_folders entry
  wiki index <root-id>       sync exactly one entry
  wiki index --force         re-write digests even when the tree is unchanged

WHAT IT DOES
  Walks each watched root WITHOUT reading any file body (scandir + stat
  only) and writes one markdown digest per root to raw/index/<root-id>.md:
  the COMPLETE tree + top-N recent changes, names unmasked. The curiosity
  producer reads these digests to propose folder-deep-scans (trimming or
  grepping as needed — the digest itself is never truncated); content is
  only ever loaded after per-request operator approval in the walk.
  Unchanged trees are delta-skipped via state/folder-index.json. Digests
  carry type: folder-index and are compile-skipped (nothing to distil).

  Knobs: limits.folder_index_max_depth (0 = unlimited; raise only as a
  walk-cost bound for huge NAS roots) / folder_index_recent_n.
  kind=smb (NAS) entries are skipped — NAS indexing lands in S06."""

H_PRODUCE = """wiki produce — run a Producer (post-compile derivative-material extractor)

USAGE
  wiki produce --list                  list registered Producers
  wiki produce <name> <source>         run one Producer on one source

WHAT IS A PRODUCER?
  Producers consume a compiled source file under raw/ and emit derived
  material (suggestion notes, knowledge-gap requests, third-party belief
  extractions). Mirrors Collectors but for the post-compile side.
  Production driver: compile.py's per-file loop. This CLI is for manual
  re-run / debug / replay.

EXAMPLES
  wiki produce --list                                       show all registered producers with gates
  wiki produce takes raw/transcripts/2026-05-17-meeting.md  re-run takes for one source
  wiki produce curiosity raw/email/inbox-2026-05-17.md      manual curiosity pass"""

H_PREPROCESS = """wiki preprocess — run a Preprocessor (in-vault intake normalizer)

USAGE
  wiki preprocess --list                    list registered Preprocessors
  wiki preprocess <name> [source]           run one Preprocessor
  wiki preprocess <name> --dry-run          preview without writing

WHAT IS A PREPROCESSOR?
  Preprocessors normalize material already INSIDE the vault (the inbox/
  drop-zone, the Obsidian Web Clipper Clippings/ folder, a single HTML
  file or URL) into the raw/** shape the compile loop reads. They run
  BEFORE compile; Producers run after it. Unlike a Collector they never
  read an outside substrate — singletons, no accounts.

  Today: inbox, html, clippings. `source` (path or URL) is required for
  preprocessors that take one (html); the folder-sweep singletons
  (inbox, clippings) ignore it. `wiki process-inbox` and
  `wiki ingest-html` remain as direct entry-points to the same logic.

EXAMPLES
  wiki preprocess --list                       show all registered preprocessors
  wiki preprocess clippings --dry-run          preview the Clippings/ sweep
  wiki preprocess html https://example.com/a   ingest one page into raw/articles"""

H_TRIAGE = """wiki triage — review + clear the intent inbox (workspace/inbox/)

USAGE
  wiki triage                 list pending records, grouped by type
  wiki triage --all           list every record (incl. done/dismissed)
  wiki triage done <stem>     mark a record status: done
  wiki triage dismiss <stem>  mark a record status: dismissed

Detected intents (task/idea/note) land in workspace/inbox/ with status: pending.
Keep one (promote task->run, idea/note->knowledge) then done, or dismiss noise.
<stem> matches the record filename; a unique prefix is enough."""

H_BRIDGE = """wiki bridge — rsync-based mirror for sandbox-restricted intake folders

USAGE
  wiki bridge list                    show configured mappings
  wiki bridge sync                    mirror every mapping
  wiki bridge sync --dry-run          show what rsync would do

WHY
  macOS TCC blocks Claude-Code-spawned subprocesses from reading
  ~/Library/CloudStorage/… (Google Drive, iCloud Drive). The bridge
  runs as the user (manually or via LaunchAgent) — TCC is satisfied —
  and pre-mirrors a Drive folder into a local path the substrate
  collectors can then folder-watch freely.

CONFIG
  Edit <vault>/.wiki/config.yaml:

    personal:
      inbox_bridges:
        - name:   screenshots-tablet
          remote: "/Users/<you>/Library/CloudStorage/GoogleDrive-<addr>/My Drive/wiki-inbox/pictures/screenshots-tablet"
          local:  "~/wiki-inbox-local/screenshots-tablet"
          mode:   move    # move (default, drains remote) or copy

  Then point the matching substrate (e.g. personal.picture_inbox)
  at the local mirror path. The bridge is substrate-agnostic — operator
  wires routing per mapping.

AUTOMATION
  See templates/.launchd/com.llm-wiki.bridge.plist.template for a
  LaunchAgent that runs wiki bridge sync on a schedule."""

H_BACKFILL = """wiki backfill — one-shot data-shape upgrades on existing vault artifacts

USAGE
  wiki backfill picture-metadata [--dry-run]   add EXIF + Android filename
                                               metadata to existing pictures
                                               archive sidecars
  wiki backfill voice-source-frontmatter [--dry-run]
                                               move legacy in-body voice
                                               source wikilinks into the
                                               daily voice.md sources: frontmatter
  wiki backfill tasks-to-workspace [--dry-run] move legacy tasks/ intent queue
                                               into workspace/inbox/

WHAT IT DOES
  Each subcommand walks the relevant substrate and adds net-new keys to
  existing artifacts that were written before a feature shipped. Idempotent:
  re-runs only write keys that aren't already present, and existing
  operator-added keys are never overwritten."""

H_STUDY = """wiki study — operator-self-reports surface (M019)

USAGE
  wiki study list                           list all studies + run status
  wiki study run <id>                       run a study (all instruments)
  wiki study run <id> --instrument SLUG     limit to one instrument
  wiki study new <id>                       create a stub study (manual schedule, 1 instrument)
  wiki study new <id> --fork-from OTHER     clone an existing study
  wiki study diff <run_a> <run_b>           compare two runs (S04 stub for now)

NOTES
  Studies live at <vault>/<personal.reports_dir>/studies/<id>/.
  Each run produces a timestamped dir with per-instrument reports.
  Air-gapped from the compile loop — reports never feed back into knowledge/."""

H_ANALYZE = """wiki analyze — operator-self-reports analyst layer (M019-S05)

USAGE
  wiki analyze                          Pass-1 over all studies, then Pass-2
  wiki analyze --study <id>             Pass-1 on one study's latest run
  wiki analyze --cross-study-only       Pass-2 cross-study synthesis only
  wiki analyze --no-pass2               Pass-1 only, skip cross-study
  wiki analyze --rerun                  Overwrite existing _analysis.md files

NOTES
  Two-pass design: Pass-1 reads each study's results + substrate, writes
  per-study _analysis.md. Pass-2 reads all Pass-1 outputs, writes
  reports/analyses/<ts>.md (cross-study synthesis). Air-gapped from
  compile-loop; analyst-agent has Read/Glob/Grep only, no Write/Edit/Bash."""

H_AUTH = """wiki auth — one-time OAuth bootstrap for a Google service account

USAGE
  wiki auth gmail <account-id>       Gmail API access (mail collector)
  wiki auth gmeet <account-id>       Google Meet transcripts (Drive export)
  wiki auth calendar <account-id>    Google Calendar events

  Legacy aliases (unchanged): wiki gmail-auth / gmeet-auth / calendar-auth <id>

WHAT IT DOES
  Reads the installed-app OAuth client JSON you provide under .claude/
  (per-account override, then a shared google-oauth-client.json, then the
  legacy gmail-oauth-client.json), opens a local-loopback browser for the
  consent screen, and persists the token under .wiki/state/. Re-running
  re-issues consent. <account-id> matches a key under personal.accounts.<id>.

EXAMPLES
  wiki auth gmail private            # consent flow for accounts.private
  wiki auth gmeet work               # Meet Recordings on accounts.work
  wiki auth calendar private"""

# ── The catalog ─────────────────────────────────────────────────────────
# Order within a group is the render order in `wiki help`.

COMMANDS: tuple[CommandSpec, ...] = (
    # Home & status
    CommandSpec("menu", "Home & status", "interactive home screen (--json for agents)",
                kind="bash", needs_vault=False),
    CommandSpec("status", "Home & status", "config + hooks + Ollama summary",
                kind="bash", menu=True),
    CommandSpec("doctor", "Home & status", "vault-health audit (--quick / --json)",
                kind="bash"),
    CommandSpec("version", "Home & status", "print installed git revision",
                kind="bash", needs_vault=False, menu=True),
    # Setup
    CommandSpec("setup", "Setup", "first-time setup (config wizard + hooks)",
                kind="bash", menu=True),
    CommandSpec("config", "Setup", "interactive config editor (get/set/keys/…)",
                kind="bash", menu=True),
    CommandSpec("hooks", "Setup", "install/uninstall session hooks per agent",
                kind="bash", menu=True),
    CommandSpec("skills", "Setup", "wire engine skills into .claude/skills/",
                kind="bash", menu=True),
    CommandSpec("install-shortcut", "Setup", "symlink ~/.local/bin/wiki -> this vault",
                kind="bash", needs_vault=False),
    CommandSpec("update", "Setup", "git pull --ff-only + sync deps/skills",
                kind="bash", menu=True),
    CommandSpec("seed", "Setup", "re-apply engine templates to the vault",
                kind="bash", menu=True),
    # Collect & ingest
    CommandSpec("collect", "Collect & ingest", "run a Collector (--list to enumerate)",
                handler="collectors/cli.py", banner=False, menu=True, help_text=H_COLLECT),
    CommandSpec("index", "Collect & ingest", "body-blind folder-index digests",
                handler="collectors/folder_index.py", help_text=H_INDEX),
    CommandSpec("produce", "Collect & ingest", "run a Producer (post-compile extractor)",
                handler="producers/cli.py", banner=False, menu=True, help_text=H_PRODUCE),
    CommandSpec("preprocess", "Collect & ingest", "run a Preprocessor (--list to enumerate)",
                handler="preprocessors/cli.py", banner=False, menu=True, help_text=H_PREPROCESS),
    CommandSpec("process-inbox", "Collect & ingest", "classify inbox/ files via Ollama",
                handler="process-inbox.py", menu=True, help_text=H_PROCESS_INBOX),
    CommandSpec("ingest-html", "Collect & ingest", "convert an HTML file or URL into raw/",
                handler="ingest-html.py", menu=True, help_text=H_INGEST_HTML),
    CommandSpec("ingest-youtube", "Collect & ingest", "pull YouTube videos into raw/notes/",
                handler="collectors/scan_youtube.py", menu=True, help_text=H_INGEST_YOUTUBE),
    CommandSpec("bridge", "Collect & ingest", "rsync mirror for sandbox-restricted folders",
                handler="bridge/cli.py", banner=False, menu=True, help_text=H_BRIDGE),
    CommandSpec("backfill", "Collect & ingest", "one-shot data-shape upgrades",
                handler=None, banner=False, show_help_on_empty=True, menu=True,
                help_text=H_BACKFILL,
                subroutes=(
                    SubRoute("picture-metadata", "backfill_picture_metadata.py",
                             "wiki backfill picture-metadata"),
                    SubRoute("voice-source-frontmatter", "backfill_voice_source_frontmatter.py",
                             "wiki backfill voice-source-frontmatter"),
                    SubRoute("tasks-to-workspace", "backfill_tasks_to_workspace.py",
                             "wiki backfill tasks-to-workspace"),
                )),
    CommandSpec("auth", "Collect & ingest", "OAuth bootstrap (gmail/gmeet/calendar)",
                kind="auth", help_text=H_AUTH),
    CommandSpec("gmail-auth", "Collect & ingest", "alias: wiki auth gmail <account-id>",
                kind="bash", menu=True),
    CommandSpec("gmeet-auth", "Collect & ingest", "alias: wiki auth gmeet <account-id>",
                kind="bash", menu=True),
    CommandSpec("calendar-auth", "Collect & ingest", "alias: wiki auth calendar <account-id>",
                kind="bash", menu=True),
    # Knowledge ops
    CommandSpec("compile", "Knowledge ops", "compile changed (or all) sources into knowledge/",
                handler="compile.py", refresh_after=True, menu=True, help_text=H_COMPILE),
    CommandSpec("dream", "Knowledge ops", "sweep all entity pages (oldest-overdue first)",
                kind="bash", menu=True),
    CommandSpec("dream-entity", "Knowledge ops", "re-synthesize ONE entity page by slug",
                kind="bash", menu=True),
    CommandSpec("query", "Knowledge ops", "ask the knowledge base in natural language",
                handler="query.py", show_help_on_empty=True, menu=True, help_text=H_QUERY),
    CommandSpec("lint", "Knowledge ops", "structural + LLM contradiction health check",
                handler="lint.py", refresh_after=True, menu=True, help_text=H_LINT),
    CommandSpec("links", "Knowledge ops", "broken-wikilink report (--fix to rewrite)",
                handler="links_audit.py", help_text=H_LINKS),
    CommandSpec("pin", "Knowledge ops", "pin an article into a Map-of-Content",
                handler="pin.py", banner=False, menu=True, help_text=H_PIN),
    CommandSpec("review-wiki", "Knowledge ops", "per-article quality scores (local LLM, free)",
                handler="review-wiki.py", menu=True, help_text=H_REVIEW_WIKI),
    CommandSpec("health-trends", "Knowledge ops", "deterministic health-trend synthesis ($0)",
                handler="health_trends.py", menu=True, help_text=H_HEALTH_TRENDS),
    CommandSpec("agent", "Knowledge ops", "run an agentic task (prompts/agents/<id>.md)",
                handler="agent_task.py", menu=True, help_text=H_AGENT),
    # Facts & takes
    CommandSpec("correct", "Facts & takes", "record hard facts that override compiled content",
                handler="facts/correct.py", refresh_after=True, show_help_on_empty=True,
                empty_help_exit=1, menu=True, help_text=H_CORRECT,
                subroutes=(
                    SubRoute("apply", "facts/correct_apply.py", "wiki correct apply",
                             "Agentic propagation — Claude Agent SDK over vault root."),
                )),
    CommandSpec("take", "Facts & takes", "record third-party belief attribution (M011)",
                handler="facts/take.py", refresh_after=True, show_help_on_empty=True,
                empty_help_exit=1, menu=True, help_text=H_TAKE),
    CommandSpec("dedup", "Facts & takes", "find + merge STT-noise duplicate entity pages",
                handler="dedup.py", refresh_after=True, menu=True, help_text=H_DEDUP),
    # Review & maintenance
    CommandSpec("flush", "Review & maintenance", "capture current session context to daily/",
                handler="flush.py", menu=True, help_text=H_FLUSH),
    CommandSpec("curiosity", "Review & maintenance", "review + run curiosity deep-scan requests",
                handler="curiosity/cli.py", menu=True, help_text=H_CURIOSITY),
    CommandSpec("suggestions", "Review & maintenance", "review + execute optimization suggestions",
                handler="suggestions/cli.py", menu=True, help_text=H_SUGGESTIONS),
    CommandSpec("reconcile", "Review & maintenance", "autonomous concept-consistency routine",
                handler="reconcile.py", menu=True, help_text=H_RECONCILE),
    CommandSpec("triage", "Review & maintenance", "review + clear the intent inbox",
                handler="triage.py", banner=False, menu=True, help_text=H_TRIAGE),
    CommandSpec("study", "Review & maintenance", "operator-self-reports surface (M019)",
                handler="study.py", menu=True, help_text=H_STUDY),
    CommandSpec("analyze", "Review & maintenance", "operator-self-reports analyst layer",
                handler="analyze.py", menu=True, help_text=H_ANALYZE),
    CommandSpec("usage", "Review & maintenance", "token-usage ledger (per provider/model)",
                handler="usage_report.py", menu=True, help_text=H_USAGE),
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


def run_auth(rest: list[str]) -> int:
    """Dispatch `wiki auth <service> <account-id>` over AUTH_SERVICES."""
    if not rest or rest[0] in ("-h", "--help", "help"):
        _print_help_text(BY_NAME["auth"])
        return 0
    service = rest[0]
    if service not in AUTH_SERVICES:
        _err(f"unknown auth service: {service} "
             f"(expected: {', '.join(AUTH_SERVICES)})")
        return 1
    # `wiki auth gmail` (no id) / `wiki gmail-auth` alias with no id -> service help.
    if len(rest) < 2 or rest[1] in ("-h", "--help", "help"):
        _print_help_text(BY_NAME["auth"])
        return 0
    account_id = rest[1]
    module_name, func_name = AUTH_SERVICES[service]
    module = importlib.import_module(module_name)
    bootstrap = getattr(module, func_name)
    ok, message = bootstrap(account_id)
    print(message)
    return 0 if ok else 1


# ── Dashboard refresh ───────────────────────────────────────────────────


def refresh_dashboards() -> None:
    """Refresh the vault Dashboard caches ONCE, via flush.py's existing
    fcntl-locked + timeout-guarded implementation.

    Importing flush is the sanctioned path (the lock was built there after the
    2026-05-03 SessionEnd storm and must not be duplicated). The import is
    lazy so commands that don't refresh — and `wiki help` — never pay for it.
    """
    import flush  # noqa: PLC0415 — lazy: only the refresh_after path needs it

    flush.refresh_dashboard_stats()
    flush.refresh_dashboard_lint()


# ── Help rendering ──────────────────────────────────────────────────────


def _style_help(text: str) -> str:
    """Bold the title line + ALL-CAPS section headers (parity with the old
    bash heredoc styling) when stdout is a TTY; otherwise return plain text."""
    if not _STDOUT_TTY:
        return text
    out: list[str] = []
    for i, line in enumerate(text.splitlines()):
        stripped = line.strip()
        is_header = stripped and stripped == stripped.upper() and any(
            ch.isalpha() for ch in stripped
        ) and all(ch.isupper() or not ch.isalpha() for ch in stripped)
        if i == 0 or is_header:
            out.append(f"{_BOLD}{line}{_RESET}")
        else:
            out.append(line)
    return "\n".join(out)


def _print_help_text(command: CommandSpec) -> None:
    if command.help_text:
        print(_style_help(command.help_text))
    else:
        print(f"{_BOLD}wiki {command.name}{_RESET} — {command.summary}")


def render_help() -> str:
    """The full `wiki help` catalog, grouped, every command visible."""
    width = max(len(c.name) for c in COMMANDS) + 2
    lines: list[str] = [
        f"{_BOLD}{_CYAN}wiki{_RESET} — personal knowledge-base engine",
        "",
        f"{_DIM}usage: wiki <command> [args]   ·   wiki <command> --help for details{_RESET}",
        "",
    ]
    for group in _GROUP_ORDER:
        members = [c for c in COMMANDS if c.group == group]
        if not members:
            continue
        lines.append(f"{_BOLD}{group}{_RESET}")
        for c in members:
            lines.append(f"  {_CYAN}{c.name:<{width}}{_RESET}{c.summary}")
        lines.append("")
    lines.append(f"{_BOLD}DOCS{_RESET}")
    lines.append(f"  {WIKI_DIR / 'README.md'}")
    return "\n".join(lines)


# ── Command dispatch ────────────────────────────────────────────────────


def _run_child(script_rel: str, args: list[str]) -> int:
    """Run one handler script as a child process (same isolation `_run_script`
    gave). Returns the child's exit code."""
    script = SCRIPTS_DIR / script_rel
    completed = subprocess.run([sys.executable, str(script), *args], check=False)
    return completed.returncode


def run_command(command: CommandSpec, rest: list[str]) -> int:
    """Dispatch a `py` command: help-intercept, banner, run, refresh-after."""
    # Top-level per-command help (deeper `wiki x sub -h` falls through to the
    # script's own argparse).
    if rest and rest[0] in ("-h", "--help", "help"):
        _print_help_text(command)
        return 0
    if not rest and command.show_help_on_empty:
        _print_help_text(command)
        return command.empty_help_exit

    script = command.handler
    banner_title = f"wiki {command.name}"
    subtitle = command.banner_subtitle
    banner_on = command.banner
    args = rest

    if rest:
        sub = next((s for s in command.subroutes if s.key == rest[0]), None)
        if sub is not None:
            script = sub.script
            banner_title = sub.banner
            subtitle = sub.subtitle
            banner_on = True
            args = rest[1:]

    if script is None:
        # A command with no default handler (backfill) and no matching subroute.
        if not rest:
            _print_help_text(command)
            return 0
        _err(f"unknown: wiki {command.name} {rest[0]} "
             f"(try 'wiki {command.name} help')")
        return 1

    if banner_on:
        _banner(banner_title, subtitle)
    code = _run_child(script, args)
    if command.refresh_after:
        refresh_dashboards()
    return code


def main(argv: list[str]) -> int:
    if not argv:
        print(render_help())
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd in ("help", "-h", "--help"):
        print(render_help())
        return 0
    if cmd == "refresh-dashboards":
        refresh_dashboards()
        return 0
    if cmd == "auth":
        return run_auth(rest)
    command = BY_NAME.get(cmd)
    if command is None or command.kind != "py":
        _err(f"unknown command: {cmd} (try 'wiki help')")
        return 1
    return run_command(command, rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
