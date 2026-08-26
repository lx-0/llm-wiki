"""Lint the knowledge base for structural and semantic issues.

Usage:
    uv run python lint.py                    # full lint including LLM contradiction check
    uv run python lint.py --structural-only  # skip the LLM contradiction check

Architecture (C04 — link-graph + corpus model seam): every structural check is
a pure function ``check(ctx) -> list[Issue]`` over a `LintContext` built ONCE
per run. The context is the single corpus read — canonical article enumeration
(`core.utils.list_wiki_articles`, includes `knowledge/MOCs/`), parsed
frontmatter (`core.frontmatter`), stripped bodies, footer-aware outgoing slugs
(`core.links.outgoing_canonical_slugs` — the engine-written `## Backlinks`
footers are NOT link edges), and the derived inbound map (the one-O(N)-pass
rule from the 2026-05-30 incident lives in the builder). Issues carry a
structured payload (`fact_slug`, `target_slug`) so consumers (reconcile,
dashboards) never parse prose.
"""

import os
os.environ["CLAUDE_INVOKED_BY"] = "lint"

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from core import frontmatter
from core.backlinks import BACKLINKS_BEGIN, BACKLINKS_END
from core.paths import KNOWLEDGE_DIR, REPORTS_DIR, ROOT_DIR
from core.state_store import update_state
from core.utils import (
    extract_wikilinks,
    file_hash,
    list_raw_files,
    list_wiki_articles,
    load_state,
    now_iso,
    read_all_wiki_content,
    today_iso,
)
from core.links import (  # noqa: E402
    _strip_frontmatter_and_fences,
    canonical_slug,
    link_target,
    outgoing_canonical_slugs,
    resolve_link,
)

# ── Logging ──────────────────────────────────────────────────────────
from core.console import setup_console_logging  # noqa: E402
log = setup_console_logging("lint")

from core.config import CONFIG  # noqa: E402

SPARSE_THRESHOLD = CONFIG.limits.sparse_threshold_words


# ── Issue type ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class Issue:
    """One lint finding. `fact_slug` / `target_slug` are the structured
    payload consumers key on (reconcile groups by fact, dashboards link the
    target) — the `detail` prose is display-only, never parsed."""

    severity: str  # error, warning, suggestion
    check: str
    file: str
    detail: str
    auto_fixable: bool = False
    fact_slug: str | None = None
    target_slug: str | None = None


def issue(
    severity: str,
    check: str,
    file: str,
    detail: str,
    auto_fixable: bool = False,
    *,
    fact_slug: str | None = None,
    target_slug: str | None = None,
) -> Issue:
    """Create a structured Issue (factory keeps the historic call shape)."""
    return Issue(
        severity=severity,
        check=check,
        file=file,
        detail=detail,
        auto_fixable=auto_fixable,
        fact_slug=fact_slug,
        target_slug=target_slug,
    )


# ── Corpus model ────────────────────────────────────────────────────

@dataclass(frozen=True)
class Article:
    """One knowledge article, read + parsed exactly once per lint run."""

    path: Path
    rel: str                  # posix path relative to knowledge_dir, e.g. "concepts/foo.md"
    text: str                 # full file content
    fm: dict                  # tolerant frontmatter (core.frontmatter grammar)
    body: str                 # frontmatter-stripped body
    slug: str | None          # canonical knowledge slug, e.g. "concepts/foo"
    outgoing: frozenset[str]  # footer-aware outgoing canonical slugs


@dataclass(frozen=True)
class LintContext:
    """The corpus model every check runs over — built ONCE per run.

    `inbound` maps target slug → source slugs and is derived from the
    footer-aware `outgoing` sets, so the engine-materialized `## Backlinks`
    footers (M020) never count as link edges. This builder IS the one-O(N)-pass
    inbound computation (2026-05-30 decision); a per-article corpus rescan can
    only be reintroduced here, nowhere else.
    """

    vault: Path
    knowledge_dir: Path
    articles: tuple[Article, ...]
    index_content: str
    inbound: dict[str, set[str]]
    state: dict
    raw_files: tuple[Path, ...]


def build_context(
    *,
    vault: Path | None = None,
    knowledge_dir: Path | None = None,
    state: dict | None = None,
    raw_files: list[Path] | None = None,
) -> LintContext:
    """Build the LintContext: the single corpus read of a lint run.

    Defaults target the live vault; tests pass a temp ``vault`` /
    ``knowledge_dir`` (+ ``state={}``) to lint an in-memory corpus without
    monkeypatching module globals.
    """
    vault = vault if vault is not None else ROOT_DIR
    kdir = knowledge_dir if knowledge_dir is not None else KNOWLEDGE_DIR

    articles: list[Article] = []
    for path in list_wiki_articles(kdir):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm, body = frontmatter.parse(text)
        articles.append(Article(
            path=path,
            rel=path.relative_to(kdir).as_posix(),
            text=text,
            fm=fm,
            body=body,
            slug=canonical_slug(path, kdir),
            outgoing=frozenset(outgoing_canonical_slugs(
                text, path, vault, kdir, BACKLINKS_BEGIN, BACKLINKS_END
            )),
        ))

    inbound: dict[str, set[str]] = {}
    for art in articles:
        if art.slug is None:
            continue
        for tgt in art.outgoing:
            if tgt == art.slug:
                continue  # self-links are not inbound edges
            inbound.setdefault(tgt, set()).add(art.slug)

    index_file = kdir / "index.md"
    try:
        index_content = index_file.read_text(encoding="utf-8") if index_file.exists() else ""
    except OSError:
        index_content = ""

    if state is None:
        state = load_state()
    if raw_files is None:
        raw_files = list_raw_files(daily_dir=vault / "daily", raw_dir=vault / "raw")

    return LintContext(
        vault=vault,
        knowledge_dir=kdir,
        articles=tuple(articles),
        index_content=index_content,
        inbound=inbound,
        state=state,
        raw_files=tuple(raw_files),
    )


