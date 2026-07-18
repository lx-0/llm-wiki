"""Lint the knowledge base for structural and semantic issues.

Usage:
    uv run python lint.py                    # full lint including LLM contradiction check
    uv run python lint.py --structural-only  # skip the LLM contradiction check
"""

import os
os.environ["CLAUDE_INVOKED_BY"] = "lint"

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from core import frontmatter
from core.paths import DAILY_DIR, KNOWLEDGE_DIR, RAW_DIR, REPORTS_DIR, ROOT_DIR
from core.utils import (
    build_inbound_count_map,
    extract_wikilinks,
    file_hash,
    get_article_word_count,
    list_raw_files,
    list_wiki_articles,
    load_state,
    now_iso,
    read_all_wiki_content,
    read_wiki_index,
    save_state,
    today_iso,
)
from core.links import canonical_slug, link_target, resolve_link  # noqa: E402
from core.paths import ROOT_DIR  # noqa: E402  — vault root

# ── Logging ──────────────────────────────────────────────────────────
from core.console import setup_console_logging  # noqa: E402
log = setup_console_logging("lint")

from core.config import CONFIG  # noqa: E402

SPARSE_THRESHOLD = CONFIG.limits.sparse_threshold_words


# ── Issue type ──────────────────────────────────────────────────────

def issue(severity: str, check: str, file: str, detail: str, auto_fixable: bool = False) -> dict:
    """Create a structured issue dict (matches Cole's pattern)."""
    return {
        "severity": severity,  # error, warning, suggestion
        "check": check,
        "file": file,
        "detail": detail,
        "auto_fixable": auto_fixable,
    }


# ── Structural checks ───────────────────────────────────────────────

def _wikilink_target_exists(link: str, source: Path) -> bool:
    """Resolve an Obsidian-style wikilink target against the vault.

    A link in a markdown file is relative to that file (the relativize-wikilinks
    convention). `core.links.resolve_link` is the single resolver: it tries the
    target relative to ``source``, the vault root, and ``<vault>/knowledge/``.
    """
    return resolve_link(link_target(link), source, ROOT_DIR) is not None


def check_broken_links() -> list[dict]:
    """Find wikilinks that point to non-existent targets.

    All targets (knowledge/, daily/, raw/notes/, raw/articles/, …) get
    the ordinary broken-link check — no per-subtree exceptions.
    """
    issues = []
    for article in list_wiki_articles():
        content = article.read_text(encoding="utf-8")
        rel = str(article.relative_to(KNOWLEDGE_DIR))
        for link in extract_wikilinks(content):
            if not _wikilink_target_exists(link, article):
                issues.append(issue(
                    "error", "broken_link", rel,
                    f"Broken link: [[{link}]] — target does not exist",
                ))
    return issues


def _is_fact(article: Path) -> bool:
    """True if the article lives under knowledge/facts/."""
    try:
        rel = article.relative_to(KNOWLEDGE_DIR)
    except ValueError:
        return False
    return rel.parts and rel.parts[0] == "facts"


def check_orphan_pages() -> list[dict]:
    """Find wiki articles that no other article links to."""
    issues = []
    index_content = read_wiki_index()
    # One O(N) pass for ALL targets, replacing the per-article
    # count_inbound_links() that made this O(N²) and hung the lint ~99 min on
    # 1700 articles (incident 2026-05-30, KNOWLEDGE.md). Behaviour-identical:
    # inbound count = sources of `name` minus self (parity-tested against the
    # count_inbound_links oracle).
    inbound_map = build_inbound_count_map()

    for article in list_wiki_articles():
        if _is_fact(article):
            continue  # facts are authoritative; orphan-by-design
        rel = str(article.relative_to(KNOWLEDGE_DIR))
        name = rel.replace(".md", "")
        inbound = len(inbound_map.get(name, set()) - {str(article)})
        in_index = f"[[{name}]]" in index_content

        if inbound == 0 and not in_index:
            issues.append(issue(
                "warning", "orphan_page", rel,
                f"Orphan page: no other articles link to [[{name}]]",
            ))
    return issues


