"""Agentically propagate a hard fact across the vault (knowledge/, daily/, raw/).

Reads `knowledge/facts/<slug>.md`, then spawns a Claude Agent SDK session with
edit permissions over the vault. The agent strikes false claims, renames files
for disambiguation, and fixes wikilinks. On success the fact's frontmatter
gets `applied: <iso-ts>` written back.

Usage:
    uv run python scripts/facts/correct_apply.py <slug>           # apply one fact
    uv run python scripts/facts/correct_apply.py <slug> --dry-run # plan only, no edits
"""

import os
os.environ["CLAUDE_INVOKED_BY"] = "correct_apply"

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    query,
)

from core.config import FACTS_DIR, ROOT_DIR, now_iso, today_iso
from core.wiki_config import CONFIG  # noqa: E402
from core.prompts import render  # noqa: E402
from core.sdk_helpers import StderrCapture, log_sdk_failure  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("correct-apply")


def _split_frontmatter(text: str) -> tuple[dict, str, str]:
    """Return (frontmatter dict, raw frontmatter block, body)."""
    if not text.startswith("---\n"):
        return {}, "", text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, "", text
    block = text[4:end]
    body = text[end + 5 :]
    try:
        fm = yaml.safe_load(block) or {}
    except yaml.YAMLError:
        fm = {}
    return (fm if isinstance(fm, dict) else {}), block, body


def _write_frontmatter(path: Path, fm: dict, body: str) -> None:
    serialized = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip()
    path.write_text(f"---\n{serialized}\n---\n\n{body.lstrip()}", encoding="utf-8")


def _backup(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak.{ts}")
    bak.write_bytes(path.read_bytes())
    return bak


async def apply(slug: str, dry_run: bool) -> int:
    fact_path = FACTS_DIR / f"{slug}.md"
    if not fact_path.exists():
        log.error("No such fact: %s (looked at %s)", slug, fact_path)
        return 1

    fact_text = fact_path.read_text(encoding="utf-8")
    fm, _block, _body = _split_frontmatter(fact_text)
    if fm.get("type") != "fact":
        log.warning("File %s does not have type: fact — proceeding anyway.", fact_path)

    rel_fact_path = fact_path.relative_to(ROOT_DIR)
    prompt = render(
        "correct_apply",
        fact_content=fact_text,
        fact_path=str(rel_fact_path),
        slug=slug,
        today=today_iso(),
        now=now_iso(),
    )

    if dry_run:
        log.info("[dry-run] Would spawn Claude Agent SDK with:")
        log.info("  cwd=%s", ROOT_DIR)
        log.info("  model=%s", CONFIG.models.compile_model)
        log.info("  fact=%s", rel_fact_path)
        log.info("  status=%s", fm.get("status"))
        log.info("  negation_terms=%s", fm.get("negation_terms") or [])
        return 0

    log.info("Spawning agent over vault root %s for fact %s", ROOT_DIR, slug)

    total_input_tokens = 0
    total_output_tokens = 0
    result_text = ""

    import time as _time
    started = _time.time()
    capture = StderrCapture()
    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                max_buffer_size=CONFIG.limits.sdk_max_buffer_size_mb * 1024 * 1024,
                cwd=str(ROOT_DIR),
                model=CONFIG.models.compile_model,
                allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
                permission_mode="acceptEdits",
                max_turns=50,
                system_prompt={"type": "preset", "preset": "claude_code"},
                stderr=capture.callback,
            ),
        ):
            if isinstance(message, AssistantMessage) and message.usage:
                total_input_tokens += message.usage.get("input_tokens", 0)
                total_output_tokens += message.usage.get("output_tokens", 0)
            if isinstance(message, ResultMessage):
                result_text = message.result or ""
    except Exception as exc:
        log_sdk_failure(
            log,
            label="correct_apply",
            source=f"fact:{slug}",
            model=CONFIG.models.compile_model,
            input_chars=len(prompt),
            started=started,
            capture=capture,
            exc=exc,
        )
        return 2

    log.info("Agent done. Tokens — input: %d, output: %d", total_input_tokens, total_output_tokens)
    if result_text:
        print("\n" + result_text + "\n")

    # Mark fact as applied. Re-read to avoid stomping if the agent edited it
    # (it shouldn't — the prompt forbids it — but be safe).
    current_text = fact_path.read_text(encoding="utf-8")
    fm_now, _, body_now = _split_frontmatter(current_text)
    if fm_now:
        _backup(fact_path)
        fm_now["applied"] = now_iso()
        fm_now["updated"] = today_iso()
        _write_frontmatter(fact_path, fm_now, body_now)
        log.info("Marked %s as applied=%s", rel_fact_path, fm_now["applied"])
    else:
        log.warning("Could not parse fact frontmatter after run; not updating `applied:`.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Propagate a hard fact across the vault.")
    parser.add_argument("slug", help="fact slug (filename without .md)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would happen without spawning the agent",
    )
    args = parser.parse_args()
    return asyncio.run(apply(args.slug, args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
