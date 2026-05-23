"""Route — the discriminated decision compile_file makes per source (M026).

`decide_route(source, content) → Route` returns one of these variants *before* any
I/O or LLM call. `compile_file` then `match`es on the variant and dispatches to the
matching execution handler. Full design: `.ytstack/backlog/compile-dispatch-seam.md`.

This module also owns the pure dispatch tables + frontmatter helpers that the
decision needs (moved here from `compile.py` in M026-S02 so `decide_route` can be
pure and self-contained). It imports `core.*`, `.classify`, `.types`; none of those
import `route`, so there is no cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.compile_role import infer_compile_role
from core.config import CONFIG
from core.paths import ROOT_DIR
from core.utils import extract_wikilinks

from .classify import ClassifyResult, classify
from .types import CompileMetadata


# ── Substrate dispatch tables (moved from compile.py, M026-S02) ───────

SUBSTRATE_PROMPTS: dict[str, tuple[str, int, str | None]] = {
    # Calendar + daily are mechanical Glob/Edit work — no reasoning depth
    # required. Routing to Haiku 4.5 (~6× cheaper than Opus) drops cost
    # from $2-3/file to $0.30-0.50 while keeping the same dispatch.
    # Empirical: 2026-02-26 (dense, 37 link-signals) hit max_turns=8 at
    # $2.38 on Opus → Haiku at 12 turns expected to finish under $0.60.
    "calendar-rollup": ("compile_calendar", 12, "claude-haiku-4-5-20251001"),
    # Daily-digest references more entities than calendar (people +
    # projects + concepts, not just attendees + recurring-concepts).
    # Empirical: 12-turn budget hit at $1.14 (Opus) with 2 entities
    # edited. 20 + Haiku covers digests with up to ~6 mentioned entities
    # well under budget.
    "daily-digest":    ("compile_daily", 20, "claude-haiku-4-5-20251001"),
    # Health-rollup is metric-only frontmatter with a stub body ~99% of
    # days. Falling through to compile_main.md spawned the heavy
    # two-layer carry-forward audit on a file with no dialog → cost
    # exceeded $2-3/file on 2026-05-16. The lean prompt executes the
    # established `concepts/health-rollup-intake-format` policy
    # directly: append to compiled_from + emit one log entry. Operator
    # body-prose branch keeps Timeline-append shape (no State writes).
    # 10 turns: 4 mandatory tool calls (Read+Edit policy article,
    # Read+Edit log.md, dictated by Claude Code's Edit-after-Read
    # safety rule) + final emit = 5 minimum, plus slack for Glob /
    # re-Read / prose-branch Timeline appends. Empirical: budget=6
    # consistently hit max_turns on 2026-05-16 batch.
    "health-rollup":   ("compile_health", 10, "claude-haiku-4-5-20251001"),
    # Screenshot batches: 50-screenshot reports with per-frame summaries
    # + table-of-contents. compile_main.md hit max_turns at $5+/file
    # on 2026-05-15 (49 screenshots → many concept-page Edits). Lean
    # prompt focuses on concept-extraction + source_screenshots tagging.
    # Haiku at 15 turns expected to fit comfortably; the source is
    # routinely 50-100 KB but Haiku 4.5 has 200K context.
    "screenshot-batch": ("compile_screenshots", 30, "claude-haiku-4-5-20251001"),
    # Camera/phone-photo batches (collectors/pictures.py). Picture-shaped
    # fields (scene_description / objects / action / text_visible) and a
    # much tighter anti-noise filter — most camera photos become zero
    # knowledge entries. 20 turns + Haiku covers the rare actionable
    # batch (whiteboard captures, receipts, document scans).
    "picture-batch":    ("compile_pictures", 20, "claude-haiku-4-5-20251001"),
    # Memory-sync / memory-seed: engine pre-resolves project_slug +
    # bootstraps `## Timeline` section before SDK (compile_stages.memory),
    # so the prompt is purely mechanical: Read → Edit-append, 2 turns.
    # 5-turn CLI cap = 2 expected + 3-turn safety; no-project-page case
    # short-circuits in Python and never invokes the SDK. Pre-pre-pass
    # arc (2026-05-17): 25 → 8 → 5 as the contract tightened.
    # 2026-05-18: 5 → 20 turns when reversing 2026-05-13 memory-exclusion.
    # The 5-turn budget assumed a pre-resolved project-page Timeline append.
    # The new prompt also handles "no project page → distill to concepts/"
    # which needs more agent moves (Glob existing concepts, Edit-append or
    # Write-new, plus optional connection-article creation).
    "memory-sync":     ("compile_memories", 20, "claude-haiku-4-5-20251001"),
    "memory-seed":     ("compile_memories", 20, "claude-haiku-4-5-20251001"),
    # Longform notes — entity-dense narrative content (strategy docs,
    # design memos, multi-section essays) routinely 15-25 KB with 15-25
    # concept references. compile_default (the lean fallback prompt) +
    # CONFIG.limits.compile_max_turns = 20 was hitting max_turns on
    # outliers; lx-yesterday-strategy-workdoc.md (19.4 KB) burned $0.21
    # on max_turns 2026-05-17. Routed here to compile_main (rich prompt)
    # with 25-turn budget — matches the memory-sync legacy budget and
    # the daily-digest tier for many-entity Haiku substrates.
    "longform":        ("compile_main", 60, "claude-haiku-4-5-20251001"),
}

# Default for any substrate-type NOT in SUBSTRATE_PROMPTS. Lean prompt
# + Haiku + operator-tunable budget. The max_turns is read from CONFIG
# at module-import time so a vault-side bump to
# `limits.compile_max_turns` actually changes the fall-through routing —
# the previous hardcoded `12` made the config knob dead code (operator
# couldn't tune the default via config; only by editing this module).
_DEFAULT_DISPATCH: tuple[str, int, str | None] = (
    "compile_default", CONFIG.limits.compile_max_turns, "claude-haiku-4-5-20251001",
)


# Path-prefix → substrate_key fallback for legacy substrate files that
# don't carry the new `type:` frontmatter yet. Producers SHOULD emit a
# frontmatter type going forward (so SUBSTRATE_PROMPTS lookup hits the
# direct path), but until every existing vault file is backfilled the
# path-pattern fallback keeps compile-dispatch sane. Pattern: matched
# against the source path with `startswith`. Longer-prefix wins on
# overlap; iterate from most-specific to least-specific.
_SUBSTRATE_PATH_FALLBACKS: tuple[tuple[str, str], ...] = (
    ("raw/notes/screenshots/screenshots-", "screenshot-batch"),
    ("raw/notes/pictures/pictures-",       "picture-batch"),
)


# ── Frontmatter helpers (moved from compile.py, M026-S02) ────────────

def _frontmatter_type(content: str) -> str | None:
    """Extract `type:` from a leading YAML frontmatter block, or None.

    Regex-only — sufficient for the single scalar field we need and avoids
    pulling a yaml dependency into the compile hot path. Tolerates quoted
    values and trailing whitespace; matches the first `type:` inside the
    leading `---` … `---` fence, not anywhere else in the body.
    """
    if not content.startswith("---"):
        return None
    end = content.find("\n---", 3)
    if end == -1:
        return None
    block = content[3:end]
    import re
    m = re.search(r"^type:\s*[\"']?([\w-]+)[\"']?\s*$", block, re.MULTILINE)
    return m.group(1) if m else None


def _frontmatter_compile_role(content: str) -> str | None:
    """Extract `compile_role:` from leading YAML frontmatter, or None.

    Sibling to `_frontmatter_type`; same regex-only rationale. Returns the
    raw string value — caller passes it to `core.compile_role.infer_compile_role`
    for enum validation and default-by-location inference (M007-S02-T01).
    """
    if not content.startswith("---"):
        return None
    end = content.find("\n---", 3)
    if end == -1:
        return None
    block = content[3:end]
    import re
    m = re.search(r"^compile_role:\s*[\"']?([\w-]+)[\"']?\s*$", block, re.MULTILINE)
    return m.group(1) if m else None


def _parse_frontmatter(content: str) -> dict:
    """Parse leading YAML frontmatter into a dict. Tolerant; returns {} on
    missing or malformed front-matter. Sibling to the regex-based
    `_frontmatter_type`/`_frontmatter_field` helpers, used for the memory
    pre-pass where we need the full `tags:` list + `project:` scalar
    together (regex would need two passes + list parsing).
    """
    if not content.startswith("---\n"):
        return {}
    end = content.find("\n---\n", 4)
    if end == -1:
        return {}
    block = content[4:end]
    import yaml  # local import keeps module-load cost minimal
    try:
        fm = yaml.safe_load(block) or {}
    except yaml.YAMLError:
        return {}
    return fm if isinstance(fm, dict) else {}


def _frontmatter_field(content: str, key: str) -> str | None:
    """Extract a scalar frontmatter field value by key, or None.

    Generic sibling to `_frontmatter_type`. Tolerates quoted values (`"`, `'`)
    and trailing whitespace; matches first occurrence of `<key>:` inside the
    leading `---` fence. Designed for title-like scalars — does NOT parse
    nested structures or lists (use yaml.safe_load for those).
    """
    if not content.startswith("---"):
        return None
    end = content.find("\n---", 3)
    if end == -1:
        return None
    block = content[3:end]
    import re
    # Allow any non-newline chars in the value (spaces, punctuation, etc.)
    pattern = rf"^{re.escape(key)}:\s*[\"']?(.*?)[\"']?\s*$"
    m = re.search(pattern, block, re.MULTILINE)
    return m.group(1).strip() if m else None


def _substrate_key(source_content: str, rel_path: str) -> str | None:
    """Dispatch key for SUBSTRATE_PROMPTS: frontmatter type, else path-pattern."""
    t = _frontmatter_type(source_content)
    if t:
        return t
    for prefix, key in _SUBSTRATE_PATH_FALLBACKS:
        if rel_path.startswith(prefix):
            return key
    return None


def _health_rollup_body_is_stub(content: str) -> bool:
    """True if a ``type: health-rollup`` body carries no operator prose.

    Bulk-ingested historical days — and the daily Oura rollup before the
    operator annotates it — have a body that is just the ``# Health — <date>``
    heading plus the ``(Add observations below as needed.)`` placeholder. Such
    a metric-only stub is point-in-time biometrics, not knowledge: it is
    recorded deterministically (state mark, no ``knowledge/`` writes) rather
    than spawned through an SDK agent. An operator-prose body returns False and
    falls through to the agent for entity/Timeline extraction.
    """
    if content.startswith("---"):
        end = content.find("\n---", 3)
        body = content[end + 4:] if end != -1 else content
    else:
        body = content
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("# ") or s == "(Add observations below as needed.)":
            continue
        return False
    return True


# ── Route union ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class Skip:
    """No work: empty body / final-only / substrate-skip-list."""

    reason: str


@dataclass(frozen=True)
class IndexOnly:
    """source-and-final file: indexed for discoverability, not distilled.

    `wikilinks` is a tuple so the dataclass stays frozen/hashable-clean. The
    handler that writes the index entry (S03) gets the source `Path` separately.
    """

    title: str
    wikilinks: tuple[str, ...]


@dataclass(frozen=True)
class HealthStub:
    """health-rollup metric stub: recorded deterministically, no agent, $0."""


@dataclass(frozen=True)
class Compile:
    """Needs an LLM call. Carries the upstream dispatch decision + classify result."""

    metadata: CompileMetadata
    classification: ClassifyResult


Route = Skip | IndexOnly | HealthStub | Compile


# ── The decision ─────────────────────────────────────────────────────

def decide_route(source: Path, content: str, *, force: bool = False) -> Route:
    """Pure routing decision for one source — no I/O, no logging, no state.

    Reproduces compile_file's pre-LLM decision in order. The memory pre-pass
    (`resolve_project_slug` + `ensure_timeline_section`) writes a `## Timeline`
    section (I/O), so it stays on the execution side: the `Compile` variant's
    metadata carries `project_slug=None` / `project_page_rel=None`, and the
    `Compile` handler enriches it before the SDK call.

    `force=True` bypasses the substrate-type skip-list (operator targeted a
    single file via `--file`); batch mode passes `force=False`.
    """
    rel_path = (
        str(source.relative_to(ROOT_DIR)) if source.is_absolute() else str(source)
    )

    if not content.strip():
        return Skip("empty")

    # compile_role dispatch (M007). Explicit frontmatter wins; otherwise
    # default-by-location inference.
    explicit_role = _frontmatter_compile_role(content)
    fm_for_role = {"compile_role": explicit_role} if explicit_role else {}
    compile_role = infer_compile_role(
        source,
        fm_for_role,
        default_by_location=CONFIG.limits.compile_role_default_by_location,
        vault_root=ROOT_DIR,
    )
    if compile_role == "final-only":
        return Skip("compile_role_final_only")
    if compile_role == "source-and-final":
        wikilinks = extract_wikilinks(content)
        title = (
            _frontmatter_field(content, "title")
            or source.stem.replace("-", " ").replace("_", " ").title()
        )
        return IndexOnly(title=title, wikilinks=tuple(wikilinks))

    # Substrate-type skip-list (operator can force-compile to bypass).
    skip_type = _frontmatter_type(content)
    if (
        not force
        and skip_type is not None
        and skip_type in CONFIG.limits.compile_skip_substrate_types
    ):
        return Skip(f"substrate_type_excluded_{skip_type}")

    # Deterministic fast-path: health-rollup metric stubs.
    if skip_type == "health-rollup" and _health_rollup_body_is_stub(content):
        return HealthStub()

    # Compile route — substrate-aware prompt/model/max_turns dispatch.
    source_type = _frontmatter_type(content)
    dispatch_key = _substrate_key(content, rel_path)
    substrate_prompt, substrate_max_turns, substrate_model = SUBSTRATE_PROMPTS.get(
        dispatch_key or "", _DEFAULT_DISPATCH,
    )

    # Model precedence (high → low): substrate_model wins → force-long-context
    # tier → size-based escalation → CONFIG.models.compile_model.
    model = substrate_model or CONFIG.models.compile_model
    force_long_ctx = (
        source_type is not None
        and source_type in CONFIG.limits.compile_force_long_context_types
        and CONFIG.models.compile_large_source_model
    )
    if substrate_model:
        # Substrate-specific model wins; don't escalate.
        pass
    elif force_long_ctx:
        model = CONFIG.models.compile_large_source_model
    elif (
        len(content) >= CONFIG.limits.compile_large_source_chars
        and CONFIG.models.compile_large_source_model
    ):
        model = CONFIG.models.compile_large_source_model

    # Turn-budget precedence: per-substrate override → long-context tier →
    # CONFIG default.
    if substrate_max_turns is not None:
        max_turns_for_call = substrate_max_turns
    elif force_long_ctx:
        max_turns_for_call = CONFIG.limits.compile_max_turns_long_context
    else:
        max_turns_for_call = CONFIG.limits.compile_max_turns

    classification = classify(content, source)
    metadata = CompileMetadata(
        source_path=source,
        compile_role=compile_role,
        model_id=model,
        max_turns=max_turns_for_call,
        substrate_type=source_type,
        substrate_prompt=substrate_prompt,
        project_slug=None,
        project_page_rel=None,
    )
    return Compile(metadata=metadata, classification=classification)