def check_orphan_sources() -> list[dict]:
    """Find daily/raw source files that were never compiled into any article."""
    issues = []
    state = load_state()
    ingested = state.get("ingested", {})

    for source in list_raw_files():
        rel = str(source.relative_to(ROOT_DIR))
        if rel not in ingested:
            issues.append(issue(
                "warning", "orphan_source", rel,
                f"Uncompiled source: {rel} has not been ingested",
            ))
    return issues


def check_stale_articles() -> list[dict]:
    """Find articles whose source files have changed since last compilation."""
    issues = []
    state = load_state()
    ingested = state.get("ingested", {})

    for source in list_raw_files():
        rel = str(source.relative_to(ROOT_DIR))
        if rel not in ingested:
            continue
        # state.ingested[rel] is a hash string (compile.py:492 writes file_hash(source) directly).
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


def _outgoing_knowledge_slugs(article: Path) -> set[str]:
    """Canonical knowledge-slugs an article links to, links resolved relative
    to the article. Substrate (daily/raw) and dangling links are dropped."""
    try:
        content = article.read_text(encoding="utf-8")
    except OSError:
        return set()
    slugs: set[str] = set()
    for link in extract_wikilinks(content):
        resolved = resolve_link(link_target(link), article, ROOT_DIR)
        if resolved is None:
            continue
        slug = canonical_slug(resolved, KNOWLEDGE_DIR)
        if slug:
            slugs.add(slug)
    return slugs


def check_missing_backlinks() -> list[dict]:
    """Find articles that link to X but X doesn't link back."""
    issues = []
    cache: dict[Path, set[str]] = {}
    for article in list_wiki_articles():
        if _is_fact(article):
            continue  # facts override; reciprocity not expected
        rel = str(article.relative_to(KNOWLEDGE_DIR))
        src_slug = canonical_slug(article, KNOWLEDGE_DIR)
        if src_slug is None:
            continue

        for link in extract_wikilinks(article.read_text(encoding="utf-8")):
            resolved = resolve_link(link_target(link), article, ROOT_DIR)
            if resolved is None:
                continue
            tgt_slug = canonical_slug(resolved, KNOWLEDGE_DIR)
            if tgt_slug is None or tgt_slug == src_slug:
                continue  # substrate citation or self-link
            back = cache.get(resolved)
            if back is None:
                back = _outgoing_knowledge_slugs(resolved)
                cache[resolved] = back
            if src_slug not in back:
                issues.append(issue(
                    "suggestion", "missing_backlink", rel,
                    f"[[{src_slug}]] links to [[{tgt_slug}]] but not vice versa",
                    auto_fixable=True,
                ))
    return issues


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
    YAML types (lists, bools); pre-C03 lint carried TWO parsers (a naive
    line-splitter and a real-YAML one) with different tolerance, arbitrarily
    distributed across checks."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return frontmatter.parse(text)[0]