def _in_folder(ctx: LintContext, folder: str) -> list[Article]:
    """Articles under ``knowledge/<folder>/``, index.md/log.md filtered."""
    prefix = f"{folder}/"
    return [
        a for a in ctx.articles
        if a.rel.startswith(prefix) and a.path.name not in ("index.md", "log.md")
    ]


# ── Structural checks ───────────────────────────────────────────────

def check_broken_links(ctx: LintContext) -> list[Issue]:
    """Find wikilinks that point to non-existent targets.

    All targets (knowledge/, daily/, raw/notes/, raw/articles/, …) get
    the ordinary broken-link check — no per-subtree exceptions.
    `core.links.resolve_link` is the single resolver: it tries the target
    relative to the source article, the vault root, and ``<vault>/knowledge/``.
    """
    issues = []
    for art in ctx.articles:
        # Skip frontmatter + fenced code, exactly like links_audit and the
        # rewrite passes: a `[[…]]` inside a ```bash block is sample code, not
        # a reference, and reporting it as a broken link is a false positive
        # the operator cannot fix (2026-08-26).
        for _, line, live in _strip_frontmatter_and_fences(art.text.split("\n")):
            if not live:
                continue
            for link in extract_wikilinks(line):
                target = link_target(link)
                if resolve_link(target, art.path, ctx.vault) is None:
                    issues.append(issue(
                        "error", "broken_link", art.rel,
                        f"Broken link: [[{link}]] — target does not exist",
                        target_slug=target,
                    ))
    return issues


# Folders whose pages are orphan-by-design: facts are authoritative overrides,
# MOC hubs are graph ROOTS (they link out to articles; nothing links back to a
# hub, and hubs are reached via dashboard.md, outside knowledge/).
_ORPHAN_EXEMPT_PREFIXES = ("facts/", "MOCs/")


def check_orphan_pages(ctx: LintContext) -> list[Issue]:
    """Find wiki articles that no other article links to.

    Footer-aware since C04: inbound edges come from `ctx.inbound`, which is
    derived from `outgoing_canonical_slugs` — the sentinel `## Backlinks`
    footer M020 writes into every linked-to article is excluded. (Footer-blind
    counting gave every out-linking article a "free" inbound from its own
    materialized footer, so only fully isolated islands were ever flagged —
    backlog/orphan-check-footer-masking.md.) In-`index.md` membership still
    counts as non-orphan, unchanged.
    """
    issues = []
    for art in ctx.articles:
        if art.rel.startswith(_ORPHAN_EXEMPT_PREFIXES):
            continue
        if art.slug is None:
            continue
        name = art.rel[:-3] if art.rel.endswith(".md") else art.rel
        inbound = len(ctx.inbound.get(art.slug, set()))
        in_index = f"[[{name}]]" in ctx.index_content

        if inbound == 0 and not in_index:
            issues.append(issue(
                "warning", "orphan_page", art.rel,
                f"Orphan page: no other articles link to [[{name}]]",
            ))
    return issues


def check_orphan_sources(ctx: LintContext) -> list[Issue]:
    """Find daily/raw source files that were never compiled into any article."""
    issues = []
    ingested = ctx.state.get("ingested", {})

    for source in ctx.raw_files:
        rel = str(source.relative_to(ctx.vault))
        if rel not in ingested:
            issues.append(issue(
                "warning", "orphan_source", rel,
                f"Uncompiled source: {rel} has not been ingested",
            ))
    return issues


def check_stale_articles(ctx: LintContext) -> list[Issue]:
    """Find articles whose source files have changed since last compilation."""
    issues = []
    ingested = ctx.state.get("ingested", {})

    for source in ctx.raw_files:
        rel = str(source.relative_to(ctx.vault))
        if rel not in ingested:
            continue
        # state.ingested[rel] is a hash string (compile.py writes file_hash(source) directly).
        # Older state files used a {hash, compiled_at, ...} dict shape — handle both defensively.
        stored = ingested[rel]
        if isinstance(stored, dict):
            stored_hash = stored.get("hash", "")
        else:
            stored_hash = str(stored)
        current_hash = file_hash(source)
        if stored_hash != current_hash:
            issues.append(issue(
                "warning", "stale_article", rel,
                f"Stale: {rel} has changed since last compilation",
            ))
    return issues


# check_missing_backlinks was removed in C04: M020 materializes the reciprocal
# edge into every linked-to article's `## Backlinks` footer on each compile, so
# reciprocity is an engine invariant now — footer-blind the check was vacuous
# (the footer satisfied it), footer-stripped it would flag every deliberate
# one-directional body link. See the C04 decision entry in .ytstack/DECISIONS.md.


FOLDER_TO_TYPE = {
    "concepts": "concept",
    "connections": "connection",
    "qa": "qa",
    "people": "person",
    "projects": "project",
    "MOCs": "moc",
    "facts": "fact",
    "areas": "area",
    "takes": "takes",
}


