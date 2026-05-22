"""Curiosity producer — post-compile pass that detects knowledge gaps.

Runs after each compiled file. Reads the source, asks a local LLM to point
at concrete gaps (with a verbatim quote from the source as anti-hallucination
gate), and writes structured `raw/requests/request-<slug>-<date>.json` files
for the consumer (`scripts/curiosity/cli.py` + `backends/`) to process.

Design notes:
  - The wiki index and "recently compiled articles" used to be in the prompt.
    Both acted as **distractors** (Chroma/Vorstel research: topically-related
    but factually-wrong context hurts more than no context). With them in
    place, the LLM cross-pollinated topics — a Pixeltales/Docker source
    produced an "Eisladen-Logistik case study" gap because that row existed
    elsewhere in the index. Dropped 2026-05-15.
  - `source_quote` is the gate. The schema asks the LLM to copy a verbatim
    phrase from the source-content; the producer rejects gaps whose quote
    isn't a substring of the source. Pattern: HuggingFace structured-RAG
    cookbook, ACL 2024 "According-to" prompting, KRLabsOrg/verbatim-rag.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import re
from pathlib import Path

import httpx  # noqa: E402  exception types only; HTTP via ollama_client

from core import ollama_client
from core.paths import ROOT_DIR
from core.utils import now_iso, today_iso
from core.prompts import render
from core.config import CONFIG

log = logging.getLogger("compile")

CURIOSITY_MODEL = CONFIG.models.curiosity_model
RAW_REQUESTS_DIR = ROOT_DIR / "raw" / "requests"


def _slug_previously_rejected(slug: str) -> bool:
    """True if any past request-<slug>-*.json carries status=rejected.

    Operator marks a request rejected via `wiki curiosity` (walk mode).
    The rejected file stays in `raw/requests/` and acts as a tombstone —
    the producer reads it to suppress future re-emissions of the same
    topic-slug. Different-day filenames don't matter; the slug is the key.
    """
    if not RAW_REQUESTS_DIR.exists():
        return False
    for past in RAW_REQUESTS_DIR.glob(f"request-{slug}-*.json"):
        try:
            data = json.loads(past.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("status") == "rejected":
            return True
    return False


def _normalize_quote(s: str) -> str:
    """Lower-case + collapse whitespace for the substring check.

    The LLM occasionally tightens whitespace inside the quote (collapses two
    spaces to one, drops a trailing newline) or changes the case of the
    first character to fit grammar. We accept those small deviations as
    long as the bag-of-characters matches a span of the source.
    """
    return re.sub(r"\s+", " ", s).strip().lower()


def _quote_anchored_in_source(quote_norm: str, source_norm: str, min_tokens: int) -> bool:
    """Return True if any `min_tokens`-long token window from the quote
    appears verbatim in the source.

    LLMs routinely paraphrase the edges of a quote while keeping a verbatim
    core (observed 2026-05-15 against `daily/2026-05-15.md`: 3/3 gaps had
    matched n-grams of 6-15 tokens, but strict whole-quote substring missed
    all three). The anchor check accepts the quote if it has *at least one*
    contiguous N-word block in the source — verifiable proof the model
    actually cited rather than invented, even if the edges drift.
    """
    if not quote_norm:
        return False
    tokens = quote_norm.split()
    if len(tokens) < min_tokens:
        # Quote too short for the anchor check — fall back to strict substring.
        # Reading a 1-4 word phrase loosely is risky (stop-word coincidence).
        return quote_norm in source_norm
    for start in range(len(tokens) - min_tokens + 1):
        window = " ".join(tokens[start:start + min_tokens])
        if window in source_norm:
            return True
    return False


async def maybe_generate_curiosity_requests(source: Path) -> None:
    """Detect knowledge gaps and write deep-scan requests to raw/requests/."""
    if not CONFIG.features.curiosity_loop:
        return

    rel_path = str(source.relative_to(ROOT_DIR))
    source_content = source.read_text(encoding="utf-8")

    # Only run curiosity on substantial sources (not tiny deltas)
    if len(source_content) < CONFIG.limits.curiosity_min_source_chars:
        return

    # Source-type allowlist (quality gate #1). Curiosity-on-email only makes
    # sense for sources that naturally have email-side correspondence:
    # meeting transcripts (follow-ups), articles (vendor/author threads),
    # notes (operational), daily logs (TODO trails). Memories and other
    # cognitive self-notes don't have that surface, so the model defaults
    # to generic catch-all folders. Empty allowlist = no filtering.
    src_globs = CONFIG.limits.curiosity_source_globs
    if src_globs and not any(fnmatch.fnmatch(rel_path, g) for g in src_globs):
        log.debug("  Curiosity: skipping %s (no source-glob match)", rel_path)
        return

    # Folder allowlist (quality gate #2). Operator can subset the curiosity
    # target pool to exclude generic catch-alls. Empty list = use all
    # email_folders. Order preserved from operator's allowlist if set.
    allowed = CONFIG.personal.curiosity_folders or []
    if allowed:
        allowed_set = set(allowed)
        folders_used = [f for f in CONFIG.personal.email_folders
                        if f.get("path") and f["path"] in allowed_set]
        if not folders_used:
            log.warning(
                "  Curiosity: personal.curiosity_folders=%r matched zero "
                "email_folders — falling back to full list",
                allowed,
            )
            folders_used = [f for f in CONFIG.personal.email_folders if f.get("path")]
    else:
        folders_used = [f for f in CONFIG.personal.email_folders if f.get("path")]

    folder_paths = [f["path"] for f in folders_used]
    if not folder_paths:
        log.info("  Curiosity: no personal.email_folders configured, skipping")
        return
    # Numbered listing — the schema constrains `folder_index` to an integer
    # range, but the prompt still has to spell out which integer maps to
    # which folder. Single source of truth: the same enumerate order is
    # used to map `folder_index → folder_path` after parsing. Uses
    # `folders_used` (post-allowlist), NOT raw CONFIG.personal.email_folders.
    folder_listing = "\n".join(
        f"{i+1}. {f['path']} — {f.get('desc', '')}".rstrip(" —")
        for i, f in enumerate(folders_used)
    )

    # Cap source excerpt at 5k chars so the prompt fits any small-context
    # model without truncation. Source is the *only* embedded artifact now —
    # the wiki index and "recently compiled articles" were dropped as they
    # acted as distractors (cross-source topic contamination).
    src_excerpt = source_content[:5000]

    prompt = render(
        "compile_curiosity",
        source_path=rel_path,
        source_content=src_excerpt,
        timestamp=now_iso(),  # cache-buster
        primary_account=CONFIG.personal.primary_account,
        email_folders_listing=folder_listing,
    )

    # Defense-in-depth: even without index_md, a pathological source could
    # in theory push past budget. Warn (don't abort) so the operator sees it.
    if len(prompt) > CONFIG.limits.curiosity_max_prompt_chars:
        log.warning(
            "  Curiosity: prompt %d chars exceeds budget %d — sending anyway",
            len(prompt), CONFIG.limits.curiosity_max_prompt_chars,
        )

    # Ollama reachability pre-check (mirrors scan_youtube / scan_screenshots /
    # pictures / review-wiki — this was the one Ollama call site missing it).
    # Without it an offline GPU server makes every curiosity pass wait the full
    # curiosity_timeout_s (240s) before failing — ~4 min wasted per compiled
    # file. The check costs ~5s and fast-skips instead. Placed after the cheap
    # size/glob/folder gates so it only runs when a real pass would happen.
    if not ollama_client.is_reachable():
        log.warning(
            "  Curiosity: Ollama not reachable at %s — skipping (server down?)",
            CONFIG.models.ollama_url,
        )
        return

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
                        # source_quote is the anti-hallucination gate. Producer
                        # validates it is a verbatim substring of source_content;
                        # gaps that fail are dropped (dropped[unsourced]).
                        "source_quote": {"type": "string"},
                        "folder_index": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": len(folder_paths),
                        },
                        # folder_confidence: 1-5 self-reported. Below
                        # CONFIG.limits.curiosity_folder_confidence_min the
                        # gap is dropped. Forces explicit abstention instead
                        # of hedging on a generic catch-all folder.
                        "folder_confidence": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 5,
                        },
                        "account": {"type": "string", "enum": account_names},
                        "rationale": {"type": "string"},
                    },
                    "required": [
                        "topic", "source_quote", "folder_index",
                        "folder_confidence", "account", "rationale",
                    ],
                },
            },
        },
        "required": ["gaps"],
    }

    # Pre-compute the normalised source-excerpt once for the quote-validation
    # gate. The LLM's quote needs to be a substring of WHAT IT SAW (the
    # excerpt that went into the prompt), not the full file — otherwise a
    # truncation past 5000 chars would falsely look like a verbatim match.
    src_excerpt_norm = _normalize_quote(src_excerpt)

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
        confidence_min = CONFIG.limits.curiosity_folder_confidence_min
        for gap in gaps[:CONFIG.limits.curiosity_max_gaps]:
            topic = gap.get("topic", "").strip()
            rationale = gap.get("rationale", "").strip()
            source_quote = (gap.get("source_quote") or "").strip()
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

            # Quality gate #3: folder confidence threshold. The LLM self-rates
            # 1-5 how confident the picked folder actually contains relevant
            # mail. Below the threshold the gap is dropped — better to abstain
            # than guess on a generic catch-all.
            folder_confidence = gap.get("folder_confidence")
            if not isinstance(folder_confidence, int):
                dropped["folder_low_confidence"] = dropped.get("folder_low_confidence", 0) + 1
                continue
            if folder_confidence < confidence_min:
                dropped["folder_low_confidence"] = dropped.get("folder_low_confidence", 0) + 1
                continue

            if not topic:
                dropped["empty_topic"] = dropped.get("empty_topic", 0) + 1
                continue
            if not rationale:
                dropped["empty_rationale"] = dropped.get("empty_rationale", 0) + 1
                continue

            # Anti-hallucination gate: the quote must be anchored in the
            # source excerpt the model actually saw. We accept the quote if
            # ANY contiguous N-token window from the (normalised) quote
            # appears in the source — tolerant of edge paraphrase but still
            # verifiable proof of source-anchoring. Reject quotes shorter
            # than 8 chars — too short to be a meaningful anchor (matches
            # stop-words like "the project").
            if not source_quote or len(source_quote) < 8:
                dropped["quote_missing"] = dropped.get("quote_missing", 0) + 1
                continue
            if not _quote_anchored_in_source(
                _normalize_quote(source_quote),
                src_excerpt_norm,
                CONFIG.limits.curiosity_quote_min_anchor_tokens,
            ):
                dropped["quote_unsourced"] = dropped.get("quote_unsourced", 0) + 1
                continue

            slug = re.sub(r"[^a-z0-9]+", "-", topic.lower())[:40].strip("-")
            request_path = RAW_REQUESTS_DIR / f"request-{slug}-{today_iso()}.json"

            if request_path.exists():
                dropped["duplicate"] = dropped.get("duplicate", 0) + 1
                continue

            # Persistent rejection: operator rejected this slug in a prior walk.
            # Any past request-<slug>-*.json with status=rejected blocks re-emission.
            if _slug_previously_rejected(slug):
                dropped["rejected_persistent"] = dropped.get("rejected_persistent", 0) + 1
                continue

            request = {
                "type": "email-deep-scan",
                "status": "pending",
                "folder": folder,
                "folder_confidence": folder_confidence,
                "account": gap.get("account", CONFIG.personal.primary_account),
                "model": gap.get("model", CURIOSITY_MODEL),
                "topic": topic,
                "source_quote": source_quote,  # provenance — verified-substring of source
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