def check_article_type() -> list[dict]:
    """Verify every knowledge article carries `type:` and that it matches its folder."""
    issues = []
    for article in list_wiki_articles():
        rel = str(article.relative_to(KNOWLEDGE_DIR))
        if article.name in ("index.md", "log.md"):
            continue
        # First path segment under knowledge/ is the substrate folder.
        parts = rel.split("/")
        if len(parts) < 2:
            continue  # top-level file other than index/log — not a typed article
        folder = parts[0]
        expected = FOLDER_TO_TYPE.get(folder)
        if expected is None:
            continue  # unknown folder — let other checks handle it
        fm = _read_frontmatter(article)
        actual = fm.get("type")
        if not actual:
            issues.append(issue(
                "warning", "missing_type", rel,
                f"Missing `type:` frontmatter — expected `type: {expected}` (matches folder `{folder}/`)",
                auto_fixable=True,
            ))
        elif actual != expected:
            issues.append(issue(
                "warning", "type_mismatch", rel,
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


def check_qa_schema() -> list[dict]:
    """Verify each knowledge/qa/ note has type:qa, an index row, and ≥1 domain tag.

    qa/ notes are written by `wiki query --file-back` via the Claude SDK. The
    prompt instructs three follow-up steps (frontmatter type, index row, log
    entry) but historically the agent sometimes reports success while skipping
    one. This check catches that drift.
    """
    issues = []
    qa_dir = KNOWLEDGE_DIR / "qa"
    if not qa_dir.exists():
        return issues
    index_content = read_wiki_index()
    domain_set = set(_domain_tags())
    for article in sorted(qa_dir.glob("*.md")):
        if article.name in ("index.md", "log.md"):
            continue
        rel = str(article.relative_to(KNOWLEDGE_DIR))
        fm = _read_frontmatter(article)
        # 1. type: qa required
        if fm.get("type") != "qa":
            actual = fm.get("type") or "(missing)"
            issues.append(issue(
                "error", "qa_missing_type", rel,
                f"qa/ note has `type: {actual}` — must be `type: qa` per schema",
                auto_fixable=True,
            ))
        # 2. must appear in index.md
        stem = article.stem
        if f"[[qa/{stem}]]" not in index_content:
            issues.append(issue(
                "warning", "qa_not_in_index", rel,
                f"qa/{stem} is not referenced in knowledge/index.md — "
                f"`wiki query --file-back` should have added a row",
            ))
        # 3. should have ≥1 domain tag (else falls into grey bucket in graph view)
        raw_tags = fm.get("tags") or []
        tags = set(raw_tags) if isinstance(raw_tags, list) else set()
        # Strip the redundant `qa` tag — that information lives in type:
        if not (tags & domain_set):
            issues.append(issue(
                "warning", "qa_no_domain_tag", rel,
                f"qa/ note has no domain tag from {sorted(domain_set)} — "
                f"will render grey in graph view. Add e.g. `tags: [llm-wiki]`.",
            ))
    return issues


def check_concept_domain_tag() -> list[dict]:
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
        folder_dir = KNOWLEDGE_DIR / folder
        if not folder_dir.exists():
            continue
        for article in sorted(folder_dir.glob("*.md")):
            if article.name in ("index.md", "log.md"):
                continue
            rel = str(article.relative_to(KNOWLEDGE_DIR))
            fm = _read_frontmatter(article)
            raw_tags = fm.get("tags") or []
            tags = set(raw_tags) if isinstance(raw_tags, list) else set()
            if not (tags & domain_set):
                issues.append(issue(
                    "warning", "concept_no_domain_tag", rel,
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


def check_connection_depth() -> list[dict]:
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
    issues: list[dict] = []
    connections_dir = KNOWLEDGE_DIR / "connections"
    if not connections_dir.exists():
        return issues

    min_words = CONFIG.limits.connection_min_words

    for article in sorted(connections_dir.glob("*.md")):
        if article.name in ("index.md", "log.md"):
            continue
        rel = str(article.relative_to(KNOWLEDGE_DIR))
        try:
            text = article.read_text(encoding="utf-8")
        except OSError:
            continue

        fm = _read_frontmatter(article)

        # Strip frontmatter for body-level checks (single grammar, C03)
        body = frontmatter.split_fence(text)[1]

        # Rule 1: ≥2 distinct knowledge-tree wikilinks. Endpoint cardinality is
        # a structural property, not an existence one (broken_link owns that),
        # so count lexically without resolving to disk. Substrate citations
        # (daily/raw) are excluded regardless of relative depth — strip any
        # leading `./` / `../` before testing the prefix (`../../daily/…`).
        knowledge_links: set[str] = set()
        for link in extract_wikilinks(body):
            target = link_target(link)
            if target.lstrip("./").startswith(("daily/", "raw/")):
                continue
            knowledge_links.add(target)
        if len(knowledge_links) < 2:
            issues.append(issue(
                "warning", "connection_under_linked", rel,
                f"connection article cites only {len(knowledge_links)} distinct "
                f"knowledge wikilink(s) — a connection MUST name ≥2 endpoints "
                f"(found: {sorted(knowledge_links)})",
            ))

        # Rule 2: one of tension/mechanism/dependency must be present + non-empty.
        present_kinds = [
            k for k in CONNECTION_KIND_FIELDS
            if k in fm and fm[k] not in (None, "", [])
        ]
        if not present_kinds:
            issues.append(issue(
                "warning", "connection_missing_kind", rel,
                f"connection article missing a kind discriminator — exactly one of "
                f"{list(CONNECTION_KIND_FIELDS)} must be present in frontmatter "
                f"to declare whether this is a mechanism / contrast / hard-dependency",
                auto_fixable=True,
            ))

        # Rule 3: body word-count ≥ floor.
        body_word_count = len(body.split())
        if body_word_count < min_words:
            issues.append(issue(
                "warning", "connection_shallow_body", rel,
                f"connection article body is {body_word_count} words "
                f"(minimum {min_words}) — too short to assert a real mechanism / "
                f"contrast / dependency beyond restating the linked concepts",
            ))

    return issues


def check_two_layer_pages() -> list[dict]:
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
    issues: list[dict] = []
    entity_folders = (("people", "person"), ("projects", "project"))
    for folder, expected_type in entity_folders:
        folder_path = KNOWLEDGE_DIR / folder
        if not folder_path.exists():
            continue
        for article in sorted(folder_path.glob("*.md")):
            if article.name in ("index.md", "log.md"):
                continue
            rel = str(article.relative_to(KNOWLEDGE_DIR))
            fm = _read_frontmatter(article)
            if fm.get("type") != expected_type:
                # Type-mismatch is caught by check_article_type; don't double-report
                continue

            text = article.read_text(encoding="utf-8")
            # Strip frontmatter so we only inspect the body (single grammar, C03)
            body = frontmatter.split_fence(text)[1]

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
                    "error", "two_layer_missing_state", rel,
                    f"`type: {expected_type}` article missing `## State` section "
                    f"(spec: prompts/compile_main.md Instruction 3)",
                ))
            if not has_body_separator:
                issues.append(issue(
                    "error", "two_layer_missing_body_separator", rel,
                    f"`type: {expected_type}` article missing the `---` separator "
                    f"between State and Timeline blocks",
                ))
            if not has_timeline:
                issues.append(issue(
                    "error", "two_layer_missing_timeline", rel,
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
                            "warning", "timeline_not_reverse_chronological", rel,
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
                            "warning", "action_items_malformed", rel,
                            f"Action Items line does not start with `- [ ]` or `- [x]`: "
                            f"{line[:80]!r}",
                        ))
                        break  # one warning per file
    return issues


def check_action_item_syntax() -> list[dict]:
    """Validate Obsidian-Tasks-plugin syntax inside `## Action Items` sections
    of entity pages (knowledge/people/ + knowledge/projects/).

    T01's `check_two_layer_pages` validates the `- [ ]` / `- [x]` prefix.
    This check goes deeper: 📅 due-date format, ⏫ priority placement, 🔁
    recurrence content. All issues are warnings (quality nudges, not
    structural breaks). One issue per file per rule.
    """
    import re
    issues: list[dict] = []
    entity_folders = (("people", "person"), ("projects", "project"))
    DATE_RE = re.compile(r"📅 (\d{4}-\d{2}-\d{2})(?:\s|$)")
    DATE_PREFIX_RE = re.compile(r"📅 ")
    PRIORITY_RE = re.compile(r"(?:^|\s)⏫(?:\s|$)")
    PRIORITY_PREFIX_RE = re.compile(r"⏫")
    RECURRENCE_RE = re.compile(r"🔁 \S")
    RECURRENCE_PREFIX_RE = re.compile(r"🔁(?:\s|$)")
    for folder, expected_type in entity_folders:
        folder_path = KNOWLEDGE_DIR / folder
        if not folder_path.exists():
            continue
        for article in sorted(folder_path.glob("*.md")):
            if article.name in ("index.md", "log.md"):
                continue
            rel = str(article.relative_to(KNOWLEDGE_DIR))
            fm = _read_frontmatter(article)
            if fm.get("type") != expected_type:
                continue
            text = article.read_text(encoding="utf-8")
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
                    "warning", "action_item_invalid_due_date", rel,
                    "Action Items section contains `📅` without a valid `YYYY-MM-DD` date — "
                    "Obsidian-Tasks-plugin syntax expects `📅 2026-05-20`",
                ))
            if malformed_priority:
                issues.append(issue(
                    "warning", "action_item_malformed_priority", rel,
                    "Action Items section contains `⏫` not bounded by whitespace — "
                    "must be standalone token, not concatenated to adjacent glyphs",
                ))
            if empty_recurrence:
                issues.append(issue(
                    "warning", "action_item_empty_recurrence", rel,
                    "Action Items section contains `🔁` without recurrence content — "
                    "Obsidian-Tasks-plugin syntax expects `🔁 every week` (or similar)",
                ))
    return issues


