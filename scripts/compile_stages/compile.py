"""LLM-call stage of the compile pipeline (M018-S02).

``compile_source(content, metadata) → CompileResult`` owns everything
between "main() has decided this source needs an LLM call" and "we have a
final article body". Concretely:

- prompt assembly via ``core.prompts.render(metadata.substrate_prompt, …)``
- owner-block injection (``_build_owner_block``)
- pre-flight 60kb budget gate (``assert_prompt_within_budget``)
- 60kb operator-visible size warning
- one SDK ``query(…)`` call with the callback-gate or legacy allowed_tools
  shape depending on ``CONFIG.features.compile_callback_gate``
- per-message stall timeout (``compile_per_call_timeout_s``)
- FailureClass classification on exception (via ``log_sdk_failure``) or on
  structured ``ResultMessage(is_error=True)``
- one-shot retry-on-kind-unknown with the long-context model when the knob
  is on, the source is large enough, and we're not already there
- skip-and-flag conversions for timeout / max_turns / kind=unknown so the
  caller's consecutive-failure budget is preserved

What stays UPSTREAM in compile.py's per-file loop:

- reading the source from disk
- compile_role frontmatter inference + ``final-only`` skip
- substrate-type skip-list check
- substrate-prompt + model + max_turns dispatch (main() packs the result
  into ``CompileMetadata`` and hands it down)
- writing the resulting article to ``knowledge/<bucket>/<slug>.md``
  (that's S03's ``commit_article``)
- state save

The function is parallel/dormant in M018-S02-T02 — T05 rewires
``compile.py:compile_file()`` to actually call it.
"""

from __future__ import annotations

import asyncio
import logging
import time

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    query,
    HookMatcher,
)

from core.config import CONFIG
from core.usage import LEDGER
from core.paths import AGENTS_FILE, KNOWLEDGE_DIR, LOG_FILE, ROOT_DIR
from core.prompts import build_output_language_instruction, render
from core.sdk_helpers import (
    FailureClass,
    PromptTooLargeError,
    StderrCapture,
    assert_prompt_within_budget,
    extract_usage_tokens,
    log_sdk_failure,
    make_path_scope_gate,
    make_path_scope_hook,
    prompt_stream,
)
from core.utils import (
    now_iso,
    read_hard_facts,
    read_wiki_index_compact,
    today_iso,
)

from .types import CompileMetadata, CompileResult

log = logging.getLogger("compile")


def _build_owner_block() -> str:
    """Operator / vault-owner context block injected into substrate prompts.

    Returns "" when ``personal.implicit_operator_author`` is unset
    (multi-tenant vaults). When set, returns a self-contained
    "## Operator / vault owner" Markdown block pointing at
    ``knowledge/people/<slug>.md`` without embedding its contents — keeps
    the block ~400 chars so substrate prompts stay budget-safe; the agent
    Reads the page on demand for self-reference resolution.
    """
    owner = (CONFIG.personal.implicit_operator_author or "").strip()
    if not owner:
        return ""
    page_rel = f"knowledge/people/{owner}.md"
    page_abs = KNOWLEDGE_DIR / "people" / f"{owner}.md"
    if page_abs.exists():
        existence = f"see `{page_rel}`"
    else:
        existence = (
            f"`{page_rel}` does not yet exist — create it via the stub-rules "
            "in §6 when substrate first introduces this person"
        )
    return (
        "## Operator / vault owner\n\n"
        f"This vault belongs to **{owner}** — {existence}.\n\n"
        "When distilling first-person beliefs, commitments, or decisions from "
        f"a source that has no explicit `author:` frontmatter, attribute them "
        f"to **{owner}**. You MAY Read `{page_rel}` to resolve self-references "
        "(\"I\", \"we\", \"my company\") and to find existing entries you "
        "should connect new facts to.\n"
    )