def _read_frontmatter(path: Path) -> dict:
    """Frontmatter dict via the single core.frontmatter grammar (C03) —
    returns {} on unreadable file / no fence / malformed YAML. Values carry
    YAML types (lists, bools). Used for files OUTSIDE the knowledge corpus
    (raw/, daily/, inbox/ walks); knowledge articles carry their parsed
    frontmatter on `Article.fm`."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return frontmatter.parse(text)[0]


def check_article_type(ctx: LintContext) -> list[Issue]:
    """Verify every knowledge article carries `type:` and that it matches its folder."""
    issues = []
    for art in ctx.articles:
        if art.path.name in ("index.md", "log.md"):
            continue
        # First path segment under knowledge/ is the substrate folder.
        parts = art.rel.split("/")
        if len(parts) < 2:
            continue  # top-level file other than index/log — not a typed article
        folder = parts[0]
        expected = FOLDER_TO_TYPE.get(folder)
        if expected is None:
            continue  # unknown folder — let other checks handle it
        actual = art.fm.get("type")
        if not actual:
            issues.append(issue(
                "warning", "missing_type", art.rel,
                f"Missing `type:` frontmatter — expected `type: {expected}` (matches folder `{folder}/`)",
                auto_fixable=True,
            ))
        elif actual != expected:
            issues.append(issue(
                "warning", "type_mismatch", art.rel,
                f"`type: {actual}` does not match folder `{folder}/` (expected `type: {expected}`)",
                auto_fixable=True,
            ))
    return issues


# Domain tags considered "meaningful" for graph-view coloring. A qa/ note
# without any of these gets a warning so it doesn't fall into the grey
# fallback bucket. List is sourced from CONFIG.graph_view.domain_tags when
# present; fallback covers the lxw vault's main domains. Add via config.yaml:
#   graph_view:
#     domain_tags: [fleet, openclaw, claude-code, ...]
_DEFAULT_DOMAIN_TAGS = (
    "fleet", "openclaw", "claude-code", "yesterday", "llm-wiki",
    "paperclip", "ytstack", "township", "pixeltales", "lxw",
)


def _domain_tags() -> tuple[str, ...]:
    cfg = getattr(CONFIG.graph_view, "domain_tags", None)
    if cfg and isinstance(cfg, list):
        return tuple(t for t in cfg if isinstance(t, str))
    return _DEFAULT_DOMAIN_TAGS


def check_qa_schema(ctx: LintContext) -> list[Issue]:
    """Verify each knowledge/qa/ note has type:qa, an index row, and ≥1 domain tag.

    qa/ notes are written by `wiki query --file-back` via the Claude SDK. The
    prompt instructs three follow-up steps (frontmatter type, index row, log
    entry) but historically the agent sometimes reports success while skipping
    one. This check catches that drift.
    """
    issues = []
    domain_set = set(_domain_tags())
    for art in _in_folder(ctx, "qa"):
        # 1. type: qa required
        if art.fm.get("type") != "qa":
            actual = art.fm.get("type") or "(missing)"
            issues.append(issue(
                "error", "qa_missing_type", art.rel,
                f"qa/ note has `type: {actual}` — must be `type: qa` per schema",
                auto_fixable=True,
            ))
        # 2. must appear in index.md
        stem = art.path.stem
        if f"[[qa/{stem}]]" not in ctx.index_content:
            issues.append(issue(
                "warning", "qa_not_in_index", art.rel,
                f"qa/{stem} is not referenced in knowledge/index.md — "
                f"`wiki query --file-back` should have added a row",
            ))
        # 3. should have ≥1 domain tag (else falls into grey bucket in graph view)
        raw_tags = art.fm.get("tags") or []
        tags = set(raw_tags) if isinstance(raw_tags, list) else set()
        # Strip the redundant `qa` tag — that information lives in type:
        if not (tags & domain_set):
            issues.append(issue(
                "warning", "qa_no_domain_tag", art.rel,
                f"qa/ note has no domain tag from {sorted(domain_set)} — "
                f"will render grey in graph view. Add e.g. `tags: [llm-wiki]`.",
            ))
    return issues


def check_concept_domain_tag(ctx: LintContext) -> list[Issue]:
    """Warn on knowledge/concepts/ and knowledge/connections/ notes whose tags
    miss any domain anchor.

    Concepts/ is the largest folder (87% of lxw vault). Connections/ — added
    by M012 (2026-05-16) — sits in the same graph-coloring regime: without a
    tag from `graph_view.domain_tags`, the note paints into the grey-fallback
    color group and disappears into the visual hairball. The compile prompt
    now requires a domain tag at creation for both article types; this check
    surfaces pre-rule notes and any future drift.

    Issue code stays `concept_no_domain_tag` for backwards compat (existing
    operator dashboards filter on this code); the `detail` string names the
    actual folder so the surface remains diagnosable.
    """
    issues = []
    domain_set = set(_domain_tags())
    for folder in ("concepts", "connections"):
        for art in _in_folder(ctx, folder):
            raw_tags = art.fm.get("tags") or []
            # str-coerce: YAML parses bare numeric tags as ints, and a mixed
            # str/int set makes sorted() raise (live check-crash 2026-08-24).
            tags = {str(t) for t in raw_tags} if isinstance(raw_tags, list) else set()
            if not (tags & domain_set):
                issues.append(issue(
                    "warning", "concept_no_domain_tag", art.rel,
                    f"{folder[:-1]} has no tag from {sorted(domain_set)} — "
                    f"will render grey in graph view. Current tags: {sorted(tags)[:6]}",
                ))
    return issues


# Frontmatter discriminator fields a `type: connection` article must carry to
# declare what KIND of connection it is. At least one must be present and
# non-empty. Names chosen to match the discourse-graph vocabulary from the
# spec at `.ytstack/backlog/connection-quality.md`:
#   - mechanism: "X enables Y because Z" (causal/dependency-via-mechanism)
#   - tension:   "X contradicts / pulls against Y" (contrast/contradiction)
#   - dependency: "Y cannot exist without X" (hard prereq, no mechanism claim)
CONNECTION_KIND_FIELDS = ("tension", "mechanism", "dependency")


def check_connection_depth(ctx: LintContext) -> list[Issue]:
    """Quality gate for `knowledge/connections/` articles (M012).

    A connection article MUST:
      1. cite ≥2 distinct knowledge-tree wikilinks (a connection between only
         one concept is just a tag);
      2. carry exactly one of `tension|mechanism|dependency` frontmatter
         fields (the discriminator for what kind of relationship is being
         claimed);
      3. have a body word-count ≥ `CONFIG.limits.connection_min_words`
         (shorter bodies almost always restate the linked concepts instead
         of asserting a real mechanism/contrast/dependency).

    Each violation surfaces as its own issue code so dashboards can route
    them independently:
      - `connection_under_linked`      (rule 1)
      - `connection_missing_kind`      (rule 2)
      - `connection_shallow_body`      (rule 3)

    Skips index.md / log.md. Notes that haven't been migrated to
    `type: connection` yet (folder-only) are still checked — rule 1 + 3 hold
    regardless of frontmatter, rule 2 fires the missing-kind warning.
    """
    issues: list[Issue] = []
    min_words = CONFIG.limits.connection_min_words

    for art in _in_folder(ctx, "connections"):
        # Rule 1: ≥2 distinct knowledge-tree wikilinks. Endpoint cardinality is
        # a structural property, not an existence one (broken_link owns that),
        # so count lexically without resolving to disk. Substrate citations
        # (daily/raw) are excluded regardless of relative depth — strip any
        # leading `./` / `../` before testing the prefix (`../../daily/…`).
        knowledge_links: set[str] = set()
        for link in extract_wikilinks(art.body):
            target = link_target(link)
            if target.lstrip("./").startswith(("daily/", "raw/")):
                continue
            knowledge_links.add(target)
        if len(knowledge_links) < 2:
            issues.append(issue(
                "warning", "connection_under_linked", art.rel,
                f"connection article cites only {len(knowledge_links)} distinct "
                f"knowledge wikilink(s) — a connection MUST name ≥2 endpoints "
                f"(found: {sorted(knowledge_links)})",
            ))

        # Rule 2: one of tension/mechanism/dependency must be present + non-empty.
        present_kinds = [
            k for k in CONNECTION_KIND_FIELDS
            if k in art.fm and art.fm[k] not in (None, "", [])
        ]
        if not present_kinds:
            issues.append(issue(
                "warning", "connection_missing_kind", art.rel,
                f"connection article missing a kind discriminator — exactly one of "
                f"{list(CONNECTION_KIND_FIELDS)} must be present in frontmatter "
                f"to declare whether this is a mechanism / contrast / hard-dependency",
                auto_fixable=True,
            ))

        # Rule 3: body word-count ≥ floor.
        body_word_count = len(art.body.split())
        if body_word_count < min_words:
            issues.append(issue(
                "warning", "connection_shallow_body", art.rel,
                f"connection article body is {body_word_count} words "
                f"(minimum {min_words}) — too short to assert a real mechanism / "
                f"contrast / dependency beyond restating the linked concepts",
            ))

    return issues


def check_two_layer_pages(ctx: LintContext) -> list[Issue]:
    """Enforce the two-layer State+Timeline shape for `type: person|project` articles.

    Each entity page MUST have: a `## State` heading, a body-level `---` separator
    between State and Timeline, a `## Timeline` heading, and Timeline entries in
    reverse-chronological order. If an `## Action Items` section is present, its
    non-empty list lines must start with `- [ ]` or `- [x]` (full Obsidian-Tasks-
    plugin syntax validation lives in check_action_item_syntax).

    Spec: prompts/compile_main.md Instruction 3 + templates/AGENTS.example.md.
    Reference fixtures: tests/fixtures/two_layer/.
    """
    import re
    issues: list[Issue] = []
    entity_folders = (("people", "person"), ("projects", "project"))
    for folder, expected_type in entity_folders:
        for art in _in_folder(ctx, folder):
            if art.fm.get("type") != expected_type:
                # Type-mismatch is caught by check_article_type; don't double-report
                continue

            body = art.body

            has_state = re.search(r"^## State\s*$", body, re.MULTILINE) is not None
            has_timeline = re.search(r"^## Timeline\s*$", body, re.MULTILINE) is not None
            separator_lines = [m.start() for m in re.finditer(r"^---\s*$", body, re.MULTILINE)]
            timeline_match = re.search(r"^## Timeline\s*$", body, re.MULTILINE)
            has_body_separator = bool(
                separator_lines and timeline_match
                and any(pos < timeline_match.start() for pos in separator_lines)
            )

            if not has_state:
                issues.append(issue(
                    "error", "two_layer_missing_state", art.rel,
                    f"`type: {expected_type}` article missing `## State` section "
                    f"(spec: prompts/compile_main.md Instruction 3)",
                ))
            if not has_body_separator:
                issues.append(issue(
                    "error", "two_layer_missing_body_separator", art.rel,
                    f"`type: {expected_type}` article missing the `---` separator "
                    f"between State and Timeline blocks",
                ))
            if not has_timeline:
                issues.append(issue(
                    "error", "two_layer_missing_timeline", art.rel,
                    f"`type: {expected_type}` article missing `## Timeline` section",
                ))

            # Reverse-chronological check on Timeline entries
            if has_timeline:
                tail = body[timeline_match.end():]
                # Match `- **YYYY-MM-DD**` line starts
                dates = re.findall(r"^- \*\*(\d{4}-\d{2}-\d{2})\*\*", tail, re.MULTILINE)
                for i in range(len(dates) - 1):
                    if dates[i] < dates[i + 1]:
                        issues.append(issue(
                            "warning", "timeline_not_reverse_chronological", art.rel,
                            f"Timeline entries out of order: {dates[i]} before {dates[i + 1]} "
                            f"(newest first expected)",
                        ))
                        break  # one warning per file

            # Action Items prefix sanity (deep syntax = T02)
            ai_match = re.search(r"^## Action Items\s*$", body, re.MULTILINE)
            if ai_match:
                # Scan lines until next `## ` heading or `---`
                after = body[ai_match.end():]
                section_end = re.search(r"^(## |---\s*$)", after, re.MULTILINE)
                section = after[:section_end.start()] if section_end else after
                for raw_line in section.splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    if not (line.startswith("- [ ]") or line.startswith("- [x]") or line.startswith("- [X]")):
                        issues.append(issue(
                            "warning", "action_items_malformed", art.rel,
                            f"Action Items line does not start with `- [ ]` or `- [x]`: "
                            f"{line[:80]!r}",
                        ))
                        break  # one warning per file
    return issues


def check_action_item_syntax(ctx: LintContext) -> list[Issue]:
    """Validate Obsidian-Tasks-plugin syntax inside `## Action Items` sections
    of entity pages (knowledge/people/ + knowledge/projects/).

    T01's `check_two_layer_pages` validates the `- [ ]` / `- [x]` prefix.
    This check goes deeper: 📅 due-date format, ⏫ priority placement, 🔁
    recurrence content. All issues are warnings (quality nudges, not
    structural breaks). One issue per file per rule.
    """
    import re
    issues: list[Issue] = []
    entity_folders = (("people", "person"), ("projects", "project"))
    DATE_RE = re.compile(r"📅 (\d{4}-\d{2}-\d{2})(?:\s|$)")
    DATE_PREFIX_RE = re.compile(r"📅 ")
    PRIORITY_RE = re.compile(r"(?:^|\s)⏫(?:\s|$)")
    PRIORITY_PREFIX_RE = re.compile(r"⏫")
    RECURRENCE_RE = re.compile(r"🔁 \S")
    RECURRENCE_PREFIX_RE = re.compile(r"🔁(?:\s|$)")
    for folder, expected_type in entity_folders:
        for art in _in_folder(ctx, folder):
            if art.fm.get("type") != expected_type:
                continue
            text = art.text
            # Locate ## Action Items section
            ai_match = re.search(r"^## Action Items\s*$", text, re.MULTILINE)
            if not ai_match:
                continue
            after = text[ai_match.end():]
            section_end = re.search(r"^(## |---\s*$)", after, re.MULTILINE)
            section = after[:section_end.start()] if section_end else after

            invalid_date = False
            malformed_priority = False
            empty_recurrence = False
            for raw_line in section.splitlines():
                line = raw_line.strip()
                if not line.startswith("- ["):
                    continue
                if DATE_PREFIX_RE.search(line) and not DATE_RE.search(line):
                    invalid_date = True
                if PRIORITY_PREFIX_RE.search(line) and not PRIORITY_RE.search(line):
                    malformed_priority = True
                if RECURRENCE_PREFIX_RE.search(line) and not RECURRENCE_RE.search(line):
                    empty_recurrence = True

            if invalid_date:
                issues.append(issue(
                    "warning", "action_item_invalid_due_date", art.rel,
                    "Action Items section contains `📅` without a valid `YYYY-MM-DD` date — "
                    "Obsidian-Tasks-plugin syntax expects `📅 2026-05-20`",
                ))
            if malformed_priority:
                issues.append(issue(
                    "warning", "action_item_malformed_priority", art.rel,
                    "Action Items section contains `⏫` not bounded by whitespace — "
                    "must be standalone token, not concatenated to adjacent glyphs",
                ))
            if empty_recurrence:
                issues.append(issue(
                    "warning", "action_item_empty_recurrence", art.rel,
                    "Action Items section contains `🔁` without recurrence content — "
                    "Obsidian-Tasks-plugin syntax expects `🔁 every week` (or similar)",
                ))
    return issues


_VALID_AREA_STATUS = ("active", "dormant", "retired")


def check_area_status(ctx: LintContext) -> list[Issue]:
    """Validate `status:` frontmatter on `knowledge/areas/` pages.

    Areas (`type: area`) are ongoing responsibilities; they carry a
    `status:` field that must be one of `active | dormant | retired`
    (distinct from project status — areas don't `plan` or `done`).
    Missing status is an error; an unknown enum value is also an error.
    """
    issues: list[Issue] = []
    for art in _in_folder(ctx, "areas"):
        if art.fm.get("type") != "area":
            # type mismatch handled by check_article_type; don't double-report
            continue
        status = art.fm.get("status")
        if not status:
            issues.append(issue(
                "error", "area_missing_status", art.rel,
                f"`type: area` article missing `status:` frontmatter "
                f"(must be one of {list(_VALID_AREA_STATUS)})",
                auto_fixable=True,
            ))
            continue
        if status not in _VALID_AREA_STATUS:
            issues.append(issue(
                "error", "area_invalid_status", art.rel,
                f"`status: {status!r}` is not a valid area status. "
                f"Allowed: {list(_VALID_AREA_STATUS)}.",
            ))
    return issues


def check_sparse_articles(ctx: LintContext) -> list[Issue]:
    """Find articles with fewer than SPARSE_THRESHOLD words (frontmatter excluded)."""
    issues = []
    for art in ctx.articles:
        if art.rel.startswith("facts/"):
            continue  # facts may legitimately be terse
        word_count = len(art.body.split())
        if word_count < SPARSE_THRESHOLD:
            issues.append(issue(
                "suggestion", "sparse_article", art.rel,
                f"Sparse article: {word_count} words (minimum recommended: {SPARSE_THRESHOLD})",
            ))
    return issues


def check_daily_consistency(ctx: LintContext) -> list[Issue]:
    """Verify the daily/-rollup invariants (post-2026-05-15 architecture).

    Two structural rules — both warnings, neither blocks:

    1. **Subfolder ↔ root digest pairing.** When `daily/<date>/` exists with
       any per-source captures, `daily/<date>.md` should also exist (the
       compile-stage digest). The digest is produced by the
       `daily-digest` agent / `daily_digest_yesterday` piggyback; a
       missing root file means the digest pass hasn't run yet or has
       failed silently. Inverse: a root file without a subfolder is a
       legacy pre-2026-05-15 flat-daily — flagged for migration.
    2. **Known sources only.** Files under `daily/<date>/` should match
       `core.daily_capture.KNOWN_SOURCES`. Stray files (e.g. operator-
       hand-typed `daily/2026-05-14/scratchpad.md`) get a quality nudge
       — either rename to a known source or move out of `daily/`.

    Skips the current day's date (digest legitimately not run yet).
    """
    import re
    from datetime import date as _date
    issues: list[Issue] = []
    daily_root = ctx.vault / "daily"
    if not daily_root.is_dir():
        return issues

    try:
        from core.daily_capture import KNOWN_SOURCES
    except ImportError:
        KNOWN_SOURCES = frozenset()

    today_iso = _date.today().isoformat()
    iso_date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    iso_md_re = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")

    # Collect dates with subfolders + with root files
    subfolder_dates: dict[str, list[str]] = {}
    root_md_dates: set[str] = set()

    for entry in daily_root.iterdir():
        if entry.is_dir() and iso_date_re.match(entry.name):
            captures = sorted(p.name for p in entry.glob("*.md"))
            if captures:
                subfolder_dates[entry.name] = captures
        elif entry.is_file() and iso_md_re.match(entry.name):
            root_md_dates.add(entry.stem)

    for d, captures in subfolder_dates.items():
        if d == today_iso:
            continue  # digest may not have run yet for today
        if d not in root_md_dates:
            issues.append(issue(
                "warning", "daily_missing_digest", f"daily/{d}.md",
                f"daily/{d}/ has {len(captures)} per-source capture(s) "
                f"({', '.join(captures)}) but no root digest. Run "
                f"`wiki agent daily-digest --var date={d}` to produce it.",
            ))
        else:
            # Root exists. Verify it's a real digest, not a legacy flat-daily
            # left behind by the migration script (which copies, doesn't move).
            root_fm = _read_frontmatter(daily_root / f"{d}.md")
            if root_fm.get("type") != "daily-digest":
                issues.append(issue(
                    "warning", "daily_root_not_digest", f"daily/{d}.md",
                    f"daily/{d}.md exists alongside daily/{d}/ but has "
                    f"type={root_fm.get('type')!r} (not 'daily-digest'). "
                    "Likely a legacy flat-daily preserved by the migration. "
                    f"Run `wiki agent daily-digest --var date={d}` to "
                    "regenerate it as a proper digest, OR delete it if the "
                    "subfolder content is sufficient.",
                ))
        # Unknown sources nudge
        for cap in captures:
            stem = cap[:-3] if cap.endswith(".md") else cap
            if KNOWN_SOURCES and stem not in KNOWN_SOURCES:
                issues.append(issue(
                    "warning", "daily_unknown_source", f"daily/{d}/{cap}",
                    f"Source name {stem!r} is not in daily_capture.KNOWN_SOURCES "
                    f"({sorted(KNOWN_SOURCES)}). Rename or relocate.",
                ))

    for d in root_md_dates - set(subfolder_dates):
        if d == today_iso:
            continue
        issues.append(issue(
            "warning", "daily_legacy_flat", f"daily/{d}.md",
            f"daily/{d}.md exists without a daily/{d}/ subfolder — this is "
            "the pre-2026-05-15 flat-daily shape. Run "
            "`uv run python scripts/migrate_daily_to_rollup.py --vault <path>` "
            "to migrate.",
        ))

    return issues


def _superseded_by_fact(art_fm: dict, slug: str) -> bool:
    """True if the article is already annotated as superseded BY this fact.

    Such an article keeps the negated term in its historical body on purpose
    (M028 supersede-default), so it must not be re-flagged as a violation —
    the annotation IS the resolution. An article superseded by a *different*
    fact still violates this one.
    """
    if art_fm.get("status") != "superseded":
        return False
    ref = str(art_fm.get("superseded_by") or "")
    return ref.rsplit("/", 1)[-1].removesuffix(".md") == slug


def check_facts_violations(ctx: LintContext) -> list[Issue]:
    """For each hard fact with negation_terms, grep all non-facts knowledge files for hits.

    Each hit is a `warning` issue carrying the fact's slug in the structured
    `fact_slug` payload (consumers — `wiki reconcile` — group on that field,
    never on the prose detail): an article asserts something a hard fact
    negates. Disambiguation/clarification facts contribute no structural lint
    hits — those drift cases need the LLM contradiction check (or the agentic
    correct-apply processor). An article already annotated `status: superseded`
    by the fact is not re-flagged.
    """
    issues: list[Issue] = []

    facts_with_terms: list[tuple[str, str, list[str]]] = []  # (slug, status, terms)
    for fact in _in_folder(ctx, "facts"):
        terms = fact.fm.get("negation_terms") or []
        if not isinstance(terms, list):
            continue
        terms = [t for t in terms if isinstance(t, str) and t.strip()]
        if not terms:
            continue
        status = str(fact.fm.get("status", "negation"))
        facts_with_terms.append((fact.path.stem, status, terms))

    if not facts_with_terms:
        return issues

    for art in ctx.articles:
        if art.rel.startswith("facts/"):
            continue
        content_lower = art.text.lower()
        for slug, status, terms in facts_with_terms:
            if _superseded_by_fact(art.fm, slug):
                continue  # already annotated as superseded by this fact
            for term in terms:
                if term.lower() in content_lower:
                    issues.append(issue(
                        "warning", "fact_violation", art.rel,
                        f"Article contains negation term {term!r} from hard fact `facts/{slug}` (status: {status}). Reconcile manually or via `wiki correct apply {slug}`.",
                        fact_slug=slug,
                    ))
    return issues


# ── Takes substrate (M011) ──────────────────────────────────────────

import re as _re_takes

_TAKE_LINE_RE = _re_takes.compile(
    r"^- \*\*\d{4}-\d{2}-\d{2}\*\* \[(?:low|medium|high)\] · `[^`]+` — .+$"
)


def check_takes_consistency(ctx: LintContext) -> list[Issue]:
    """Validate `knowledge/takes/*.md` shape (M011, v1 — shape-only).

    Per-file checks:
      - Frontmatter `type: takes` is present.
      - Frontmatter `holder:` is present (non-empty).
      - Every body line that starts with `- **` matches the canonical
        take regex; malformed lines surface as warnings.
    """
    issues: list[Issue] = []
    for art in _in_folder(ctx, "takes"):
        if art.fm.get("type") != "takes":
            issues.append(issue(
                "error", "takes_frontmatter_type", art.rel,
                "Takes file must carry `type: takes` in frontmatter.",
            ))
        holder = art.fm.get("holder")
        if not holder or not str(holder).strip():
            issues.append(issue(
                "error", "takes_frontmatter_holder_missing", art.rel,
                "Takes file must carry a non-empty `holder:` field in frontmatter.",
            ))
        for lineno, line in enumerate(art.body.splitlines(), start=1):
            if not line.startswith("- **"):
                continue
            if not _TAKE_LINE_RE.match(line):
                issues.append(issue(
                    "warning", "takes_line_malformed", art.rel,
                    f"Line {lineno} does not match canonical take shape: {line[:120]}",
                ))
    return issues


# ── compile_role enum validation (M007-S01-T03) ─────────────────────

from core.compile_role import VALID_ROLES as _COMPILE_ROLE_VALID  # noqa: E402


def check_domain_value(ctx: LintContext) -> list[Issue]:
    """Warn on `domain:` frontmatter values outside CONFIG.personal.domains.

    Optional axis (M013). When `domain:` is set on a knowledge/ article, it
    MUST be one of the configured values (default `["company", "personal",
    "ai", "meta"]`, extensible per vault). Articles without `domain:` are
    silently ignored — the feature is opt-in. WARNING (not error): the
    operator gets a grace period to fix typos / introduce new domains via
    config before drift becomes a hard fail. Empty `personal.domains` list
    disables the check entirely (operator opted out).

    Spec: `.ytstack/backlog/domain-frontmatter.md`.
    """
    issues: list[Issue] = []
    domains_cfg = getattr(CONFIG.personal, "domains", None) or []
    valid = {d for d in domains_cfg if isinstance(d, str)}
    if not valid:
        return issues
    for art in ctx.articles:
        value = art.fm.get("domain")
        if value is None:
            continue
        if not isinstance(value, str) or value not in valid:
            allowed = ", ".join(sorted(valid))
            issues.append(issue(
                "warning", "domain_invalid_value", art.rel,
                f"`domain: {value!r}` is not in CONFIG.personal.domains "
                f"({allowed}). Fix the value, or add it to config.yaml "
                f"under `personal.domains:`.",
            ))
    return issues


def _iter_vault_frontmatters(ctx: LintContext):
    """Yield ``(vault_rel, fm)`` for every `.md` under raw/, daily/, inbox/
    (walked + parsed here) and knowledge/ (reused from the corpus model —
    no second knowledge read)."""
    for root in (ctx.vault / "raw", ctx.vault / "daily", ctx.vault / "inbox"):
        if not root.exists():
            continue
        for md in root.rglob("*.md"):
            yield str(md.relative_to(ctx.vault)), _read_frontmatter(md)
    for art in ctx.articles:
        try:
            rel = art.path.relative_to(ctx.vault).as_posix()
        except ValueError:
            rel = f"knowledge/{art.rel}"
        yield rel, art.fm


def check_compile_role(ctx: LintContext) -> list[Issue]:
    """Reject frontmatter `compile_role:` values not in VALID_ROLES.

    Walks every `.md` under raw/, daily/, knowledge/, inbox/. Files that omit
    `compile_role:` get no issue (default-by-location inference handles them
    at compile time per `scripts.core.compile_role.infer_compile_role`).

    Cross-location-move warning (slice plan mentions detecting renames across
    top-level boundaries without explicit override) is deferred — needs
    git-history walk, tracked as follow-up.
    """
    issues: list[Issue] = []
    for rel, fm in _iter_vault_frontmatters(ctx):
        role = fm.get("compile_role")
        if role is None:
            continue
        if role not in _COMPILE_ROLE_VALID:
            valid_list = ", ".join(sorted(_COMPILE_ROLE_VALID))
            issues.append(issue(
                "error", "compile_role_invalid", rel,
                f"`compile_role: {role!r}` is not a valid value. "
                f"Allowed: {valid_list}.",
            ))
    return issues


def check_author_required_on_source_and_final(ctx: LintContext) -> list[Issue]:
    """`compile_role: source-and-final` pages MUST carry `author:` frontmatter.

    Provenance protection: when operator-personal content sits in
    knowledge/concepts/ alongside compile-output concepts, the only thing
    distinguishing them is the frontmatter author + compile_role pair. If a
    source-and-final page loses its `author:` field, the page becomes
    indistinguishable from a regular compile-output concept and can drown in
    the noise. This check makes that loss detectable at lint time.

    (Operator-feedback after M014 dream-cycle: "ich will nicht, dass meine
    persoenlichen texte irgendwann einfach rausgefiltert werden oder
    unbedeutend werden". Lint is the enforcement surface.)
    """
    issues: list[Issue] = []
    for rel, fm in _iter_vault_frontmatters(ctx):
        if fm.get("compile_role") != "source-and-final":
            continue
        if not fm.get("author"):
            issues.append(issue(
                "error", "source_and_final_missing_author", rel,
                "`compile_role: source-and-final` requires an `author:` "
                "frontmatter field. Without it, operator-authored content "
                "is indistinguishable from compile-output and can drown "
                "in the noise. Add `author: <name>` (or set "
                "`personal.implicit_operator_author` and operator-author "
                "files inherit it).",
            ))
    return issues


# ── LLM contradiction check ─────────────────────────────────────────

from core.prompts import render  # noqa: E402
from core.sdk_helpers import StderrCapture, log_sdk_failure  # noqa: E402
import time as _time  # noqa: E402


async def check_contradictions() -> list[Issue]:
    """Use an LLM to find contradictions between articles."""
    wiki_content = read_all_wiki_content()
    if not wiki_content.strip():
        return []

    prompt = render("lint_contradiction", wiki_content=wiki_content)
    result_parts: list[str] = []

    started = _time.time()
    capture = StderrCapture()
    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                max_buffer_size=CONFIG.limits.sdk_max_buffer_size_mb * 1024 * 1024,
                system_prompt=render("lint_contradiction_system"),
                # `tools=[]` (-> --tools "") truly disables tools. `allowed_tools=[]`
                # is falsy and skipped by the SDK transport, leaving the default
                # toolset active -> agentic loop over the corpus. See the flush.py
                # fix + KNOWLEDGE "to disable tools use tools=[]".
                tools=[],
                max_turns=3,
                setting_sources=[],
                stderr=capture.callback,
            ),
        ):
            if isinstance(message, ResultMessage):
                if message.subtype == "success" and message.result:
                    result_parts.append(message.result)
    except Exception as exc:
        failure = log_sdk_failure(
            log,
            label="lint_contradiction",
            model="(default)",
            input_chars=len(prompt),
            started=started,
            capture=capture,
            exc=exc,
        )
        return [issue(
            "error", "contradiction", "(system)",
            f"LLM contradiction check failed (kind={failure.kind}, see logs)",
        )]

    result = "\n".join(result_parts)
    if "NO_ISSUES" in result:
        return []

    issues = []
    for line in result.strip().split("\n"):
        line = line.strip()
        if line.startswith("CONTRADICTION:") or line.startswith("INCONSISTENCY:"):
            issues.append(issue(
                "warning", "contradiction", "(cross-article)", line,
            ))

    return issues


# ── Report generation ────────────────────────────────────────────────

def generate_report(all_issues: list[Issue]) -> str:
    """Generate a markdown lint report."""
    errors = [i for i in all_issues if i.severity == "error"]
    warnings = [i for i in all_issues if i.severity == "warning"]
    suggestions = [i for i in all_issues if i.severity == "suggestion"]
    auto_fixable = [i for i in all_issues if i.auto_fixable]

    lines = [
        f"# Lint Report — {today_iso()}",
        "",
        f"**Total issues:** {len(all_issues)}",
        f"- Errors: {len(errors)}",
        f"- Warnings: {len(warnings)}",
        f"- Suggestions: {len(suggestions)}",
        f"- Auto-fixable: {len(auto_fixable)}",
        "",
    ]

    for severity, items, marker in [
        ("Errors", errors, "x"),
        ("Warnings", warnings, "!"),
        ("Suggestions", suggestions, "?"),
    ]:
        if items:
            lines.append(f"## {severity}")
            lines.append("")
            for i in items:
                fixable = " *(auto-fixable)*" if i.auto_fixable else ""
                lines.append(f"- **[{marker}]** `{i.file}` — {i.detail}{fixable}")
            lines.append("")

    if not all_issues:
        lines.append("All checks passed. Knowledge base is healthy.")
        lines.append("")

    return "\n".join(lines)


# ── Check registry ───────────────────────────────────────────────────

# name → check(ctx). Registration order is run/report order.
CHECKS: list[tuple[str, Callable[[LintContext], list[Issue]]]] = [
    ("Broken links", check_broken_links),
    ("Orphan pages", check_orphan_pages),
    ("Orphan sources", check_orphan_sources),
    ("Stale articles", check_stale_articles),
    ("Article type", check_article_type),
    ("QA schema", check_qa_schema),
    ("Concept domain tag", check_concept_domain_tag),
    ("Connection depth", check_connection_depth),
    ("Two-layer pages", check_two_layer_pages),
    ("Action item syntax", check_action_item_syntax),
    ("Area status", check_area_status),
    ("Daily consistency", check_daily_consistency),
    ("Sparse articles", check_sparse_articles),
    ("Facts violations", check_facts_violations),
    ("Compile role enum", check_compile_role),
    ("Source-and-final author required", check_author_required_on_source_and_final),
    ("Domain value enum", check_domain_value),
    ("Takes consistency", check_takes_consistency),
]


# ── Main ─────────────────────────────────────────────────────────────

def _lint_exit_code(errors: int, structural_only: bool) -> int:
    """Exit code for the lint run.

    `--structural-only` is the cheap piggyback path: it ran successfully and the
    findings live in the lint report + the home-screen lint probe — finding
    content issues is DATA, not a task failure, so it returns 0. (Otherwise the
    piggyback runner stamps a healthy sweep `failed:1` and false-alarms the
    dashboard — the actual lxw symptom.) Interactive full lint keeps exit 1 on
    errors so an operator / CI gate still sees a non-zero "issues present"
    signal; a non-zero from the structural path then unambiguously means lint
    itself failed to run.
    """
    if structural_only:
        return 0
    return 1 if errors > 0 else 0


async def main() -> None:
    parser = argparse.ArgumentParser(description="Lint the knowledge base")
    parser.add_argument(
        "--structural-only",
        action="store_true",
        help="Skip the LLM contradiction check (faster, free)",
    )
    args = parser.parse_args()

    log.info("Starting lint (structural_only=%s)", args.structural_only)

    ctx = build_context()
    log.info("Corpus context built: %d article(s)", len(ctx.articles))

    all_issues: list[Issue] = []

    for name, check_fn in CHECKS:
        log.info("Checking: %s...", name)
        try:
            issues = check_fn(ctx)
        except Exception as exc:  # noqa: BLE001 — one bad check must not abort the run
            log.exception("Check %r crashed: %s", name, exc)
            all_issues.append(issue(
                "error", "check_crashed", "(system)",
                f"Lint check {name!r} crashed: {exc}. See logs for traceback.",
            ))
            continue
        all_issues.extend(issues)
        log.info("  Found %d issue(s)", len(issues))

    if args.structural_only:
        log.info("Skipping: Contradictions (--structural-only)")
    else:
        log.info("Checking: Contradictions (LLM)...")
        issues = await check_contradictions()
        all_issues.extend(issues)
        log.info("  Found %d issue(s)", len(issues))

    # Generate and save report
    report = generate_report(all_issues)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORTS_DIR / f"lint-{today_iso()}.md"
    report_file.write_text(report, encoding="utf-8")
    log.info("Report saved to %s", report_file)

    # Update state (merge-under-lock — a whole-dict save here raced compile's
    # long-held state copy, last-writer-wins).
    def _stamp_lint(state: dict) -> None:
        state["last_lint"] = now_iso()

    update_state(_stamp_lint)

    # Summary
    errors = sum(1 for i in all_issues if i.severity == "error")
    warnings = sum(1 for i in all_issues if i.severity == "warning")
    suggestions = sum(1 for i in all_issues if i.severity == "suggestion")
    print(f"\nResults: {errors} errors, {warnings} warnings, {suggestions} suggestions")

    if errors > 0:
        print("\nErrors found — knowledge base needs attention!")
    sys.exit(_lint_exit_code(errors, args.structural_only))


if __name__ == "__main__":
    asyncio.run(main())
