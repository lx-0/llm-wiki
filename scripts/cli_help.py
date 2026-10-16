"""Per-command help for the `wiki` CLI — `wiki <cmd> --help` (migrated verbatim from the
former bash heredocs).

Kept as data so `wiki <cmd> --help` stays as rich as before while the source of truth
lives in one tested place. The catalogue (`cli_catalog.COMMANDS`) points each command at
its text, and every help text is printed through `print_help`, by the dispatcher and by a
handler alike (M034-S05-T04; `tests/test_cli.py` refuses a plain print of an H_ text).
"""

from __future__ import annotations

import sys


def _is_header(line: str) -> bool:
    stripped = line.strip()
    return (
        bool(stripped)
        and stripped == stripped.upper()
        and any(ch.isalpha() for ch in stripped)
        and all(ch.isupper() or not ch.isalpha() for ch in stripped)
    )


def print_help(text: str) -> None:
    """One help text: the title line and the ALL-CAPS section headers bold when stdout is a
    terminal (the old bash heredocs' styling), plain text otherwise."""
    if not sys.stdout.isatty():
        print(text)
        return
    print(
        "\n".join(
            f"\033[1m{line}\033[0m" if i == 0 or _is_header(line) else line
            for i, line in enumerate(text.splitlines())
        )
    )


H_COMPILE = """wiki compile — run the compiler against changed (or all) sources

USAGE
  wiki compile                       compile only sources whose hash changed since last run
  wiki compile --all                 force-recompile every source in raw/ + daily/
  wiki compile --file PATH           compile a single file (relative to vault root)
  wiki compile --max-files N         stop after N files (0 = unlimited)

NOTES
  Wraps scripts/compile.py. Runs Claude Agent SDK against your configured compile_model.
  LLM cost applies. Dashboard counts refresh automatically afterwards."""

H_FLUSH = """wiki flush — extract a daily entry from a disposable context file

USAGE
  wiki flush <context_file.md> <session_id>

INPUT
  Write a temporary UTF-8 Markdown file containing the conversation context:
  relevant user requests, decisions, outcomes and unresolved work. Hooks normally
  prepare it automatically; manual callers must supply it. Use a unique session_id
  for a new capture; repeated IDs are subject to the session dedup window.

CONSUMED FILE
  The input is deleted after success, on duplicate-skip and when empty.
  Failed extraction moves it into .wiki/sessions/failed-flushes/ for retry.
  Pass only a disposable copy, never an original project or vault file.

NOTES
  Extraction uses the Claude Agent SDK: LLM cost applies. The result is written
  to daily/YYYY-MM-DD/sessions.md. After scheduling.compile_after_hour, a flush
  can also trigger compilation (additional LLM cost) and due piggyback tasks.
  Dashboard counts refresh automatically afterwards."""

H_LINT = """wiki lint — health-check the knowledge base

USAGE
  wiki lint                          full: structural + LLM contradiction check ($ cost)
  wiki lint --structural-only        cheap structural checks only (no LLM)

NOTES
  Wraps scripts/lint.py. Structural checks: broken_links, orphan_pages,
  orphan_sources, stale_articles, article_type, sparse_articles, and more —
  all run over one shared corpus context (LintContext).
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

H_PUBLISH = """wiki publish — mirror the vault's markdown into meinkontext (producer contract)

USAGE
  wiki publish --auth                one-time connect: browser login + consent
                                     (tokens → .wiki/state/meinkontext-oauth.json)
  wiki publish --dry-run             print the publish plan (create/update/retract)
  wiki publish --dry-run --json      machine-readable plan (GUI/agent seam)
  wiki publish                       execute the plan (idempotent by content hash)
  wiki publish --piggyback           cadence mode; quiet no-op while publish.enabled is false

SETUP
  1. wiki config set publish.enabled true
  2. wiki config set publish.endpoint https://<your-context-mcp>/mcp
  3. wiki publish --auth    (needs a meinkontext USER login — org api-keys are read-only)
  Full runbook: docs/setup-publish.md

