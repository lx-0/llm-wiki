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
from core.paths import KNOWLEDGE_DIR, ROOT_DIR
from core.utils import now_iso, read_wiki_index_compact, today_iso
from core.prompts import render
from core.config import CONFIG

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
    # Numbered listing — the schema constrains `folder_index` to an integer
    # range, but the prompt still has to spell out which integer maps to
    # which folder. Single source of truth: the same enumerate order is
    # used to map `folder_index → folder_path` after parsing.
    folder_listing = "\n".join(
        f"{i+1}. {f['path']} — {f.get('desc', '')}".rstrip(" —")
        for i, f in enumerate(CONFIG.personal.email_folders)
    )

    # Pre-flight: keep the prompt under the picked model's effective window.
    # Different models silently degrade differently when oversized — phi4's
    # 16k window truncated and hallucinated; gemma4 ignores the schema
    # entirely. The compact-index portion grows linearly with the vault and
    # is the only knob we can shrink without losing the source signal. If
    # the assembled prompt would breach budget, truncate index_md in place,
    # warn the operator, and continue — curiosity is opportunistic, not
    # blocking.
    src_excerpt = source_content[:5000]
    compiled_excerpt = compiled_articles[:3000]
    budget = CONFIG.limits.curiosity_max_prompt_chars
    # Reserve room for everything except index_md (template, source excerpt,
    # folder listing, compiled excerpt, timestamp, slack).
    non_index_chars = len(src_excerpt) + len(compiled_excerpt) + len(folder_listing) + 4_000
    max_index_chars = max(10_000, budget - non_index_chars)
    if len(index_md) > max_index_chars:
        log.warning(
            "  Curiosity: compact index (%d chars) exceeds budget — truncating to %d chars",
            len(index_md), max_index_chars,
        )
        index_md = index_md[:max_index_chars] + "\n\n_[index truncated for curiosity budget]_\n"

    prompt = render(
        "compile_curiosity",
        index_md=index_md,
        source_path=rel_path,
        source_content=src_excerpt,
        compiled_articles=compiled_excerpt,
        timestamp=now_iso(),  # cache-buster
        primary_account=CONFIG.personal.primary_account,
        email_folders_listing=folder_listing,
    )

    log.info("  Curiosity pass for %s (model=%s, prompt=%d chars)",
             rel_path, CURIOSITY_MODEL, len(prompt))

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
                        "folder_index": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": len(folder_paths),
                        },
                        "account": {"type": "string", "enum": account_names},
                        "rationale": {"type": "string"},
                    },
                    "required": ["topic", "folder_index", "account", "rationale"],
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

        raw_count = len(gaps)
        kept = 0
        dropped: dict[str, int] = {}
        for gap in gaps[:CONFIG.limits.curiosity_max_gaps]:
            topic = gap.get("topic", "").strip()
            rationale = gap.get("rationale", "").strip()
            # Accept both new (folder_index) and legacy (folder) shapes during
            # the rollout — Ollama JSON Schema enforcement is best-effort, so
            # the gap may carry either field even when only one is required.
            folder_index = gap.get("folder_index")
            folder = (gap.get("folder") or "").strip()
            if isinstance(folder_index, int) and 1 <= folder_index <= len(folder_paths):
                folder = folder_paths[folder_index - 1]
            elif folder not in folder_paths:
                dropped["folder_unmapped"] = dropped.get("folder_unmapped", 0) + 1
                continue

            if not topic:
                dropped["empty_topic"] = dropped.get("empty_topic", 0) + 1
                continue
            if not rationale:
                dropped["empty_rationale"] = dropped.get("empty_rationale", 0) + 1
                continue

            slug = re.sub(r"[^a-z0-9]+", "-", topic.lower())[:40].strip("-")
            request_path = RAW_REQUESTS_DIR / f"request-{slug}-{today_iso()}.json"

            if request_path.exists():
                dropped["duplicate"] = dropped.get("duplicate", 0) + 1
                continue

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
            kept += 1
            log.info("  Curiosity request: %s → %s", topic, folder)

        if dropped or kept != raw_count:
            drop_str = ", ".join(f"{k}={v}" for k, v in dropped.items()) or "none"
            log.info(
                "  Curiosity: %d gap(s) gen, %d kept (dropped: %s)",
                raw_count, kept, drop_str,
            )

    except httpx.TimeoutException:
        log.warning("  Curiosity: Ollama timeout (model=%s, %ds)",
                    CURIOSITY_MODEL, CONFIG.limits.curiosity_timeout_s)
    except httpx.HTTPStatusError as e:
        # Distinguish "model not pulled" (404) from generic Ollama errors so
        # the operator gets a clear "ollama pull <model>" hint when needed.
        if e.response.status_code == 404:
            log.warning(
                "  Curiosity: Ollama model %r not available — pull it on the host "
                "(`ollama pull %s`) or change CONFIG.models.curiosity_model",
                CURIOSITY_MODEL, CURIOSITY_MODEL,
            )
        else:
            log.warning("  Curiosity: Ollama HTTP %s — %s",
                        e.response.status_code, e.response.text[:200])
    except httpx.HTTPError as e:
        log.warning("  Curiosity: Ollama connection error: %s", e)
    except (json.JSONDecodeError, KeyError) as e:
        log.warning("  Curiosity: parse error: %s", e)
    except Exception:
        log.exception("  Curiosity pass failed")
