"""Query the knowledge base with natural language.

Usage:
    uv run python query.py "What do I know about X?"
    uv run python query.py "What do I know about X?" --file-back
"""

import os
os.environ["CLAUDE_INVOKED_BY"] = "query"

import argparse
import asyncio
import logging
import sys

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    query,
)

from config import KNOWLEDGE_DIR, QA_DIR, ROOT_DIR, now_iso, today_iso
from utils import (
    load_state,
    read_all_wiki_content,
    read_hard_facts,
    save_state,
    slugify,
)

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("query")

from prompts import render  # noqa: E402

# ── Query prompt ─────────────────────────────────────────────────────

# ── Main ─────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Query the knowledge base")
    parser.add_argument("question", type=str, help="Your question")
    parser.add_argument(
        "--file-back",
        action="store_true",
        help="Save the answer as a Q&A article in the wiki",
    )
    args = parser.parse_args()

    question = args.question
    file_back = args.file_back

    log.info("Query: %s (file_back=%s)", question, file_back)

    # Load entire wiki content for context
    wiki_content = read_all_wiki_content()
    facts_md = read_hard_facts()

    if file_back:
        QA_DIR.mkdir(parents=True, exist_ok=True)
        prompt = render(
            "query_file_back",
            wiki_content=wiki_content,
            facts_md=facts_md,
            question=question,
            today=today_iso(),
            now=now_iso(),
        )
        allowed_tools = ["Read", "Glob", "Grep", "Write", "Edit"]
    else:
        prompt = render(
            "query_main",
            wiki_content=wiki_content,
            facts_md=facts_md,
            question=question,
        )
        allowed_tools = ["Read", "Glob", "Grep"]

    # Run the query agent
    total_input_tokens = 0
    total_output_tokens = 0
    result_text = ""

    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                cwd=str(ROOT_DIR),
                system_prompt={"type": "preset", "preset": "claude_code"},
                allowed_tools=allowed_tools,
                permission_mode="acceptEdits",
                max_turns=15,
            ),
        ):
            if isinstance(message, AssistantMessage) and message.usage:
                total_input_tokens += message.usage.get("input_tokens", 0)
                total_output_tokens += message.usage.get("output_tokens", 0)
            if isinstance(message, ResultMessage):
                result_text = message.result
    except Exception:
        log.exception("Query failed")
        sys.exit(1)

    # Print the answer
    print("\n" + result_text)

    # Cost tracking
    cost = (total_input_tokens * 5.0 + total_output_tokens * 25.0) / 1_000_000
    log.info("Tokens — input: %d, output: %d, cost: $%.4f", total_input_tokens, total_output_tokens, cost)

    # Update state
    state = load_state()
    state["query_count"] = state.get("query_count", 0) + 1
    state["total_cost"] = round(state.get("total_cost", 0.0) + cost, 4)
    state["last_query"] = now_iso()
    save_state(state)


if __name__ == "__main__":
    asyncio.run(main())