NOTES
  One-way mirror of every markdown file under `publish.roots` (engine
  default: knowledge/; add raw/, daily/, reports/, workspace/ to publish the
  substrate too) into ONE managed wiki on the operator's meinkontext server
  (context-mcp; binding contract: docs/PRODUCER-CONTRACT.md in that repo).
  Unchanged articles are never re-sent; local deletes archive upstream.
"""

H_REINDEX = """wiki reindex — reconcile knowledge/index.md against the corpus

USAGE
  wiki reindex                       apply (dedupe, drop dangling, append missing)
  wiki reindex --dry-run             report what would change without writing

NOTES
  Deterministic engine bookkeeping (M031): duplicate rows → last occurrence
  wins; rows for deleted articles are dropped; articles without a row are
  appended with a first-paragraph summary. The same pass runs automatically
  after every compile — this command is the manual/catch-up trigger.
"""

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
  Wraps scripts/review_wiki.py. Uses the local Ollama model — $0 cost.
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
  ingested in-process by preprocessors/html_ingest.py (text + visual). After
  the sweep, triggers wiki compile on the freshly-routed sources.

NOTES
  Entry module scripts/process_inbox.py (logic: preprocessors/inbox.py). Free —
  uses local Ollama, no Claude API
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
  --model MODEL                   Vision model for visual mode (default from config)
  --no-compile                    write raw/ files, skip the compile that follows

NOTES
  Entry module scripts/ingest_html.py (logic: preprocessors/html_ingest.py).
  Visual mode needs Playwright + a local
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

# Home & status — moved from the bash heredocs with the commands (M034-S01-T05); the
# bash oracle's `menu-help` / `doctor-help` goldens hold them to the bash text.
H_MENU = """wiki menu — interactive home screen + agent-facing JSON

USAGE
  wiki menu                interactive home screen (prompt_toolkit-driven)
  wiki menu --json         emit suggestions + status JSON, exit
                           (consumed by use-llm-wiki skill)"""

H_DOCTOR = """wiki doctor — vault-health audit

USAGE
  wiki doctor              full pretty report (config / connectivity / pipeline)
  wiki doctor --json       machine-readable (for agents)
  wiki doctor --quick      skip TCP + subprocess probes (~50ms; for hooks)
  wiki doctor --quick --json   both

EXIT CODE
  0   no critical issues
  1   at least one critical issue

CHECKS
  Config + setup: setup-wizard-ran, hooks-installed, template-drift, engine-update-available
  Connectivity: ollama-reachable, claude-authed
  Pipeline: compile-errors-recent, no-knowledge-articles, compile-state"""

H_VERSION = """wiki version — print the installed engine's git revision

USAGE
  wiki version             revision, tag (when one names the commit) and origin

NOTES
  Reads the engine checkout under .wiki/; outside a git checkout it says so.
  Works without a vault."""

# dream routing — moved from the bash heredocs with the routing (M034-S01-T06); the bash
# oracle's `dream-help` / `dream-entity-help` goldens hold them to the bash text.
H_DREAM = """wiki dream — sweep all entity pages (M014)

