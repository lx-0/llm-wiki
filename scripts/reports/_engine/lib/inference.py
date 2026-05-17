"""SDK-driven item-answer inference for operator-self-report instruments.

The wedge composition (verified empirically in M019-S01-T01):

  allowed_tools = ['Read', 'Glob', 'Grep']
  disallowed_tools = ['Write', 'Edit', 'NotebookEdit']
  permission_mode = 'default'                      # NOT acceptEdits
  can_use_tool = make_path_scope_gate([])          # deny-all-writes
  setting_sources = ['project']

Agent receives an inference prompt (rendered from
`prompts/reports/infer_instrument.md`) with one batch of items + the
substrate-resolved excerpts inline. Returns one TextBlock containing
strict JSON; this module parses + validates the JSON and returns a
`BatchResult` for the caller to compose with `score_instrument()`.

Batching strategy (R3 from eng-review): caller declares how the
instrument's items split into batches. Single-subscale instruments
(PHQ-9, GAD-7, WHO-5, MEQ-19 in the wedge) run as one batch covering
all items. Multi-subscale post-wedge instruments (IPIP-NEO 30 facets,
HEXACO 6 domains) split into one batch per facet/domain so the
agent's structured-JSON output stays robust at scale. Wedge runs the
machinery trivially (1 batch); the machinery is the migration path
for personality.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections.abc import AsyncIterable
from dataclasses import dataclass, field
from pathlib import Path

# Project root on sys.path so `scripts.*` imports resolve when this
# module is imported via the engine's normal `scripts.reports.*` path.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from claude_agent_sdk import (  # noqa: E402
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    UserMessage,
    query,
)

from scripts.core.sdk_helpers import (  # noqa: E402
    StderrCapture,
    classify_failure,
    log_sdk_failure,
    make_path_scope_gate,
    prompt_stream,
)
from scripts.reports._engine.instrument import Instrument, LikertItem  # noqa: E402


# Wedge composition — locked by S01-T01 empirical verification. Do not
# add Write/Edit/Bash here under any circumstance; the empty-roots
# path-scope-gate is defense-in-depth, and Bash-escalation-via-sed was
# observed during the probe (model attempted it spontaneously). See
# `.ytstack/KNOWLEDGE.md` 'M019 R1 wiring' for the full finding.
WEDGE_ALLOWED_TOOLS: tuple[str, ...] = ("Read", "Glob", "Grep")
WEDGE_DISALLOWED_TOOLS: tuple[str, ...] = ("Write", "Edit", "NotebookEdit")

# Model picked for the wedge — Opus 4.7 is overkill for clinical
# screens (PHQ-9 needs reading comprehension, not deep reasoning) and
# would burn budget unnecessarily on weekly runs. Haiku is fast +
# cheap + 200K context capable. Override via the `model` kwarg if a
# specific instrument needs more.
DEFAULT_INFERENCE_MODEL = "claude-haiku-4-5"

# Max turns for one inference call. The agent typically Reads N
# substrate files (one Read per file via Glob+Read or per-batch
# concatenated context) then emits the JSON in a single TextBlock.
# 10 turns is generous; the probe in S01-T01 used 3 and that was tight.
DEFAULT_MAX_TURNS = 10


@dataclass
class EvidenceRecord:
    """Single substrate citation backing one item-answer.

    Provenance contract: every interpretive claim in the inference
    output must cite at least one substrate path. The agent fills
    `file`, `quote`, and optionally `line`. `weight` is reserved for
    post-wedge multi-evidence aggregation (analyst layer may weight
    citations); wedge defaults to 1.0 uniformly.
    """

    file: str
    quote: str
    line: int | None = None
    weight: float = 1.0

    @classmethod
    def from_json(cls, raw: dict) -> "EvidenceRecord":
        return cls(
            file=str(raw.get("file", "")),
            quote=str(raw.get("quote", "")),
            line=int(raw["line"]) if raw.get("line") is not None else None,
            weight=float(raw.get("weight", 1.0)),
        )


@dataclass
class ItemInference:
    """Agent's structured output for one item in a batch.

    `answer is None` means the agent declined to infer — either the
    item is `substrate_inferable: false` (interior state, must be
    operator-input) or the agent could not find enough evidence to
    answer at any confidence level. `confidence` is 0.0 in both cases.
    """

    item_id: str
    answer: int | None
    confidence: float
    evidence: list[EvidenceRecord]
    reasoning: str

    @classmethod
    def from_json(cls, item_id: str, raw: dict) -> "ItemInference":
        answer_val = raw.get("answer")
        return cls(
            item_id=item_id,
            answer=int(answer_val) if answer_val is not None else None,
            confidence=float(raw.get("confidence", 0.0)),
            evidence=[
                EvidenceRecord.from_json(ev) for ev in (raw.get("evidence") or [])
            ],
            reasoning=str(raw.get("reasoning", "")).strip(),
        )


@dataclass
class BatchResult:
    """One batched inference call's outcome.

    `items` keys are item_ids (string form, matches items.yaml). The
    caller composes one or more BatchResults into a full instrument
    inference set, then hands the answers dict (`{item_id: int | None}`)
    to `score_instrument()` for deterministic scoring.
    """

    items: dict[str, ItemInference]
    elapsed_ms: int
    model_id: str
    prompt_version: str            # SHA256 of the rendered prompt
    cost_usd: float
    batch_label: str = "all"       # human-readable batch identifier


@dataclass
class InferenceBatch:
    """One batching unit — subset of an instrument's items handed to
    the agent in a single SDK call.

    Single-subscale instruments use one batch with all items + label
    "all". Multi-subscale instruments use one batch per
    subscale/domain.
    """

    label: str
    items: tuple[LikertItem, ...]

    @property
    def item_ids(self) -> list[str]:
        return [it.id for it in self.items]


def default_batches(instrument: Instrument) -> list[InferenceBatch]:
    """Default batching = one batch per subscale, or one batch total.

    For wedge instruments (PHQ-9: no subscales), returns one batch
    containing all items. For ASRS-v1.1 (Part A + Part B subscales),
    returns two batches.
    """
    by_subscale: dict[str | None, list[LikertItem]] = {}
    for it in instrument.items:
        by_subscale.setdefault(it.subscale, []).append(it)
    if len(by_subscale) == 1 and None in by_subscale:
        return [InferenceBatch(label="all", items=tuple(instrument.items))]
    return [
        InferenceBatch(
            label=(subscale if subscale is not None else "ungrouped"),
            items=tuple(items),
        )
        for subscale, items in by_subscale.items()
    ]


class InferenceError(RuntimeError):
    """Raised when an inference call fails in a way the caller must
    surface (SDK crash, schema-invalid output, scope-lock violation).
    """


def _validate_json_schema(
    parsed: dict, expected_item_ids: list[str], batch_label: str
) -> None:
    """Reject malformed agent output before turning it into ItemInference."""
    if not isinstance(parsed, dict):
        raise InferenceError(
            f"batch {batch_label!r}: agent output is not a JSON object"
        )
    items_section = parsed.get("items")
    if not isinstance(items_section, dict):
        raise InferenceError(
            f"batch {batch_label!r}: missing/invalid 'items' object in output"
        )
    returned_ids = set(items_section.keys())
    expected_ids = set(expected_item_ids)
    missing = expected_ids - returned_ids
    extra = returned_ids - expected_ids
    if missing:
        raise InferenceError(
            f"batch {batch_label!r}: agent omitted items {sorted(missing)}"
        )
    if extra:
        raise InferenceError(
            f"batch {batch_label!r}: agent returned unknown items {sorted(extra)}"
        )


def _extract_json_from_textblocks(text: str) -> dict:
    """Find the JSON object in the agent's text output.

    The prompt asks for strict JSON; in practice models sometimes
    wrap it in ```json fences or pad with prose. This pulls the first
    top-level `{...}` block and tries `json.loads` on progressively
    larger prefixes. If parsing fails entirely, raises.
    """
    # Try the whole thing first.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find first `{` and try to balance braces.
    start = text.find("{")
    if start < 0:
        raise InferenceError("agent output contained no JSON object")
    depth = 0
    end = -1
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        raise InferenceError("agent output had unbalanced JSON braces")
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError as exc:
        raise InferenceError(f"agent output JSON failed to parse: {exc}") from exc


async def infer_batch_async(
    rendered_prompt: str,
    batch: InferenceBatch,
    *,
    vault_cwd: Path,
    prompt_version: str,
    model: str = DEFAULT_INFERENCE_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> BatchResult:
    """Run one inference batch end-to-end with one-shot retry on
    bundled-CLI silent crashes (kind=unknown / cli_crash).

    Mirrors compile.py's retry-on-kind=unknown pattern. Random
    bundled-CLI exit-1-empty-stderr is unfortunately common on the
    happy path; a single retry usually succeeds. Auth/rate-limit/
    cost-cap failures are NOT retried — those need operator
    intervention.
    """
    import logging
    log = logging.getLogger("reports.inference")
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            return await _infer_batch_once_async(
                rendered_prompt,
                batch,
                vault_cwd=vault_cwd,
                prompt_version=prompt_version,
                model=model,
                max_turns=max_turns,
            )
        except InferenceError as exc:
            last_exc = exc
            # Retry on: (1) opaque CLI failures (kind=unknown / cli_crash),
            # (2) schema-validation failures (agent omitted items / extra
            # items / non-JSON output). Haiku occasionally drops one item
            # despite the prompt's "every item MUST appear" instruction;
            # re-roll usually produces the full set. Auth/rate-limit
            # errors are explicitly NOT retried.
            msg = str(exc)
            retryable = (
                "unknown:" in msg or "cli_crash:" in msg
                or "agent omitted items" in msg
                or "agent returned unknown items" in msg
                or "agent output JSON failed to parse" in msg
                or "agent output had unbalanced JSON braces" in msg
                or "agent output contained no JSON object" in msg
            )
            if attempt == 0 and retryable:
                log.warning(
                    "  inference batch=%s failed with retryable error; "
                    "retrying once after 2s …",
                    batch.label,
                )
                import asyncio
                await asyncio.sleep(2.0)
                continue
            raise
    assert last_exc is not None
    raise last_exc


async def _infer_batch_once_async(
    rendered_prompt: str,
    batch: InferenceBatch,
    *,
    vault_cwd: Path,
    prompt_version: str,
    model: str = DEFAULT_INFERENCE_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> BatchResult:
    """One attempt of an inference batch. Internal — callers use
    `infer_batch_async` which wraps this with retry-once-on-unknown."""
    import logging

    log = logging.getLogger("reports.inference")
    started_wall = time.time()
    start = time.perf_counter()
    text_chunks: list[str] = []
    cost = 0.0
    capture = StderrCapture()

    options = ClaudeAgentOptions(
        cwd=str(vault_cwd),
        model=model,
        allowed_tools=list(WEDGE_ALLOWED_TOOLS),
        disallowed_tools=list(WEDGE_DISALLOWED_TOOLS),
        permission_mode="default",
        max_turns=max_turns,
        setting_sources=["project"],
        can_use_tool=make_path_scope_gate([]),
        stderr=capture.callback,
    )

    try:
        async for message in query(
            prompt=prompt_stream(rendered_prompt), options=options
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if type(block).__name__ == "TextBlock":
                        text_chunks.append(getattr(block, "text", ""))
            elif isinstance(message, UserMessage):
                # Tool results — agent's Reads come back here. Don't
                # need to capture them; the JSON output references
                # them by path.
                continue
            elif isinstance(message, ResultMessage):
                cost = float(getattr(message, "total_cost_usd", 0.0) or 0.0)
    except Exception as exc:
        failure = log_sdk_failure(
            log,
            label=f"reports.inference batch={batch.label}",
            started=started_wall,
            capture=capture,
            exc=exc,
            model=model,
            input_chars=len(rendered_prompt),
            extra={"prompt_version": prompt_version},
        )
        raise InferenceError(
            f"inference call failed for batch {batch.label!r}: {failure}"
        ) from exc

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    full_text = "".join(text_chunks)
    parsed = _extract_json_from_textblocks(full_text)
    _validate_json_schema(parsed, batch.item_ids, batch.label)
    items: dict[str, ItemInference] = {}
    for item in batch.items:
        items[item.id] = ItemInference.from_json(item.id, parsed["items"][item.id])

    return BatchResult(
        items=items,
        elapsed_ms=elapsed_ms,
        model_id=model,
        prompt_version=prompt_version,
        cost_usd=cost,
        batch_label=batch.label,
    )


def infer_batch(
    rendered_prompt: str,
    batch: InferenceBatch,
    *,
    vault_cwd: Path,
    prompt_version: str,
    model: str = DEFAULT_INFERENCE_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> BatchResult:
    """Sync wrapper around `infer_batch_async`."""
    return asyncio.run(
        infer_batch_async(
            rendered_prompt,
            batch,
            vault_cwd=vault_cwd,
            prompt_version=prompt_version,
            model=model,
            max_turns=max_turns,
        )
    )


@dataclass
class InferenceRun:
    """Composition of one or more BatchResults covering a full instrument."""

    instrument_slug: str
    instrument_version: str
    batches: list[BatchResult] = field(default_factory=list)

    @property
    def answers(self) -> dict[str, int | None]:
        """Flatten the per-batch results into one answers dict."""
        merged: dict[str, int | None] = {}
        for br in self.batches:
            for item_id, inf in br.items.items():
                merged[item_id] = inf.answer
        return merged

    @property
    def per_item(self) -> dict[str, ItemInference]:
        """Flatten the per-batch results into one item-id-keyed dict."""
        merged: dict[str, ItemInference] = {}
        for br in self.batches:
            merged.update(br.items)
        return merged

    @property
    def total_cost_usd(self) -> float:
        return sum(b.cost_usd for b in self.batches)

    @property
    def total_elapsed_ms(self) -> int:
        return sum(b.elapsed_ms for b in self.batches)
