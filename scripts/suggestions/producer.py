"""Suggestion producer — Claude SDK pass that runs after compiling email sources.

Writes YAML suggestion files to `raw/suggestions/`. The interactive CLI
(`suggestions/cli.py`) is the consumer; backends in `suggestions/backends/`
execute approved actions.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from core.config import RAW_SUGGESTIONS_DIR, ROOT_DIR, today_iso
from core.prompts import render
from core.sdk_helpers import StderrCapture, log_sdk_failure
from core.utils import read_wiki_index
from core.wiki_config import CONFIG

log = logging.getLogger("compile")


def _is_email_source(source_path: str) -> bool:
    """Check if a source file contains email scanner data."""
    return "email" in source_path.lower() or "thunderbird" in source_path.lower()


def _read_rules_overview() -> str:
    """Read the Thunderbird rules overview if it exists."""
    overview = ROOT_DIR / "raw" / "notes" / "email" / "thunderbird-rules-overview.md"
    if overview.exists():
        return overview.read_text(encoding="utf-8")
    return "(No rules overview found. Run: thunderbird-rules.py --export)"


def _read_procmail_config() -> str:
    """Read current procmail config from server if available."""
    try:
        import sys
        sys.path.insert(0, str(ROOT_DIR / "scripts"))
        from importlib import import_module
        tb = import_module("thunderbird-rules")
        config = tb.get_procmail_config()
        if config:
            return config
    except Exception:
        pass
    return "(Procmail config not available)"


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
    rules_overview = _read_rules_overview()
    index_md = read_wiki_index()

    procmail_config = _read_procmail_config()

    accounts_inline = ", ".join(
        f"{name} = {info.get('email', '')}" for name, info in CONFIG.personal.accounts.items()
    ) or "(none configured)"

    prompt = render(
        "compile_suggestion",
        rules_overview=rules_overview,
        procmail_config=procmail_config,
        source_path=rel_path,
        source_content=source_content,
        index_md=index_md,
        today=today_iso(),
        primary_account=CONFIG.personal.primary_account,
        email_accounts_inline=accounts_inline,
    )

    started = time.time()
    capture = StderrCapture()
    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                cwd=str(ROOT_DIR),
                model=CONFIG.models.compile_model,
                allowed_tools=["Read", "Write", "Glob"],
                permission_mode="acceptEdits",
                max_turns=10,
                system_prompt=render("compile_suggestion_system"),
                setting_sources=[],
                stderr=capture.callback,
            ),
        ):
            if isinstance(message, ResultMessage):
                log.info("  Suggestions: %s", message.result[:200])
    except Exception as exc:
        log_sdk_failure(
            log,
            label="suggestion_pass",
            source=rel_path,
            model=CONFIG.models.compile_model,
            input_chars=len(source_content),
            started=started,
            capture=capture,
            exc=exc,
        )