async def _attempt(
    *,
    prompt: str,
    model_id: str,
    max_turns: int,
    source_content: str,
    rel_path: str,
) -> tuple[dict, FailureClass | None]:
    """One SDK ``query(...)`` round. Returns ``(success_dict, None)`` or
    ``({}, FailureClass(...))``. Mirrors the inner ``_attempt`` in
    ``compile.py:compile_file`` byte-for-byte; extracted here so
    ``compile_source`` can retry it cleanly.
    """
    total_input_tokens = 0
    total_output_tokens = 0
    result_text = ""
    final_result: "ResultMessage | None" = None
    started = time.time()
    capture = StderrCapture()
    per_call_timeout = CONFIG.limits.compile_per_call_timeout_s
    common_options = dict(
        max_buffer_size=CONFIG.limits.sdk_max_buffer_size_mb * 1024 * 1024,
        cwd=str(ROOT_DIR),
        model=model_id,
        max_turns=max_turns,
        system_prompt=render("compile_main_system"),
        setting_sources=["project"],
        stderr=capture.callback,
    )
    if CONFIG.features.compile_callback_gate:
        # Path-scoped Write/Edit via PreToolUse hook (2026-05-18). The
        # previous ``can_use_tool=make_path_scope_gate(...)`` approach
        # combined with ``allowed_tools=[Read,Glob,Grep]`` (Write/Edit
        # absent) silently blocked writes INSIDE knowledge/ too — the
        # bundled CLI does not expose tools to the agent when absent from
        # allowed_tools, regardless of callback Allow. ~16h of silent
        # write-failure across compile + dream before discovery. The hook
        # path keeps Write/Edit IN allowed_tools (exposed) but path-scopes
        # them via PreToolUse hook — empirically INSIDE-allow + OUTSIDE-deny
        # both work. See KNOWLEDGE.md for the probe transcript.
        agent_options = ClaudeAgentOptions(
            **common_options,
            allowed_tools=["Read", "Glob", "Grep", "Write", "Edit"],
            hooks={
                "PreToolUse": [
                    HookMatcher(
                        matcher="Write|Edit",
                        hooks=[make_path_scope_hook([ROOT_DIR / "knowledge", LOG_FILE])],
                    ),
                ],
            },
            permission_mode="default",
        )
        query_prompt = prompt_stream(prompt)
    else:
        agent_options = ClaudeAgentOptions(
            **common_options,
            allowed_tools=[
                "Read", "Glob", "Grep",
                "Write(knowledge/**)",
                "Edit(knowledge/**)",
            ],
            permission_mode="acceptEdits",
        )
        query_prompt = prompt
    try:
        agen = query(prompt=query_prompt, options=agent_options).__aiter__()
        while True:
            try:
                if per_call_timeout and per_call_timeout > 0:
                    message = await asyncio.wait_for(
                        agen.__anext__(), timeout=per_call_timeout
                    )
                else:
                    message = await agen.__anext__()
            except StopAsyncIteration:
                break
            if isinstance(message, AssistantMessage) and message.usage:
                total_input_tokens += message.usage.get("input_tokens", 0)
                total_output_tokens += message.usage.get("output_tokens", 0)
            if isinstance(message, ResultMessage):
                final_result = message
                result_text = message.result or ""
    except asyncio.TimeoutError:
        elapsed = time.time() - started
        log.warning(
            "  compile_file ⏱ per-call timeout after %.1fs (no messages "
            "for %ds) — bundled CLI hung; skipping file (consecutive-"
            "failure budget preserved). model=%s source=%s (%d chars).",
            elapsed, per_call_timeout, model_id, rel_path, len(source_content),
        )
        try:
            aclose = getattr(agen, "aclose", None)
            if aclose is not None:
                await aclose()
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass
        capture.dump_to(log)
        log_sdk_failure(
            log,
            label="compile_file",
            source=rel_path,
            model=model_id,
            input_chars=len(source_content),
            started=started,
            capture=capture,
            exc=TimeoutError(
                f"per-call timeout after {elapsed:.1f}s "
                f"(per_call_timeout={per_call_timeout}s)"
            ),
        )
        return {}, FailureClass("timeout", f"per-call stall after {elapsed:.1f}s")
    except Exception as exc:
        elapsed = time.time() - started
        if final_result is not None and final_result.is_error:
            # Ledger gets the TRUE input (uncached + cache-creation + cache-read)
            # for an accurate cost picture; the budget `tokens` check below stays
            # on the uncached per-turn sum so its tuned threshold keeps its
            # meaning (cache_read is re-counted per turn and would explode it —
            # see UsageTokens / sdk_helpers).
            _usage = extract_usage_tokens(final_result.usage)
            ledger_input = _usage.total_input or total_input_tokens
            ledger_output = _usage.output_tokens or total_output_tokens
            cost = final_result.total_cost_usd or 0.0
            tokens = total_input_tokens + total_output_tokens
            LEDGER.record(model=model_id, input_tokens=ledger_input, output_tokens=ledger_output)
            kind = "max_turns" if final_result.subtype == "error_max_turns" else "agent_error"
            detail = (
                f"{final_result.subtype} after {final_result.num_turns} turns "
                f"({elapsed:.1f}s, {tokens:,} tok)"
            )
            if final_result.errors:
                detail += f" — errors: {'; '.join(final_result.errors)}"
            budget = CONFIG.limits.compile_max_tokens_per_file
            if budget > 0 and tokens > budget:
                failure = FailureClass(
                    "tokens_exceeded",
                    f"{tokens:,} tok > budget {budget:,} on {rel_path} (underlying {kind}: {detail})",
                )
            else:
                failure = FailureClass(kind, detail)
            log.error(
                "  compile_file ✗ %s · %s",
                f"failed after {elapsed:.1f}s — kind={failure.kind}",
                detail,
            )
            log.error("    source:    %s", rel_path)
            log.error("    model:     %s", model_id)
            log.error("    input:     %d chars (%.1f KB)",
                      len(source_content), len(source_content) / 1024)
            log.error("    tokens:    %s in / %s out burned despite failure",
                      f"{total_input_tokens:,}", f"{total_output_tokens:,}")
            if failure.kind == "tokens_exceeded":
                log.error(
                    "    TOKEN BUDGET EXCEEDED — batch will abort (raise "
                    "`compile_max_tokens_per_file` from %s if you accept this, "
                    "or add the substrate type to `compile_skip_substrate_types`).",
                    f"{budget:,}",
                )
            capture.dump_to(log)
            return {}, failure
        failure = log_sdk_failure(
            log,
            label="compile_file",
            source=rel_path,
            model=model_id,
            input_chars=len(source_content),
            started=started,
            capture=capture,
            exc=exc,
        )
        return {}, failure

    elapsed = time.time() - started
    cost = float(final_result.total_cost_usd) if (
        final_result is not None and final_result.total_cost_usd is not None
    ) else 0.0
    # TRUE input (cache-inclusive) for ledger + reporting; budget `tokens`
    # stays on the uncached per-turn sum (see error-path comment above).
    _usage = extract_usage_tokens(final_result.usage if final_result is not None else None)
    true_input_tokens = _usage.total_input or total_input_tokens
    true_output_tokens = _usage.output_tokens or total_output_tokens
    tokens = total_input_tokens + total_output_tokens
    LEDGER.record(model=model_id, input_tokens=true_input_tokens, output_tokens=true_output_tokens)
    budget = CONFIG.limits.compile_max_tokens_per_file
    if budget > 0 and tokens > budget:
        log.error(
            "  compile_file ✗ tokens_exceeded · %s tok > budget %s "
            "(elapsed %.1fs, model=%s)",
            f"{tokens:,}", f"{budget:,}", elapsed, model_id,
        )
        log.error("    source:    %s", rel_path)
        log.error(
            "    hint:      this file burned beyond the per-file token guard. "
            "Likely substrate-prompt mismatch (e.g. dense calendar in "
            "compile_main.md). Skip the type via "
            "`compile_skip_substrate_types`, or raise "
            "`compile_max_tokens_per_file` (current: %s) if you accept it.",
            f"{budget:,}",
        )
        return {}, FailureClass(
            "tokens_exceeded",
            f"{tokens:,} tok > budget {budget:,} on {rel_path}",
        )
    log.info(
        "  ✓ %.1fs · in:%s out:%s (%s tok)",
        elapsed,
        f"{true_input_tokens:,}",
        f"{true_output_tokens:,}",
        f"{tokens:,}",
    )
    return (
        {
            "input_tokens": true_input_tokens,
            "output_tokens": true_output_tokens,
            "cost_usd": cost,
            "result": result_text,
        },
        None,
    )


