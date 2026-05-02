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

def check_broken_links() -> list[dict]:
    """Find wikilinks that point to non-existent articles."""
    issues = []
    for article in list_wiki_articles():
        content = article.read_text(encoding="utf-8")
        rel = str(article.relative_to(KNOWLEDGE_DIR))
        for link in extract_wikilinks(content):
            if link.startswith("daily/") or link.startswith("raw/"):
                continue  # source references are valid
            if not wiki_article_exists(link):
                issues.append(issue(
                    "error", "broken_link", rel,
                    f"Broken link: [[{link}]] — target does not exist",
                ))
    return issues


def check_orphan_pages() -> list[dict]:
    """Find wiki articles that no other article links to."""
    issues = []
    index_content = read_wiki_index()

    for article in list_wiki_articles():
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
        if rel in ingested:
            stored_hash = ingested[rel].get("hash", "")
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


def check_sparse_articles() -> list[dict]:
    """Find articles with fewer than SPARSE_THRESHOLD words."""
    issues = []
    for article in list_wiki_articles():
        word_count = get_article_word_count(article)
        if word_count < SPARSE_THRESHOLD:
            rel = str(article.relative_to(KNOWLEDGE_DIR))
            issues.append(issue(
                "suggestion", "sparse_article", rel,
                f"Sparse article: {word_count} words (minimum recommended: {SPARSE_THRESHOLD})",
            ))
    return issues


# ── LLM contradiction check ─────────────────────────────────────────

from prompts import render  # noqa: E402


async def check_contradictions() -> list[dict]:
    """Use an LLM to find contradictions between articles."""
    wiki_content = read_all_wiki_content()
    if not wiki_content.strip():
        return []

    prompt = render("lint_contradiction", wiki_content=wiki_content)
    result_parts: list[str] = []

    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                system_prompt=render("lint_contradiction_system"),
                allowed_tools=[],
                max_turns=3,
                setting_sources=[],
            ),
        ):
            if isinstance(message, ResultMessage):
                if message.subtype == "success" and message.result:
                    result_parts.append(message.result)
    except Exception:
        log.exception("Contradiction check failed")
        return [issue("error", "contradiction", "(system)", "LLM contradiction check failed (see logs)")]

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
        ("Sparse articles", check_sparse_articles),
    ]

    for name, check_fn in checks:
        log.info("Checking: %s...", name)
        issues = check_fn()
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
