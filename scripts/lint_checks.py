"""The structural lint checks: links, orphans, staleness, article types, the qa / concept
/ connection / entity-page / area shapes, sparse articles, the daily rollup, hard-fact
violations.

Every check is a pure function ``check(ctx) -> list[Issue]`` over the `LintContext`
(`lint_model`); `lint.CHECKS` runs them in report order. `_domain_tags` is read here —
a test patches it on this module, never on the `lint` facade.
"""

from core.config import CONFIG
from core.links import _strip_frontmatter_and_fences, link_target, resolve_link
from core.utils import extract_wikilinks, file_hash
from lint_model import Issue, LintContext, _in_folder, _read_frontmatter, issue

SPARSE_THRESHOLD = CONFIG.limits.sparse_threshold_words


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
                    issues.append(
                        issue(
                            "error",
                            "broken_link",
                            art.rel,
                            f"Broken link: [[{link}]] — target does not exist",
                            target_slug=target,
                        )
                    )
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
            issues.append(
                issue(
                    "warning",
                    "orphan_page",
                    art.rel,
                    f"Orphan page: no other articles link to [[{name}]]",
                )
            )
    return issues


def check_orphan_sources(ctx: LintContext) -> list[Issue]:
    """Find daily/raw source files that were never compiled into any article."""
    issues = []
    ingested = ctx.state.get("ingested", {})

    for source in ctx.raw_files:
        rel = str(source.relative_to(ctx.vault))
        if rel not in ingested:
            issues.append(
                issue(
                    "warning",
                    "orphan_source",
                    rel,
                    f"Uncompiled source: {rel} has not been ingested",
                )
            )
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
        stored_hash = stored.get("hash", "") if isinstance(stored, dict) else str(stored)
        current_hash = file_hash(source)
        if stored_hash != current_hash:
            issues.append(
                issue(
                    "warning",
                    "stale_article",
                    rel,
                    f"Stale: {rel} has changed since last compilation",
                )
            )
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
            issues.append(
                issue(
                    "warning",
                    "missing_type",
                    art.rel,
                    f"Missing `type:` frontmatter — expected `type: {expected}` (matches folder `{folder}/`)",
                    auto_fixable=True,
                )
            )
        elif actual != expected:
            issues.append(
                issue(
                    "warning",
                    "type_mismatch",
                    art.rel,
                    f"`type: {actual}` does not match folder `{folder}/` (expected `type: {expected}`)",
                    auto_fixable=True,
                )
            )
    return issues