async def compile_source(
    content: str, metadata: CompileMetadata
) -> CompileResult:
    """Run the LLM compile for one source. No file I/O, no state writes.

    Inputs:
    - ``content`` — the substrate body main() already read from disk.
    - ``metadata`` — upstream dispatch decisions: source_path, compile_role,
      model_id, max_turns, substrate_type, substrate_prompt.

    Output: a ``CompileResult`` with ``status`` in {ok, skipped, failed}.
    Skip reasons cover prompt_too_large / compile_per_call_timeout /
    long_context_kind_unknown / max_turns_exhausted /
    kind_unknown_small_source. Failure kinds are the FailureClass values
    (rate_limit, cli_crash, auth, model, network, agent_error,
    cost_exceeded, …).

    Knobs read from CONFIG.limits:
    - compile_max_prompt_chars (60kb pre-flight)
    - compile_per_call_timeout_s (per-message stall)
    - compile_retry_long_context_on_unknown + compile_retry_long_context_min_source_chars
      + compile_failure_backoff_s (one-shot retry-on-kind-unknown ladder)
    - compile_skip_on_long_context_unknown (treats unrecoverable
      kind=unknown / max_turns as skip-and-flag instead of hard failure)
    """
    rel_path = str(metadata.source_path.relative_to(ROOT_DIR)) \
        if metadata.source_path.is_absolute() else str(metadata.source_path)

    # Context blobs the substrate prompt expects. Read inside the stage
    # (option A per the T02 task — keeps CompileMetadata lean; the alternative
    # was extending the dataclass with three pre-read strings).
    agents_md = ""
    if AGENTS_FILE.exists():
        agents_md = AGENTS_FILE.read_text(encoding="utf-8")
    index_md = read_wiki_index_compact()
    facts_md = read_hard_facts()
    owner_block = _build_owner_block()
    today = today_iso()
    now = now_iso()

    prompt = render(
        metadata.substrate_prompt,
        agents_md=agents_md,
        facts_md=facts_md,
        owner_block=owner_block,
        index_md=index_md,
        source_path=rel_path,
        source_content=content,
        today=today,
        now=now,
        # Memory pre-pass results (populated by `compile.py` for memory-*
        # substrates). Empty string when not applicable so `${project_slug}`
        # / `${project_page}` in non-memory prompts substitute cleanly.
        project_slug=metadata.project_slug or "",
        project_page=metadata.project_page_rel or "",
        # Issue #4: operator-pinned output prose language. "" (auto) keeps
        # every substrate prompt byte-identical; a configured language appends
        # the `## Output language` override section to whichever prompts
        # reference the placeholder.
        output_language_instruction=build_output_language_instruction(
            CONFIG.personal.output_language
        ),
    )

    try:
        assert_prompt_within_budget(
            len(prompt),
            CONFIG.limits.compile_max_prompt_chars,
            label=f"compile_file {rel_path}",
            breakdown={
                "compact index": len(index_md),
                "AGENTS.md": len(agents_md),
                "hard facts": len(facts_md),
                "source": len(content),
            },
        )
    except PromptTooLargeError as exc:
        log.error("  %s", exc)
        return CompileResult(status="skipped", skip_reason="prompt_too_large")

    # Operator-visible 60kb size warning. Independent of model-escalation
    # (that decision was made upstream by main()) — the warning fires on
    # every source ≥60kb because that's the empirically-observed boundary
    # for silent-fail / kind=unknown failure classes.
    if len(content) >= 60_000:
        log.info(
            "  size warning: %d chars (%.1f KB) — entering known-fragile "
            "size class; SDK call may take 5-15 min or fail kind=unknown "
            "(per-call timeout: %ds)",
            len(content), len(content) / 1024,
            CONFIG.limits.compile_per_call_timeout_s,
        )

    model = metadata.model_id
    success, failure = await _attempt(
        prompt=prompt,
        model_id=model,
        max_turns=metadata.max_turns,
        source_content=content,
        rel_path=rel_path,
    )
    total_cost = success.get("cost_usd", 0.0) if success else 0.0

    long_ctx_model = CONFIG.models.compile_large_source_model
    min_for_retry = CONFIG.limits.compile_retry_long_context_min_source_chars
    if (
        failure is not None
        and failure.kind == "unknown"
        and CONFIG.limits.compile_retry_long_context_on_unknown
        and long_ctx_model
        and model != long_ctx_model
        and len(content) >= min_for_retry
    ):
        backoff = CONFIG.limits.compile_failure_backoff_s
        if backoff > 0:
            log.warning(
                "  sleeping %ds before long-context retry (rate-limit cushion)",
                backoff,
            )
            await asyncio.sleep(backoff)
        log.warning(
            "  retrying with long-context model %s after kind=unknown",
            long_ctx_model,
        )
        success, failure = await _attempt(
            prompt=prompt,
            model_id=long_ctx_model,
            max_turns=metadata.max_turns,
            source_content=content,
            rel_path=rel_path,
        )
        if success:
            total_cost += success.get("cost_usd", 0.0)
        model = long_ctx_model
    elif (
        failure is not None
        and failure.kind == "unknown"
        and len(content) < min_for_retry
    ):
        log.info(
            "  skipping long-context retry (source %d chars < %d) — "
            "small-source kind=unknown is typically tool-fanout, not context overflow",
            len(content), min_for_retry,
        )

    # Skip-and-flag for structural failures with no further retry path.
    if failure is not None and failure.kind == "timeout":
        return CompileResult(
            status="skipped",
            skip_reason="compile_per_call_timeout",
            cost_usd=total_cost,
        )

    if failure is not None and CONFIG.limits.compile_skip_on_long_context_unknown:
        if failure.kind == "max_turns":
            # Two knobs depending on routing: long-context substrates
            # (compile_force_long_context_types) use compile_max_turns_long_context;
            # everything else uses compile_max_turns. The "long" hint here is
            # only correct when this file was actually long-context-routed.
            turn_knob = (
                "compile_max_turns_long_context"
                if model == long_ctx_model
                else "compile_max_turns"
            )
            log.warning(
                "  skipping: max_turns hit (%s) — agent didn't finish within "
                "the turn budget. Bumping `%s` for this substrate may help; "
                "the file is left uncompiled. "
                "Not counted toward consecutive-failure abort.",
                failure.detail,
                turn_knob,
            )
            return CompileResult(
                status="skipped",
                skip_reason="max_turns_exhausted",
                cost_usd=total_cost,
            )
        if failure.kind == "unknown":
            if model == long_ctx_model:
                log.warning(
                    "  skipping: kind=unknown on long-context model %s "
                    "— bundled CLI exited 1 with no structured ResultMessage. "
                    "Not counted toward consecutive-failure abort.",
                    model,
                )
                return CompileResult(
                    status="skipped",
                    skip_reason="long_context_kind_unknown",
                    cost_usd=total_cost,
                )
            if len(content) < min_for_retry:
                log.warning(
                    "  skipping: small-source kind=unknown with no retry path "
                    "(source %d chars < %d, long-context retry doesn't help here). "
                    "Not counted toward consecutive-failure abort.",
                    len(content), min_for_retry,
                )
                return CompileResult(
                    status="skipped",
                    skip_reason="kind_unknown_small_source",
                    cost_usd=total_cost,
                )

    if failure is not None:
        return CompileResult(
            status="failed",
            failure_kind=failure.kind,
            failure_detail=failure.detail,
            cost_usd=total_cost,
        )

    return CompileResult(
        status="ok",
        article=success.get("result", ""),
        cost_usd=success.get("cost_usd", 0.0),
        input_tokens=success.get("input_tokens", 0),
        output_tokens=success.get("output_tokens", 0),
    )