_VALID_AREA_STATUS = ("active", "dormant", "retired")


def check_area_status() -> list[dict]:
    """Validate `status:` frontmatter on `knowledge/areas/` pages.

    Areas (`type: area`) are ongoing responsibilities; they carry a
    `status:` field that must be one of `active | dormant | retired`
    (distinct from project status — areas don't `plan` or `done`).
    Missing status is an error; an unknown enum value is also an error.
    """
    issues: list[dict] = []
    areas_dir = KNOWLEDGE_DIR / "areas"
    if not areas_dir.exists():
        return issues
    for article in sorted(areas_dir.glob("*.md")):
        if article.name in ("index.md", "log.md"):
            continue
        rel = str(article.relative_to(KNOWLEDGE_DIR))
        fm = _read_frontmatter(article)
        if fm.get("type") != "area":
            # type mismatch handled by check_article_type; don't double-report
            continue
        status = fm.get("status")
        if not status:
            issues.append(issue(
                "error", "area_missing_status", rel,
                f"`type: area` article missing `status:` frontmatter "
                f"(must be one of {list(_VALID_AREA_STATUS)})",
                auto_fixable=True,
            ))
            continue
        if status not in _VALID_AREA_STATUS:
            issues.append(issue(
                "error", "area_invalid_status", rel,
                f"`status: {status!r}` is not a valid area status. "
                f"Allowed: {list(_VALID_AREA_STATUS)}.",
            ))
    return issues