USAGE
  wiki dream                               sweep all entities, oldest-overdue first (default)
  wiki dream --dry-run                     print plan, no SDK calls
  wiki dream --limit N                     hard cap on entity count this run
  wiki dream list-candidates               debug: print scored candidate list, no run
  wiki dream web-research <slug>           public-entity web enrichment (issue #2, Exa)
  wiki dream web-research <slug> --dry-run print the Public Profile block, write nothing

NOTES
  Sweeps `knowledge/{people,projects,areas}/*.md` oldest-synthesized first,
  skipping entities synthesized within the cooldown window. Per-entity AND
  per-run cumulative cost caps are enforced — see `wiki dream-entity help`.
  `--all-entities` / `sweep` are accepted as legacy aliases."""

H_DREAM_ENTITY = """wiki dream-entity — re-synthesize ONE entity page (M014)

USAGE
  wiki dream-entity <slug>                resynthesize a single entity
  wiki dream-entity <slug> --dry-run      print prompt size + estimated cost only
  wiki dream-entity <slug> --ignore-cooldown   force-run despite last_synthesized_at
  wiki dream-entity <slug> --cost-cap 5.0      override per-entity USD cap

NOTES
  Slug must match `knowledge/{people,projects,areas}/<slug>.md` (without .md).
  Greps all substrate (raw/**, daily/**) for slug mentions, builds a corpus
  prompt, calls Claude Agent SDK to rewrite the entity's State block + append
  to Timeline. Pre-flight cost cap REJECTS the SDK call if estimate exceeds
  `limits.dream_entity_max_cost_usd` (default $2.00). Cooldown defaults
  to `scheduling.dream_cooldown_days` (default 7 days)."""

H_STATS = """wiki stats — read-only vault dashboard (what's in the vault)

USAGE
  wiki stats                  snapshot of the vault you run it from
  wiki stats --vault PATH     snapshot of another vault

NOTES
  Knowledge counts, raw-source distribution, compile backlog, an active compile
  run, graph density and pipeline cadence, as one colored snapshot. Read-only:
  never mutates state, never triggers a compile. `wiki doctor` says what is
  broken; this shows what is there. Wraps scripts/health.py, run from the
  engine's own environment (never a bare `uv run --project .wiki`, which on a
  cloud-synced vault recreates the in-vault venv)."""

# `wiki config` — moved from the bash `help_config` with the port (M034-S02-T02); the bash
# oracle's `config-help` golden holds it. Corrected since the move: the wizard asks 6
# questions (it said 5), the compile-model example names today's default, and
# procmail_execution is on by default and gates the All-Inkl procmail write (S02-T03; it said
# "off by default" while the default was true and nothing read it).
H_CONFIG = """wiki config — manage tunable parameters in .wiki/config.yaml

USAGE
  wiki config                       interactive editor (browse sections, edit fields)
  wiki config get KEY               print one value
  wiki config set KEY VALUE         set + write back
  wiki config keys                  list all settable keys
  wiki config path                  print path to config.yaml
  wiki config wizard                re-run the 6-question setup wizard
  wiki config status                summary table + Ollama probe

KEYS use dot-notation:
  models.compile_model              claude-opus-4-8 | claude-sonnet-4-6 | claude-haiku-4-5
  models.ollama_url                 e.g. http://localhost:11434
  scheduling.compile_after_hour     0–23 (auto-compile trigger hour, local time)
  features.curiosity_loop           true|false
  features.vision_screenshots       true|false
  features.procmail_execution       true|false (on by default; off stops All-Inkl procmail writes)
  piggybacks.<task>.enabled         e.g. piggybacks.scan_screenshots.enabled
  piggybacks.<task>.cooldown_hours  e.g. 24 (daily) or 168 (weekly)

EXAMPLES
  wiki config get models.compile_model
  wiki config set models.compile_model claude-sonnet-4-6
  wiki config set piggybacks.scan_screenshots.enabled false
  wiki config keys | grep features

Note: comments in config.yaml are dropped on programmatic writes (PyYAML round-trip)."""

# `wiki setup` — moved from the bash `help_setup` with the port (M034-S02-T03); the bash
# oracle's `setup-help` golden holds it. Corrected with the move: the wizard has 6 questions
# (it said 5 and left out the global skill), and procmail execution is on by default.
H_SETUP = """wiki setup — first-time setup

Walks the 6-question config wizard, then runs the hook installer.

WIZARD QUESTIONS
  1. Ollama base URL    (probed for reachability)
  2. Compile model      (opus | sonnet | haiku)
  3. Auto-compile hour  (0–23, local time)
  4. Procmail execution (All-Inkl procmail writes; on by default)
  5. Local-LLM features (curiosity loop + vision screenshots)
  6. Global skill       (link use-llm-wiki into ~/.claude/skills/)

Press Enter on any question to keep the current value."""

# `wiki install-shortcut` — moved from the bash heredoc with the port (M034-S02-T04); the
# bash oracle's `install-shortcut-help` golden holds it. One line added with the move: the
# refusal of a non-symlink at the link path (the bash deleted it).
H_INSTALL_SHORTCUT = """wiki install-shortcut — create `wiki` symlink on PATH

USAGE
  wiki install-shortcut         create ~/.local/bin/wiki → this vault's wiki
  wiki install-shortcut --print-only   show what would happen, don't write

Idempotent. Replaces a stale symlink pointing at a different vault.
Refuses to replace anything that is not a symlink (another program called `wiki`).
Reports if ~/.local/bin isn't on PATH and prints the one-line shell-rc
edit needed."""

# `wiki hooks` — moved from the bash `help_hooks` with the port (M034-S03-T05); the bash
# oracle's `hooks-help` golden holds it. Corrected with the move: uninstall removes the
# wiki's own commands by the one hook-command grammar (the help named `.wiki/hooks/`, which
# matched nothing current), the merge needs no jq, and Cursor registers all three events.
H_HOOKS = """wiki hooks — install session hooks into AI agent configs

USAGE
  wiki hooks install                interactive: pick agents + scope, merge hooks in
  wiki hooks uninstall              interactive: remove wiki-managed hooks
  wiki hooks status                 install table per agent / scope

TARGETS
  claude   .claude/settings.json     (Claude Code)
  codex    .codex/hooks.json         (OpenAI Codex CLI 0.30+)
  gemini   .gemini/settings.json     (Google Gemini CLI)
  cursor   .cursor/hooks.json        (Cursor 1.7+)

SCOPE
  user      ~/<.agent>/...           applies to all sessions
  project   <repo>/<.agent>/...      applies only when CWD is this repo

EVENT MAPPING (auto, per agent)
                  claude         codex          gemini         cursor
  session-start   SessionStart   SessionStart   SessionStart   sessionStart
  session-end     SessionEnd     Stop           SessionEnd     sessionEnd
  pre-compact     PreCompact     —              PreCompress    preCompact

SAFETY
  • Existing config files are merged — your other hooks and settings stay.
  • Every write makes a .bak.YYYYMMDD-HHMMSS backup first (a second one in the
    same second gets -2).
  • Uninstall removes only the wiki's own hook commands; a config without any is
    left alone.

NOT SUPPORTED
  pi         TypeScript-only hooks (~/.omp/agent/hooks/{pre,post}/*.ts)
  opencode   no native hooks yet (sst/opencode#5409)"""

# `wiki skills` — moved from the bash `help_skills` with the port (M034-S03-T06); the bash
# oracle's `skills-help` golden holds it. Static now, like every help here: it names
# `<vault>` where the bash printed this vault's path.
H_SKILLS = """wiki skills — wire engine skills into Claude Code

USAGE
  wiki skills install               symlink missing engine skills into .claude/skills/
  wiki skills install --global      also link global skills into ~/.claude/skills/
  wiki skills install --no-global   vault-local only (turns the global opt-in off)
  wiki skills uninstall             remove engine-owned symlinks (foreign entries kept)
  wiki skills uninstall --global    also remove this vault's global links + deregister
  wiki skills sync                  install missing + prune stale (run after wiki update)
  wiki skills status                per-skill linked / collision / missing table

NOTES
  Source: <vault>/.wiki/skills/
  Target: <vault>/.claude/skills/
  Only symlinks pointing at ../../.wiki/skills/<name> are managed.
  Foreign entries (your own skills, other tools) are never modified.

GLOBAL INSTALL
  Most skills operate inside a vault and stay vault-local. A few (currently:
  use-llm-wiki) let an agent in *any* project discover and use this wiki —
  those can also be linked into ~/.claude/skills/.
  The opt-in is the skills.global_install config key; the --global /
  --no-global flags are one-shot shortcuts that write it (so it persists —
  `wiki update` keeps an opted-in vault globally linked). The vault root is
  recorded in ${XDG_CONFIG_HOME:-$HOME/.config}/llm-wiki/vaults for the skill's
  discovery probe. Equivalent: wiki config set skills.global_install true."""

# `wiki status` — new with the port (M034-S03-T05): the bash `cmd_status` had no help.
H_STATUS = """wiki status — config + hooks + Ollama summary

USAGE
  wiki status                       the config summary with the Ollama probe
                                    (`wiki config status`), then the hooks table
                                    (`wiki hooks status`)"""

# `wiki seed` — the bash `cmd_seed` heredoc as static text (M034-S04-T04).
H_SEED = """wiki seed — re-apply engine templates to the vault root

USAGE
  wiki seed                     additive: add missing files, merge community-plugins
  wiki seed --check             read-only audit: report which templates have drifted
  wiki seed --force             overwrite existing vault templates with engine versions
  wiki seed <path> [--force|--check]   restrict to ONE file (surgical refresh)
  wiki seed --extract-custom <path>    capture a JSON config's drift into an overlay

WHAT IT DOES
  - Seeds missing files: README.md, AGENTS.md, dashboard.md, knowledge.base, .claude/.env.example
  - Seeds missing .obsidian/*.json + .obsidian/plugins/<name>/data.json
  - Merges community-plugins.json and the dashboard's CSS snippet (additive — adds
    the engine's, never drops yours)
  - Merges the dashboard's buttons into Meta-Bind's and Shell commands' settings by
    id: the engine's entries are kept current, yours stay
  - Cache files (_dashboard-*.md) are NOT seeded — first `wiki flush` writes them.

TARGETED (single file)
  Pass a vault-relative path to act on just that file — every other template is
  left untouched. Lets you refresh ONE stale file with --force without clobbering
  unrelated customisations (e.g. your QuickAdd macros or graph palette). A path
  that matches nothing is an error:
    wiki seed AGENTS.md --check          # audit just AGENTS.md
    wiki seed AGENTS.md --force          # refresh just AGENTS.md
    wiki seed .obsidian/app.json --check

CONFIG OVERLAYS (JSON configs — graph.json, app.json, plugin data.json)
  These are derived as engine-template ⊕ your overlay: the engine owns the
  base (so new-feature keys flow in on update), your customisations live in an
  untracked overlay at <vault>/.wiki/custom/<path>. Edit the overlay, not
  the live file — then `--force` re-derives non-destructively. To migrate an
  already-customised file, capture its current drift into an overlay once:
    wiki seed --extract-custom .obsidian/graph.json   # drift → .wiki/custom/...
    # …then edit .wiki/custom/.obsidian/graph.json going forward
    wiki seed .obsidian/graph.json --force            # re-derive base ⊕ overlay
  Markdown/YAML files (AGENTS.md, dashboard.md) are engine-owned — no overlay;
  refresh them with a targeted --force.

DRIFT REPORTING
  Default mode tags each kept-existing file as either up-to-date or
  drifted from engine. `--check` runs the same audit without writing
  anything — use it after `wiki update` to see what would change before
  deciding whether to `--force` or merge manually. JSON files that differ only
  in key order are reported up-to-date, not drifted.

SAFETY
  Default mode never overwrites your edits. Use --force only if you want to
  discard your customisations and pick up the latest engine version. Combine
  --force with a <path> to scope the overwrite to a single file."""

# The bash `cmd_update` heredoc (deleted in M034-S05-T03), as update-help.txt recorded it.
H_UPDATE = """wiki update — git pull --ff-only the .wiki/ checkout

USAGE
  wiki update                   pull + sync skill symlinks
  wiki update --no-skills       pull only, skip skill sync

NOTES
  If the .wiki/ checkout has uncommitted changes to tracked engine files
  (a --ff-only pull would abort on them), `wiki update` shows them and
  offers to `git stash` them so the pull can proceed. After the pull the
  stash is re-applied automatically — but only if it merges cleanly onto the
  new engine. If it would conflict, it's left unpopped (recover with
  `git -C <.wiki> stash pop`). Run from a terminal: non-interactively the
  command refuses rather than touching your changes.

  Everything after the pull (dependency sync, migrations, skills sync) runs
  from the engine just pulled — the command re-executes itself — so a changed
  update procedure applies in the same run, not the next one."""
