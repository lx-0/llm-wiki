"""Curiosity producer — post-compile pass that detects knowledge gaps.

Runs after each compiled file. Reads the new article + recent compiled
articles + a folder map, asks a local Gemma4 to point at concrete gaps,
and writes structured `raw/requests/request-<slug>-<date>.json` files
for the consumer (`scripts/curiosity/cli.py` + `backends/`) to process.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import httpx  # noqa: E402  exception types only; HTTP via ollama_client

from core import ollama_client
from core.config import KNOWLEDGE_DIR, ROOT_DIR, now_iso, today_iso
from core.prompts import render
from core.utils import read_wiki_index_compact
from core.wiki_config import CONFIG

log = logging.getLogger("compile")

CURIOSITY_MODEL = CONFIG.models.curiosity_model
RAW_REQUESTS_DIR = ROOT_DIR / "raw" / "requests"


def _get_recently_compiled_articles() -> str:
    """Get articles updated today (likely just compiled)."""
    today = today_iso()
    articles = []
    for subdir in ["concepts", "connections", "people", "projects"]:
        d = KNOWLEDGE_DIR / subdir
        if not d.exists():
            continue
        for f in d.glob("*.md"):
            content = f.read_text(encoding="utf-8")
            if f"updated: {today}" in content or f"created: {today}" in content:
                articles.append(f"### {f.relative_to(KNOWLEDGE_DIR)}\n\n{content[:500]}")
    return "\n\n".join(articles) if articles else "(No articles updated today)"


async def maybe_generate_curiosity_requests(source: Path) -> None:
    """Detect knowledge gaps and write deep-scan requests to raw/requests/."""
    if not CONFIG.features.curiosity_loop:
        return

    rel_path = str(source.relative_to(ROOT_DIR))
    source_content = source.read_text(encoding="utf-8")

    # Only run curiosity on substantial sources (not tiny deltas)
    if len(source_content) < CONFIG.limits.curiosity_min_source_chars:
        return

    index_md = read_wiki_index_compact()
    compiled_articles = _get_recently_compiled_articles()

    folder_paths = [f["path"] for f in CONFIG.personal.email_folders if f.get("path")]
    if not folder_paths:
        log.info("  Curiosity: no personal.email_folders configured, skipping")
        return
    folder_listing = "\n".join(
        f"- {f['path']} — {f.get('desc', '')}".rstrip(" —")
        for f in CONFIG.personal.email_folders
    )

    prompt = render(
        "compile_curiosity",
        index_md=index_md,
        source_path=rel_path,
        source_content=source_content[:5000],  # cap to avoid huge prompts
        compiled_articles=compiled_articles[:3000],
        timestamp=now_iso(),  # cache-buster
        primary_account=CONFIG.personal.primary_account,
        email_folders_listing=folder_listing,
    )

    log.info("  Curiosity pass for %s", rel_path)

    account_names = list(CONFIG.personal.accounts.keys()) or [CONFIG.personal.primary_account]
    schema = {
        "type": "object",
        "properties": {
            "gaps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "folder": {"type": "string", "enum": folder_paths},
                        "account": {"type": "string", "enum": account_names},
                        "rationale": {"type": "string"},
                    },
                    "required": ["topic", "folder", "account", "rationale"],
                },
            },
        },
        "required": ["gaps"],
    }

    try:
        content = ollama_client.chat_schema(
            prompt,
            model=CURIOSITY_MODEL,
            schema=schema,
            timeout=CONFIG.limits.curiosity_timeout_s,
        )
        try:
            parsed = ollama_client.parse_json_lenient(content)
        except json.JSONDecodeError:
            log.warning("  Curiosity: invalid JSON: %s", content[:200])
            return

        if isinstance(parsed, list):
            gaps = parsed
        elif isinstance(parsed, dict):
            gaps = parsed.get("gaps", [])
        else:
            log.info("  Curiosity: unexpected response type")
            return
        if not gaps:
            log.info("  Curiosity: no gaps found")
            return

        non_dict = [g for g in gaps if not isinstance(g, dict)]
        if non_dict:
            log.warning("  Curiosity: dropping %d non-dict gap(s); sample=%r",
                        len(non_dict), non_dict[0])
        gaps = [g for g in gaps if isinstance(g, dict)]
        if not gaps:
            return

        RAW_REQUESTS_DIR.mkdir(parents=True, exist_ok=True)

        for gap in gaps[:CONFIG.limits.curiosity_max_gaps]:
            folder = gap.get("folder", "").strip()
            topic = gap.get("topic", "").strip()
            rationale = gap.get("rationale", "").strip()

            if not folder or not topic or not rationale:
                log.info("  Curiosity: skipping (folder=%r, topic=%r, rationale=%r)",
                         folder[:30] if folder else '', topic[:30] if topic else '', rationale[:30] if rationale else '')
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", topic.lower())[:40].strip("-")
            request_path = RAW_REQUESTS_DIR / f"request-{slug}-{today_iso()}.json"

            if request_path.exists():
                continue  # don't overwrite

            request = {
                "type": "email-deep-scan",
                "status": "pending",
                "folder": folder,
                "account": gap.get("account", CONFIG.personal.primary_account),
                "model": gap.get("model", CURIOSITY_MODEL),
                "topic": topic,
                "rationale": rationale,
                "source": rel_path,
                "created": now_iso(),
            }
            request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
            log.info("  Curiosity request: %s → %s", topic, folder)

    except httpx.TimeoutException:
        log.warning("  Curiosity: Ollama timeout")
    except (json.JSONDecodeError, KeyError) as e:
        log.warning("  Curiosity: parse error: %s", e)
    except Exception:
        log.exception("  Curiosity pass failed")