# Domain tags considered "meaningful" for graph-view coloring. A qa/ note
# without any of these gets a warning so it doesn't fall into the grey
# fallback bucket. THE list is `CONFIG.graph_view.domain_tags` — there is no
# engine fallback: this module used to hardcode one operator's project names
# because the knob sat in NEVER_INJECTED and no vault could set it
# (2026-08-26). Empty list = the operator has not named their domains, so the
# rule stays quiet rather than warning against a list nobody chose.
def _domain_tags() -> tuple[str, ...]:
    cfg = getattr(CONFIG.graph_view, "domain_tags", None)
    if isinstance(cfg, list):
        return tuple(t for t in cfg if isinstance(t, str))
    return ()


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
            issues.append(
                issue(
                    "error",
                    "qa_missing_type",
                    art.rel,
                    f"qa/ note has `type: {actual}` — must be `type: qa` per schema",
                    auto_fixable=True,
                )
            )
        # 2. must appear in index.md
        stem = art.path.stem
        if f"[[qa/{stem}]]" not in ctx.index_content:
            issues.append(
                issue(
                    "warning",
                    "qa_not_in_index",
                    art.rel,
                    f"qa/{stem} is not referenced in knowledge/index.md — "
                    f"`wiki query --file-back` should have added a row",
                )
            )
        # 3. should have ≥1 domain tag (else falls into grey bucket in graph
        # view). Skipped entirely when the operator has named no domains —
        # warning "no domain tag from []" on every note would be noise, and
        # the engine has no business guessing what their domains are.
        raw_tags = art.fm.get("tags") or []
        tags = {str(t) for t in raw_tags} if isinstance(raw_tags, list) else set()
        # Strip the redundant `qa` tag — that information lives in type:
        if domain_set and not (tags & domain_set):
            issues.append(
                issue(
                    "warning",
                    "qa_no_domain_tag",
                    art.rel,
                    f"qa/ note has no domain tag from {sorted(domain_set)} — "
                    f"will render grey in graph view. Add e.g. `tags: [llm-wiki]`.",
                )
            )
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
            # Quiet when the operator has named no domains — see _domain_tags.
            if domain_set and not (tags & domain_set):
                issues.append(
                    issue(
                        "warning",
                        "concept_no_domain_tag",
                        art.rel,
                        f"{folder[:-1]} has no tag from {sorted(domain_set)} — "
                        f"will render grey in graph view. Current tags: {sorted(tags)[:6]}",
                    )
                )
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
            issues.append(
                issue(
                    "warning",
                    "connection_under_linked",
                    art.rel,
                    f"connection article cites only {len(knowledge_links)} distinct "
                    f"knowledge wikilink(s) — a connection MUST name ≥2 endpoints "
                    f"(found: {sorted(knowledge_links)})",
                )
            )

        # Rule 2: one of tension/mechanism/dependency must be present + non-empty.
        present_kinds = [
            k for k in CONNECTION_KIND_FIELDS if k in art.fm and art.fm[k] not in (None, "", [])
        ]
        if not present_kinds:
            issues.append(
                issue(
                    "warning",
                    "connection_missing_kind",
                    art.rel,
                    f"connection article missing a kind discriminator — exactly one of "
                    f"{list(CONNECTION_KIND_FIELDS)} must be present in frontmatter "
                    f"to declare whether this is a mechanism / contrast / hard-dependency",
                    auto_fixable=True,
                )
            )

        # Rule 3: body word-count ≥ floor.
        body_word_count = len(art.body.split())
        if body_word_count < min_words:
            issues.append(
                issue(
                    "warning",
                    "connection_shallow_body",
                    art.rel,
                    f"connection article body is {body_word_count} words "
                    f"(minimum {min_words}) — too short to assert a real mechanism / "
                    f"contrast / dependency beyond restating the linked concepts",
                )
            )

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
                separator_lines
                and timeline_match
                and any(pos < timeline_match.start() for pos in separator_lines)
            )

            if not has_state:
                issues.append(
                    issue(
                        "error",
                        "two_layer_missing_state",
                        art.rel,
                        f"`type: {expected_type}` article missing `## State` section "
                        f"(spec: prompts/compile_main.md Instruction 3)",
                    )
                )
            if not has_body_separator:
                issues.append(
                    issue(
                        "error",
                        "two_layer_missing_body_separator",
                        art.rel,
                        f"`type: {expected_type}` article missing the `---` separator "
                        f"between State and Timeline blocks",
                    )
                )
            if not has_timeline:
                issues.append(
                    issue(
                        "error",
                        "two_layer_missing_timeline",
                        art.rel,
                        f"`type: {expected_type}` article missing `## Timeline` section",
                    )
                )

            # Reverse-chronological check on Timeline entries
            if has_timeline:
                tail = body[timeline_match.end() :]
                # Match `- **YYYY-MM-DD**` line starts
                dates = re.findall(r"^- \*\*(\d{4}-\d{2}-\d{2})\*\*", tail, re.MULTILINE)
                for i in range(len(dates) - 1):
                    if dates[i] < dates[i + 1]:
                        issues.append(
                            issue(
                                "warning",
                                "timeline_not_reverse_chronological",
                                art.rel,
                                f"Timeline entries out of order: {dates[i]} before {dates[i + 1]} "
                                f"(newest first expected)",
                            )
                        )
                        break  # one warning per file

            # Action Items prefix sanity (deep syntax = T02)
            ai_match = re.search(r"^## Action Items\s*$", body, re.MULTILINE)
            if ai_match:
                # Scan lines until next `## ` heading or `---`
                after = body[ai_match.end() :]
                section_end = re.search(r"^(## |---\s*$)", after, re.MULTILINE)
                section = after[: section_end.start()] if section_end else after
                for raw_line in section.splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    if not (
                        line.startswith("- [ ]")
                        or line.startswith("- [x]")
                        or line.startswith("- [X]")
                    ):
                        issues.append(
                            issue(
                                "warning",
                                "action_items_malformed",
                                art.rel,
                                f"Action Items line does not start with `- [ ]` or `- [x]`: "
                                f"{line[:80]!r}",
                            )
                        )
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
            after = text[ai_match.end() :]
            section_end = re.search(r"^(## |---\s*$)", after, re.MULTILINE)
            section = after[: section_end.start()] if section_end else after

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
                issues.append(
                    issue(
                        "warning",
                        "action_item_invalid_due_date",
                        art.rel,
                        "Action Items section contains `📅` without a valid `YYYY-MM-DD` date — "
                        "Obsidian-Tasks-plugin syntax expects `📅 2026-05-20`",
                    )
                )
            if malformed_priority:
                issues.append(
                    issue(
                        "warning",
                        "action_item_malformed_priority",
                        art.rel,
                        "Action Items section contains `⏫` not bounded by whitespace — "
                        "must be standalone token, not concatenated to adjacent glyphs",
                    )
                )
            if empty_recurrence:
                issues.append(
                    issue(
                        "warning",
                        "action_item_empty_recurrence",
                        art.rel,
                        "Action Items section contains `🔁` without recurrence content — "
                        "Obsidian-Tasks-plugin syntax expects `🔁 every week` (or similar)",
                    )
                )
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
            issues.append(
                issue(
                    "error",
                    "area_missing_status",
                    art.rel,
                    f"`type: area` article missing `status:` frontmatter "
                    f"(must be one of {list(_VALID_AREA_STATUS)})",
                    auto_fixable=True,
                )
            )
            continue
        if status not in _VALID_AREA_STATUS:
            issues.append(
                issue(
                    "error",
                    "area_invalid_status",
                    art.rel,
                    f"`status: {status!r}` is not a valid area status. "
                    f"Allowed: {list(_VALID_AREA_STATUS)}.",
                )
            )
    return issues


