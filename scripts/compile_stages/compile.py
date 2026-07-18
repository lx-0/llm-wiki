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

from claude_agent_sdk import query

from core.config import CONFIG
from core.paths import AGENTS_FILE, KNOWLEDGE_DIR, LOG_FILE, ROOT_DIR
from core.prompts import build_output_language_instruction, render
from core.sdk_helpers import (
    FailureClass,
    PromptTooLargeError,
    SdkCallSpec,
    WriteScope,
    assert_prompt_within_budget,
    run_sdk_query,
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
    """One SDK round via ``run_sdk_query``. Returns ``(success_dict, None)``
    or ``({}, FailureClass(...))``.

    The harness owns the mechanics (options assembly, path-scope hook,
    per-message stall timeout, usage extraction, LEDGER recording,
    failure diagnostics). Compile-only POLICY stays here: the per-file
    token budget guard on the deliberately-uncached per-turn basis
    (DECISIONS 2026-06-02 — cache_read is re-counted per turn and would
    explode the tuned threshold), applied to structured errors and
    successes alike.
    """
    result = await run_sdk_query(
        prompt,
        SdkCallSpec(
            label="compile_file",
            logger=log,
            model=model_id,
            cwd=ROOT_DIR,
            max_turns=max_turns,
            system_prompt=render("compile_main_system"),
            setting_sources=("project",),
            # Path-scoped Write/Edit via PreToolUse hook (2026-05-18): the
            # earlier can_use_tool + tools-absent shape silently blocked
            # INSIDE-scope writes too (~16h of silent write-failure). The
            # legacy glob shape stays one config flip away via
            # features.compile_callback_gate. See KNOWLEDGE.md.
            allowed_tools=("Read", "Glob", "Grep", "Write", "Edit"),
            write_scope=WriteScope(
                roots=(ROOT_DIR / "knowledge", LOG_FILE),
                legacy_allowed_tools=(
                    "Read", "Glob", "Grep",
                    "Write(knowledge/**)", "Edit(knowledge/**)",
                ),
            ),
            stall_timeout_s=CONFIG.limits.compile_per_call_timeout_s,
            source=rel_path,
            input_chars=len(source_content),
        ),
        query_fn=query,
    )

    tokens = result.uncached_input_tokens + result.uncached_output_tokens
    budget = CONFIG.limits.compile_max_tokens_per_file

    if result.failure is not None:
        failure = result.failure
        if failure.kind == "timeout":
            log.warning(
                "  compile_file: skipping file after per-call timeout "
                "(consecutive-failure budget preserved).",
            )
            return {}, failure
        # Budget policy on structured errors (subtype present): a failed
        # call that burned past the guard escalates to tokens_exceeded so
        # the batch aborts instead of burning the same budget on the next
        # file.
        if result.subtype is not None and budget > 0 and tokens > budget:
            failure = FailureClass(
                "tokens_exceeded",
                f"{tokens:,} tok > budget {budget:,} on {rel_path} "
                f"(underlying {failure.kind}: {failure.detail})",
            )
            log.error(
                "    TOKEN BUDGET EXCEEDED — batch will abort (raise "
                "`compile_max_tokens_per_file` from %s if you accept this, "
                "or add the substrate type to `compile_skip_substrate_types`).",
                f"{budget:,}",
            )
        return {}, failure

    if budget > 0 and tokens > budget:
        log.error(
            "  compile_file ✗ tokens_exceeded · %s tok > budget %s "
            "(elapsed %.1fs, model=%s)",
            f"{tokens:,}", f"{budget:,}", result.elapsed_s, model_id,
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
        result.elapsed_s,
        f"{result.input_tokens:,}",
        f"{result.output_tokens:,}",
        f"{tokens:,}",
    )
    return (
        {
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
            "result": result.result_text,
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
            # The turn budget is metadata.max_turns — pinned per substrate in
            # compile_stages.route.SUBSTRATE_PROMPTS (or limits.compile_max_turns
            # for unmapped substrates). Raise it there if this substrate
            # legitimately needs more turns.
            log.warning(
                "  skipping: max_turns hit (%s) — agent didn't finish within "
                "the %d-turn budget; the file is left uncompiled. "
                "Not counted toward consecutive-failure abort.",
                failure.detail,
                metadata.max_turns,
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
