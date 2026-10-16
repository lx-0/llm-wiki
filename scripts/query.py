"""Query the knowledge base with natural language.

Usage:
    uv run python query.py "What do I know about X?"
    uv run python query.py "What do I know about X?" --brief
    uv run python query.py "What do I know about X?" --brief --json
    uv run python query.py "What do I know about X?" --file-back
"""

import os

os.environ["CLAUDE_INVOKED_BY"] = "query"

import argparse
import asyncio
import json
import logging
import sys

from claude_agent_sdk import query

from core.config import CONFIG
from core.console import say, setup_console_logging
from core.paths import KNOWLEDGE_DIR, LOG_FILE, QA_DIR, ROOT_DIR
from core.prompts import render
from core.sdk_helpers import (
    PromptTooLargeError,
    SdkCallSpec,
    SdkRunResult,
    WriteScope,
    assert_prompt_within_budget,
    run_sdk_query,
)
from core.state_store import update_state
from core.utils import (
    now_iso,
    read_hard_facts,
    read_wiki_index_compact,
    slugify,
    today_iso,
)

log = logging.getLogger("query")

# ── Query prompt ─────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query the knowledge base")
    parser.add_argument("question", type=str, help="Your question")
    parser.add_argument(
        "--file-back",
        action="store_true",
        help="Save the answer as a Q&A article in the wiki (implies full mode)",
    )
    parser.add_argument(
        "--brief",
        action="store_true",
        help="Short bullet answer instead of a full essay (incompatible with --file-back)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "Machine-readable output: print a {question, answer, input_tokens, "
            "output_tokens} JSON object instead of the raw answer (desktop app / "
            "agents; incompatible with --file-back)"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --file-back: overwrite an existing qa/ note that matches the question slug",
    )
    parser.add_argument(
        "--include-final-only",
        action="store_true",
        help=(
            "Include articles marked compile_role: final-only (archived, "
            "hand-curated) in the answer. Default: skip them (they're hidden "
            "from active surfaces). Use when you specifically want to query "
            "archived knowledge. (M007-S03-T03)"
        ),
    )
    parser.add_argument(
        "--domain",
        type=str,
        default=None,
        help=(
            "Restrict the answer to articles whose frontmatter `domain:` "
            "matches this value (e.g. company | personal | ai | meta). "
            "Untagged articles are excluded from the filtered set. "
            "Configurable list lives in CONFIG.personal.domains. (M013)"
        ),
    )
    return parser


def _validate_flags(args: argparse.Namespace) -> None:
    """Exit 2 on a mode conflict (`--brief` / `--json` with `--file-back`) or a
    `--domain` outside `CONFIG.personal.domains`."""
    if args.brief and args.file_back:
        log.error(
            "--brief and --file-back are mutually exclusive — brief mode answers in-line only"
        )
        sys.exit(2)
    if args.json and args.file_back:
        log.error("--json and --file-back are mutually exclusive — JSON mode answers in-line only")
        sys.exit(2)

    domain = args.domain
    # M013: validate against the configured enum early. Unknown values would
    # otherwise produce an empty answer (the LLM filter matches nothing) with
    # no clear operator signal. An empty `personal.domains` disables the
    # feature — accept any value without validating.
    domains_cfg = getattr(CONFIG.personal, "domains", None) or []
    valid_domains = [d for d in domains_cfg if isinstance(d, str)]
    if domain is not None and valid_domains and domain not in valid_domains:
        log.error(
            "--domain %r is not in CONFIG.personal.domains (%s). "
            "Add it to config.yaml under `personal.domains:` or pick one of "
            "the configured values.",
            domain,
            ", ".join(valid_domains),
        )
        sys.exit(2)


def _compile_role_note(include_final_only: bool) -> str:
    """compile_role filter (M007-S03-T03). By default, instruct the LLM to
    skip articles with compile_role: final-only frontmatter — they're
    archived hand-curated reference, hidden from active surfaces. The
    --include-final-only flag re-enables them for queries that
    specifically want archived knowledge."""
    if include_final_only:
        return (
            "\n\n## compile_role filter\n\n"
            "Include articles regardless of compile_role (operator requested "
            "via --include-final-only). Treat final-only and source-and-final "
            "alongside source-only/compile-output articles.\n"
        )
    return (
        "\n\n## compile_role filter\n\n"
        "If any article you find has frontmatter `compile_role: final-only`, "
        "SKIP it — it's archived hand-curated content the operator chose to "
        "hide from active queries. Mention in your answer ONLY if directly "
        "asked about archives or if no non-archived material answers the "
        "question. Source-only and source-and-final articles are in-scope.\n"
    )


def _domain_note(domain: str | None) -> str:
    """M013: domain filter. When `--domain <value>` is provided, instruct the
    LLM to restrict its answer to articles whose frontmatter `domain:`
    matches the requested value. Untagged articles are excluded from the
    filtered set (operator opted into a filter — silent inclusion would
    mask the lack of tagging). No-op ("") when --domain is not provided."""
    if domain is None:
        return ""
    return (
        "\n\n## domain filter\n\n"
        f"Restrict your answer to articles whose frontmatter `domain:` "
        f"value is exactly `{domain}`. Read the frontmatter (top YAML "
        f"block) of any candidate article before citing it. Articles "
        f"without `domain:` set, or with a different value, are out of "
        f"scope for this query — skip them. If no in-scope article "
        f"answers the question, say so explicitly rather than falling "
        f"back to untagged content.\n"
    )


def _build_prompt(
    args: argparse.Namespace, *, index_md: str, facts_md: str
) -> tuple[str, list[str]]:
    """The mode's template and tool set; `--file-back` adds Write/Edit behind the
    qa/ dedup guard (exit 3 unless `--force`)."""
    question = args.question
    if args.file_back:
        QA_DIR.mkdir(parents=True, exist_ok=True)
        # Dedup guard: refuse to overwrite an existing qa/ note unless --force.
        # Match by exact slug; near-duplicates are still possible but cheap
        # protection against accidental double-runs of the same question.
        candidate_slug = slugify(question)[:80]  # cap length to match write
        existing = list(QA_DIR.glob(f"{candidate_slug}*.md"))
        if existing and not args.force:
            log.error(
                "qa/ already has %d note(s) matching slug `%s*.md` (%s). "
                "Re-run with --force to overwrite, or rephrase the question for a distinct slug.",
                len(existing),
                candidate_slug,
                ", ".join(p.name for p in existing[:3]),
            )
            sys.exit(3)
        prompt = render(
            "query_file_back",
            index_md=index_md,
            facts_md=facts_md,
            question=question,
            today=today_iso(),
            now=now_iso(),
        )
        allowed_tools = ["Read", "Glob", "Grep", "Write", "Edit"]
    elif args.brief:
        prompt = render(
            "query_brief",
            index_md=index_md,
            facts_md=facts_md,
            question=question,
        )
        allowed_tools = ["Read", "Glob", "Grep"]
    else:
        prompt = render(
            "query_main",
            index_md=index_md,
            facts_md=facts_md,
            question=question,
        )
        allowed_tools = ["Read", "Glob", "Grep"]
    return prompt, allowed_tools


def _print_answer(result: SdkRunResult, question: str, *, as_json: bool) -> None:
    """Print the answer. --json is the machine-readable seam (desktop app /
    agents; same posture as `wiki doctor --json`) — consumers parse this
    payload instead of scraping the banner + prose off stdout."""
    if as_json:
        say(
            json.dumps(
                {
                    "question": question,
                    "answer": result.result_text,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                },
                indent=2,
            )
        )
    else:
        say("\n" + result.result_text)


def _bump_query_counters(state: dict) -> None:
    """Merged under the state lock so a compile running in parallel can't
    clobber these counters with its own long-held copy (and vice versa).
    No dollar accumulation: token accounting in usage.json/LEDGER is the
    metering surface (DECISIONS 2026-05-23). Queries were the last writer
    feeding the retired `total_cost` key, which made the number drift
    upward from queries alone while compile's spend vanished."""
    state["query_count"] = state.get("query_count", 0) + 1
    state["last_query"] = now_iso()


# ── Main ─────────────────────────────────────────────────────────────


async def main() -> None:
    """The phases: parse + validate → the compact index + the hard facts with the
    compile-role / domain notes → the mode's prompt → the budget pre-flight → the
    query agent → the answer → the counters."""
    setup_console_logging("query")
    args = _build_parser().parse_args()
    _validate_flags(args)
    log.info(
        "Query: %s (brief=%s, file_back=%s, include_final_only=%s, domain=%s)",
        args.question,
        args.brief,
        args.file_back,
        args.include_final_only,
        args.domain,
    )

    # Embed only the compact article index (path + date); the agent pulls
    # full article bodies on demand via Read/Grep/Glob. Embedding every
    # article body here overflowed the model's context window once the
    # vault grew large (4.4 MB / >1M tokens on the 850-article lxw vault).
    index_md = read_wiki_index_compact()
    facts_md = (
        read_hard_facts() + _compile_role_note(args.include_final_only) + _domain_note(args.domain)
    )
    prompt, allowed_tools = _build_prompt(args, index_md=index_md, facts_md=facts_md)

    # Pre-flight: reject a corpus-sized prompt before the SDK call. Without
    # this guard, an oversized prompt dies inside the bundled CLI with an
    # opaque exit-1 / empty-stderr kind=unknown failure (see KNOWLEDGE.md).
    try:
        assert_prompt_within_budget(
            len(prompt),
            CONFIG.limits.query_max_prompt_chars,
            label="query",
            breakdown={"compact index": len(index_md), "hard facts": len(facts_md)},
        )
    except PromptTooLargeError as exc:
        log.error("%s", exc)
        sys.exit(1)

    # Run the query agent. The harness owns mechanics (stderr capture,
    # usage extraction, failure diagnostics) AND records this call's
    # tokens to the usage LEDGER — query.py previously never recorded.
    #
    # Write authority follows AGENTS.md's HARD substrate rule (M034-S06-T07; the agent reads
    # compiled substrate, which carries change-descriptions an agent may act on). The base
    # toolset is exactly the mode's tools, so a read mode has no Write/Edit and no mode has
    # Bash. `--file-back` writes through a PreToolUse path scope on what its prompt asks for
    # — the Q&A article, the index row, the operations log — with the vault's project
    # settings. Until 0.8.1 every mode ran `acceptEdits` with the default toolset: any write
    # anywhere in the vault went through unasked.
    writes = args.file_back
    result = await run_sdk_query(
        prompt,
        SdkCallSpec(
            label="query",
            logger=log,
            cwd=ROOT_DIR,
            max_turns=15,
            system_prompt={"type": "preset", "preset": "claude_code"},
            allowed_tools=tuple(allowed_tools),
            tools=tuple(allowed_tools),
            write_scope=(
                WriteScope(roots=(QA_DIR, KNOWLEDGE_DIR / "index.md", LOG_FILE)) if writes else None
            ),
            setting_sources=("project",) if writes else None,
            permission_mode="default",
        ),
        query_fn=query,
    )
    if result.failure is not None:
        sys.exit(1)

    _print_answer(result, args.question, as_json=args.json)

    # Usage is tracked in tokens per (provider, model) — DECISIONS
    # 2026-05-23; the old hardcoded $5/$25-per-Mtok estimate is gone.
    # Token counts are cache-inclusive (see UsageTokens).
    log.info(
        "Tokens — input: %d, output: %d",
        result.input_tokens,
        result.output_tokens,
    )
    update_state(_bump_query_counters)


if __name__ == "__main__":
    asyncio.run(main())