def check_sparse_articles(ctx: LintContext) -> list[Issue]:
    """Find articles with fewer than SPARSE_THRESHOLD words (frontmatter excluded)."""
    issues = []
    for art in ctx.articles:
        if art.rel.startswith("facts/"):
            continue  # facts may legitimately be terse
        word_count = len(art.body.split())
        if word_count < SPARSE_THRESHOLD:
            issues.append(
                issue(
                    "suggestion",
                    "sparse_article",
                    art.rel,
                    f"Sparse article: {word_count} words (minimum recommended: {SPARSE_THRESHOLD})",
                )
            )
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
            issues.append(
                issue(
                    "warning",
                    "daily_missing_digest",
                    f"daily/{d}.md",
                    f"daily/{d}/ has {len(captures)} per-source capture(s) "
                    f"({', '.join(captures)}) but no root digest. Run "
                    f"`wiki agent daily-digest --var date={d}` to produce it.",
                )
            )
        else:
            # Root exists. Verify it's a real digest, not a legacy flat-daily
            # left behind by the migration script (which copies, doesn't move).
            root_fm = _read_frontmatter(daily_root / f"{d}.md")
            if root_fm.get("type") != "daily-digest":
                issues.append(
                    issue(
                        "warning",
                        "daily_root_not_digest",
                        f"daily/{d}.md",
                        f"daily/{d}.md exists alongside daily/{d}/ but has "
                        f"type={root_fm.get('type')!r} (not 'daily-digest'). "
                        "Likely a legacy flat-daily preserved by the migration. "
                        f"Run `wiki agent daily-digest --var date={d}` to "
                        "regenerate it as a proper digest, OR delete it if the "
                        "subfolder content is sufficient.",
                    )
                )
        # Unknown sources nudge
        for cap in captures:
            stem = cap[:-3] if cap.endswith(".md") else cap
            if KNOWN_SOURCES and stem not in KNOWN_SOURCES:
                issues.append(
                    issue(
                        "warning",
                        "daily_unknown_source",
                        f"daily/{d}/{cap}",
                        f"Source name {stem!r} is not in daily_capture.KNOWN_SOURCES "
                        f"({sorted(KNOWN_SOURCES)}). Rename or relocate.",
                    )
                )

    for d in root_md_dates - set(subfolder_dates):
        if d == today_iso:
            continue
        issues.append(
            issue(
                "warning",
                "daily_legacy_flat",
                f"daily/{d}.md",
                f"daily/{d}.md exists without a daily/{d}/ subfolder — this is "
                "the pre-2026-05-15 flat-daily shape. Run "
                "`uv run python scripts/migrate_daily_to_rollup.py --vault <path>` "
                "to migrate.",
            )
        )

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
                    issues.append(
                        issue(
                            "warning",
                            "fact_violation",
                            art.rel,
                            f"Article contains negation term {term!r} from hard fact `facts/{slug}` (status: {status}). Reconcile manually or via `wiki correct apply {slug}`.",
                            fact_slug=slug,
                        )
                    )
    return issues
