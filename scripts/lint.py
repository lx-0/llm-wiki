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

from config import (
    DAILY_DIR,
    KNOWLEDGE_DIR,
    RAW_DIR,
    REPORTS_DIR,
    ROOT_DIR,
    now_iso,
    today_iso,
)
from utils import (
    count_inbound_links,
    extract_wikilinks,
    file_hash,
    get_article_word_count,
    list_raw_files,
    list_wiki_articles,
    load_state,
    read_all_wiki_content,
    read_wiki_index,
    save_state,
    wiki_article_exists,
)

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("lint")

from wiki_config import CONFIG  # noqa: E402

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

def _wikilink_target_exists(link: str) -> bool:
    """Resolve an Obsidian-style wikilink target against the vault.

    Obsidian resolves `[[daily/2026-04-25.md]]` against vault root and
    `[[concepts/foo]]` against any indexed dir. We mirror that:
    in-knowledge bare names go through `wiki_article_exists`; substrate
    paths (daily/, raw/) resolve as-given against `ROOT_DIR`.
    """
    from config import ROOT_DIR
    if link.startswith(("daily/", "raw/")):
        # Substrate path — resolve verbatim against vault root.
        # Tolerate both with-suffix (`daily/X.md`) and without (`daily/X`).
        candidate = ROOT_DIR / link
        if candidate.exists():
            return True
        if not link.endswith(".md") and (ROOT_DIR / f"{link}.md").exists():
            return True
        return False
    return wiki_article_exists(link)


def check_broken_links() -> list[dict]:
    """Find wikilinks that point to non-existent targets.

    Per `prompts/compile_main.md` rule 6 (distill-don't-cite, narrowed
    2026-05-04): only `raw/memories/` is policy-banned in article bodies
    because it's a managed mirror that prunes (sync-memories.py:202).
    `daily/`, `raw/notes/`, `raw/articles/` are durable substrates and
    citable — they get the ordinary broken-link check.

    Failure modes:
      - `warning substrate_link` — body carries `[[raw/memories/...]]`
        (policy violation; run migrate_strip_substrate_links.py)
      - `error broken_link`      — wikilink target does not exist,
        regardless of which directory it points at
    """
    issues = []
    for article in list_wiki_articles():
        content = article.read_text(encoding="utf-8")
        rel = str(article.relative_to(KNOWLEDGE_DIR))
        for link in extract_wikilinks(content):
            if link.startswith("raw/memories/"):
                # Body citation of the managed-mirror subtree — violates
                # distill-don't-cite. Run scripts/migrate_strip_substrate_links.py.
                issues.append(issue(
                    "warning", "substrate_link", rel,
                    f"Substrate link in body: [[{link}]] — strip via "
                    f"`uv run python scripts/migrate_strip_substrate_links.py --apply`",
                ))
                continue
            # All other targets (knowledge/, daily/, raw/notes/, raw/articles/)
            # get the ordinary broken-link check.
            if not _wikilink_target_exists(link):
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

    for article in list_wiki_articles():
        if _is_fact(article):
            continue  # facts are authoritative; orphan-by-design
        rel = str(article.relative_to(KNOWLEDGE_DIR))
        name = rel.replace(".md", "")
        inbound = count_inbound_links(name, exclude_file=article)
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


def check_missing_backlinks() -> list[dict]:
    """Find articles that link to X but X doesn't link back."""
    issues = []
    for article in list_wiki_articles():
        if _is_fact(article):
            continue  # facts override; reciprocity not expected
        content = article.read_text(encoding="utf-8")
        rel = str(article.relative_to(KNOWLEDGE_DIR))
        source_link = rel.replace(".md", "").replace("\\", "/")

        for link in extract_wikilinks(content):
            if link.startswith("daily/") or link.startswith("raw/"):
                continue
            target_path = KNOWLEDGE_DIR / f"{link}.md"
            if target_path.exists():
                target_content = target_path.read_text(encoding="utf-8")
                if f"[[{source_link}]]" not in target_content:
                    issues.append(issue(
                        "suggestion", "missing_backlink", rel,
                        f"[[{source_link}]] links to [[{link}]] but not vice versa",
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
}


def _read_frontmatter(path: Path) -> dict:
    """Cheap YAML frontmatter parse — returns {} on no/invalid frontmatter."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end].strip("\n")
    out: dict = {}
    for line in block.splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, _, val = line.partition(":")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


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


def _read_yaml_frontmatter(path: Path) -> dict:
    """Full YAML frontmatter parse (supports lists). Returns {} on no/invalid frontmatter."""
    import yaml
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def check_facts_violations() -> list[dict]:
    """For each hard fact with negation_terms, grep all non-facts knowledge files for hits.

    Each hit is a `warning` issue: an article asserts something a hard fact negates.
    Disambiguation/clarification facts contribute no structural lint hits — those drift
    cases need the LLM contradiction check (or the agentic correct-apply processor).
    """
    issues: list[dict] = []
    if not (KNOWLEDGE_DIR / "facts").exists():
        return issues

    facts_with_terms: list[tuple[str, str, list[str]]] = []  # (slug, status, terms)
    for fact in sorted((KNOWLEDGE_DIR / "facts").glob("*.md")):
        fm = _read_yaml_frontmatter(fact)
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
        for slug, status, terms in facts_with_terms:
            for term in terms:
                if term.lower() in content_lower:
                    issues.append(issue(
                        "warning", "fact_violation", rel,
                        f"Article contains negation term {term!r} from hard fact `facts/{slug}` (status: {status}). Reconcile manually or via `wiki correct apply {slug}`.",
                    ))
    return issues


# ── LLM contradiction check ─────────────────────────────────────────

from prompts import render  # noqa: E402
from sdk_helpers import StderrCapture, log_sdk_failure  # noqa: E402
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
                system_prompt=render("lint_contradiction_system"),
                allowed_tools=[],
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
        ("Sparse articles", check_sparse_articles),
        ("Facts violations", check_facts_violations),
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
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
