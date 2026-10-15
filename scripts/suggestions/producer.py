"""Suggestion producer — Claude SDK pass that runs after compiling email sources.

Writes YAML suggestion files to `raw/suggestions/`. The interactive CLI
(`suggestions/cli.py`) is the consumer; backends in `suggestions/backends/`
execute approved actions.
"""

from __future__ import annotations

import logging
from pathlib import Path

from claude_agent_sdk import query

from core.config import CONFIG
from core.paths import RAW_SUGGESTIONS_DIR, ROOT_DIR
from core.prompts import render
from core.sdk_helpers import SdkCallSpec, WriteScope, run_sdk_query
from core.utils import read_wiki_index_compact, today_iso

log = logging.getLogger("compile")


def _is_email_source(source_path: str) -> bool:
    """Check if a source file contains email scanner data."""
    return "email" in source_path.lower() or "thunderbird" in source_path.lower()


async def maybe_generate_suggestions(source: Path, dry_run: bool = False) -> None:
    """If the source is email data, run a suggestion pass."""
    rel_path = str(source.relative_to(ROOT_DIR))
    if not _is_email_source(rel_path):
        return

    log.info("  Suggestion pass for %s", rel_path)

    if dry_run:
        log.info("  [dry-run] Would run suggestion pass")
        return

    RAW_SUGGESTIONS_DIR.mkdir(parents=True, exist_ok=True)

    source_content = source.read_text(encoding="utf-8")
    index_md = read_wiki_index_compact()

    accounts_inline = (
        ", ".join(
            f"{name} = {info.get('email', '')}" for name, info in CONFIG.personal.accounts.items()
        )
        or "(none configured)"
    )

    prompt = render(
        "compile_suggestion",
        source_path=rel_path,
        source_content=source_content,
        index_md=index_md,
        today=today_iso(),
        primary_account=CONFIG.personal.primary_account,
        email_accounts_inline=accounts_inline,
    )

    result = await run_sdk_query(
        prompt,
        SdkCallSpec(
            label="suggestion_pass",
            logger=log,
            model=CONFIG.models.compile_model,
            cwd=ROOT_DIR,
            max_turns=10,
            system_prompt=render("compile_suggestion_system"),
            allowed_tools=("Read", "Write", "Glob"),
            setting_sources=("project",),
            # The source is third-party email: an instruction injected into a
            # body must not be able to write anywhere but raw/suggestions/.
            write_scope=WriteScope(roots=(RAW_SUGGESTIONS_DIR,)),
            source=rel_path,
            input_chars=len(source_content),
        ),
        query_fn=query,
    )
    if result.ok:
        log.info("  Suggestions: %s", result.result_text[:200])