def check_sparse_articles() -> list[dict]:
    """Find articles with fewer than SPARSE_THRESHOLD words."""
    issues = []
    for article in list_wiki_articles():
        if _is_fact(article):
            continue  # facts may legitimately be terse
        word_count = get_article_word_count(article)
        if word_count < SPARSE_THRESHOLD:
            rel = str(article.relative_to(KNOWLEDGE_DIR))
            issues.append(issue(
                "suggestion", "sparse_article", rel,
                f"Sparse article: {word_count} words (minimum recommended: {SPARSE_THRESHOLD})",
            ))
    return issues


def check_daily_consistency() -> list[dict]:
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
    issues: list[dict] = []
    daily_root = ROOT_DIR / "daily"
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


def check_facts_violations() -> list[dict]:
    """For each hard fact with negation_terms, grep all non-facts knowledge files for hits.

    Each hit is a `warning` issue: an article asserts something a hard fact negates.
    Disambiguation/clarification facts contribute no structural lint hits — those drift
    cases need the LLM contradiction check (or the agentic correct-apply processor).
    An article already annotated `status: superseded` by the fact is not re-flagged.
    """
    issues: list[dict] = []
    if not (KNOWLEDGE_DIR / "facts").exists():
        return issues

    facts_with_terms: list[tuple[str, str, list[str]]] = []  # (slug, status, terms)
    for fact in sorted((KNOWLEDGE_DIR / "facts").glob("*.md")):
        fm = _read_frontmatter(fact)
        terms = fm.get("negation_terms") or []
        if not isinstance(terms, list):
            continue
        terms = [t for t in terms if isinstance(t, str) and t.strip()]
        if not terms:
            continue
        status = str(fm.get("status", "negation"))
        facts_with_terms.append((fact.stem, status, terms))

    if not facts_with_terms:
        return issues

    for article in list_wiki_articles():
        if _is_fact(article):
            continue
        rel = str(article.relative_to(KNOWLEDGE_DIR))
        try:
            content_lower = article.read_text(encoding="utf-8").lower()
        except OSError:
            continue
        art_fm = _read_frontmatter(article)
        for slug, status, terms in facts_with_terms:
            if _superseded_by_fact(art_fm, slug):
                continue  # already annotated as superseded by this fact
            for term in terms:
                if term.lower() in content_lower:
                    issues.append(issue(
                        "warning", "fact_violation", rel,
                        f"Article contains negation term {term!r} from hard fact `facts/{slug}` (status: {status}). Reconcile manually or via `wiki correct apply {slug}`.",
                    ))
    return issues


