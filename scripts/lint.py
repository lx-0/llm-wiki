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

Layout (M033-S04-T07): `lint_model` holds `Issue` and the corpus model,
`lint_checks` the structural checks, `lint_schema` the frontmatter-schema checks.
This module runs them (`CHECKS`), adds the LLM contradiction check, writes the report,
and re-exports what consumers reach as `lint.X` — never a name a test patches
(`_domain_tags` is patched on `lint_checks`; `tests/test_lint_layout.py`).
"""

import os

os.environ["CLAUDE_INVOKED_BY"] = "lint"

import argparse
import asyncio
import logging
import sys
from collections.abc import Callable

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from core.config import CONFIG
from core.console import say, setup_console_logging
from core.paths import REPORTS_DIR
from core.state_store import update_state
from core.utils import now_iso, read_all_wiki_content, today_iso
from lint_checks import (
    CONNECTION_KIND_FIELDS,
    FOLDER_TO_TYPE,
    SPARSE_THRESHOLD,
    check_action_item_syntax,
    check_area_status,
    check_article_type,
    check_broken_links,
    check_concept_domain_tag,
    check_connection_depth,
    check_daily_consistency,
    check_facts_violations,
    check_orphan_pages,
    check_orphan_sources,
    check_qa_schema,
    check_sparse_articles,
    check_stale_articles,
    check_two_layer_pages,
)
from lint_model import Article, Issue, LintContext, build_context, issue
from lint_schema import (
    check_author_required_on_source_and_final,
    check_compile_role,
    check_domain_value,
    check_takes_consistency,
)

__all__ = [
    "CHECKS",
    "CONNECTION_KIND_FIELDS",
    "FOLDER_TO_TYPE",
    "SPARSE_THRESHOLD",
    "Article",
    "Issue",
    "LintContext",
    "build_context",
    "check_action_item_syntax",
    "check_area_status",
    "check_article_type",
    "check_author_required_on_source_and_final",
    "check_broken_links",
    "check_compile_role",
    "check_concept_domain_tag",
    "check_connection_depth",
    "check_contradictions",
    "check_daily_consistency",
    "check_domain_value",
    "check_facts_violations",
    "check_orphan_pages",
    "check_orphan_sources",
    "check_qa_schema",
    "check_sparse_articles",
    "check_stale_articles",
    "check_takes_consistency",
    "check_two_layer_pages",
    "generate_report",
    "issue",
    "main",
]

log = logging.getLogger("lint")


# ── LLM contradiction check ─────────────────────────────────────────

import time as _time

from core.prompts import render
from core.sdk_helpers import StderrCapture, log_sdk_failure


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
                if getattr(message, "is_error", False):
                    # SDK 0.2.x reports a refused call (bad model, API 400,
                    # client version floor) as subtype="success" + is_error
                    # with the API's text in `result`. Without this guard
                    # that text would be parsed as contradiction findings.
                    log.error(
                        "  lint_contradiction ✗ structured error (%s): %s",
                        message.subtype,
                        " ".join((message.result or "").split())[:240],
                    )
                elif message.subtype == "success" and message.result:
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
        return [
            issue(
                "error",
                "contradiction",
                "(system)",
                f"LLM contradiction check failed (kind={failure.kind}, see logs)",
            )
        ]

    result = "\n".join(result_parts)
    if "NO_ISSUES" in result:
        return []

    issues = []
    for raw_line in result.strip().split("\n"):
        line = raw_line.strip()
        if line.startswith("CONTRADICTION:") or line.startswith("INCONSISTENCY:"):
            issues.append(
                issue(
                    "warning",
                    "contradiction",
                    "(cross-article)",
                    line,
                )
            )

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
    setup_console_logging("lint")
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
        except Exception as exc:
            log.exception("Check %r crashed: %s", name, exc)
            all_issues.append(
                issue(
                    "error",
                    "check_crashed",
                    "(system)",
                    f"Lint check {name!r} crashed: {exc}. See logs for traceback.",
                )
            )
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
    say(f"\nResults: {errors} errors, {warnings} warnings, {suggestions} suggestions")

    if errors > 0:
        say("\nErrors found — knowledge base needs attention!")
    sys.exit(_lint_exit_code(errors, args.structural_only))


if __name__ == "__main__":
    asyncio.run(main())