# ── Takes substrate (M011) ──────────────────────────────────────────

import re as _re_takes

_TAKE_LINE_RE = _re_takes.compile(
    r"^- \*\*\d{4}-\d{2}-\d{2}\*\* \[(?:low|medium|high)\] · `[^`]+` — .+$"
)


def check_takes_consistency() -> list[dict]:
    """Validate `knowledge/takes/*.md` shape (M011, v1 — shape-only).

    Per-file checks:
      - Frontmatter `type: takes` is present.
      - Frontmatter `holder:` is present (non-empty).
      - Every body line that starts with `- **` matches the canonical
        take regex; malformed lines surface as warnings.
    """
    issues: list[dict] = []
    takes_dir = KNOWLEDGE_DIR / "takes"
    if not takes_dir.exists():
        return issues

    for md in sorted(takes_dir.glob("*.md")):
        rel = str(md.relative_to(KNOWLEDGE_DIR))
        fm = _read_frontmatter(md)
        if fm.get("type") != "takes":
            issues.append(issue(
                "error", "takes_frontmatter_type", rel,
                "Takes file must carry `type: takes` in frontmatter.",
            ))
        holder = fm.get("holder")
        if not holder or not str(holder).strip():
            issues.append(issue(
                "error", "takes_frontmatter_holder_missing", rel,
                "Takes file must carry a non-empty `holder:` field in frontmatter.",
            ))
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        body = frontmatter.split_fence(text)[1]
        for lineno, line in enumerate(body.splitlines(), start=1):
            if not line.startswith("- **"):
                continue
            if not _TAKE_LINE_RE.match(line):
                issues.append(issue(
                    "warning", "takes_line_malformed", rel,
                    f"Line {lineno} does not match canonical take shape: {line[:120]}",
                ))
    return issues


# ── compile_role enum validation (M007-S01-T03) ─────────────────────

from core.compile_role import VALID_ROLES as _COMPILE_ROLE_VALID  # noqa: E402


def check_domain_value() -> list[dict]:
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
    issues: list[dict] = []
    domains_cfg = getattr(CONFIG.personal, "domains", None) or []
    valid = {d for d in domains_cfg if isinstance(d, str)}
    if not valid:
        return issues
    for article in list_wiki_articles():
        fm = _read_frontmatter(article)
        value = fm.get("domain")
        if value is None:
            continue
        if not isinstance(value, str) or value not in valid:
            rel = str(article.relative_to(KNOWLEDGE_DIR))
            allowed = ", ".join(sorted(valid))
            issues.append(issue(
                "warning", "domain_invalid_value", rel,
                f"`domain: {value!r}` is not in CONFIG.personal.domains "
                f"({allowed}). Fix the value, or add it to config.yaml "
                f"under `personal.domains:`.",
            ))
    return issues


def check_compile_role() -> list[dict]:
    """Reject frontmatter `compile_role:` values not in VALID_ROLES.

    Walks every `.md` under raw/, daily/, knowledge/, inbox/. Files that omit
    `compile_role:` get no issue (default-by-location inference handles them
    at compile time per `scripts.core.compile_role.infer_compile_role`).

    Cross-location-move warning (slice plan mentions detecting renames across
    top-level boundaries without explicit override) is deferred — needs
    git-history walk, tracked as follow-up.
    """
    issues: list[dict] = []
    inbox_dir = ROOT_DIR / "inbox"
    roots = [RAW_DIR, DAILY_DIR, KNOWLEDGE_DIR, inbox_dir]
    for root in roots:
        if not root.exists():
            continue
        for md in root.rglob("*.md"):
            fm = _read_frontmatter(md)
            role = fm.get("compile_role")
            if role is None:
                continue
            if role not in _COMPILE_ROLE_VALID:
                rel = str(md.relative_to(ROOT_DIR))
                valid_list = ", ".join(sorted(_COMPILE_ROLE_VALID))
                issues.append(issue(
                    "error", "compile_role_invalid", rel,
                    f"`compile_role: {role!r}` is not a valid value. "
                    f"Allowed: {valid_list}.",
                ))
    return issues


def check_author_required_on_source_and_final() -> list[dict]:
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
    issues: list[dict] = []
    inbox_dir = ROOT_DIR / "inbox"
    roots = [RAW_DIR, DAILY_DIR, KNOWLEDGE_DIR, inbox_dir]
    for root in roots:
        if not root.exists():
            continue
        for md in root.rglob("*.md"):
            fm = _read_frontmatter(md)
            if fm.get("compile_role") != "source-and-final":
                continue
            if not fm.get("author"):
                rel = str(md.relative_to(ROOT_DIR))
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


async def check_contradictions() -> list[dict]:
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

def generate_report(all_issues: list[dict]) -> str:
    """Generate a markdown lint report."""
    errors = [i for i in all_issues if i["severity"] == "error"]
    warnings = [i for i in all_issues if i["severity"] == "warning"]
    suggestions = [i for i in all_issues if i["severity"] == "suggestion"]
    auto_fixable = [i for i in all_issues if i.get("auto_fixable")]

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
                fixable = " *(auto-fixable)*" if i.get("auto_fixable") else ""
                lines.append(f"- **[{marker}]** `{i['file']}` — {i['detail']}{fixable}")
            lines.append("")

    if not all_issues:
        lines.append("All checks passed. Knowledge base is healthy.")
        lines.append("")

    return "\n".join(lines)


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

    all_issues: list[dict] = []

    checks = [
        ("Broken links", check_broken_links),
        ("Orphan pages", check_orphan_pages),
        ("Orphan sources", check_orphan_sources),
        ("Stale articles", check_stale_articles),
        ("Missing backlinks", check_missing_backlinks),
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

    for name, check_fn in checks:
        log.info("Checking: %s...", name)
        try:
            issues = check_fn()
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

    # Update state
    state = load_state()
    state["last_lint"] = now_iso()
    save_state(state)

    # Summary
    errors = sum(1 for i in all_issues if i["severity"] == "error")
    warnings = sum(1 for i in all_issues if i["severity"] == "warning")
    suggestions = sum(1 for i in all_issues if i["severity"] == "suggestion")
    print(f"\nResults: {errors} errors, {warnings} warnings, {suggestions} suggestions")

    if errors > 0:
        print("\nErrors found — knowledge base needs attention!")
    sys.exit(_lint_exit_code(errors, args.structural_only))


if __name__ == "__main__":
    asyncio.run(main())
