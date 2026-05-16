"""Dream-cycle: periodic cross-time re-synthesis of entity pages (M014 MVP).

Where `compile.py` is per-file distillation (one substrate file → one or more
knowledge/ updates), dream-cycle is cross-time synthesis: it picks ONE entity
(person / project / area), greps all substrate mentioning that entity (or
naming it as `author:`), and rewrites the entity's State block + appends to
Timeline from the full corpus.

The cross-time view surfaces recurring themes, drifting roles, and emerging
concept-clusters that per-file compile cannot see (each compile pass sees ONE
file + index.md).

CLI surface:

    wiki dream-entity <slug>            # re-synthesize one entity
    wiki dream --all-entities           # sweep everyone, respecting cooldown
    wiki dream-entity <slug> --dry-run  # print corpus + estimated cost, no SDK call

Piggyback wiring: see `flush.py:_LEGACY_PIGGYBACK_COMMANDS["dream_cycle"]`.
The piggyback shells out to `dream.py --piggyback`, which sweeps the N
most-overdue entities under the per-run cost cap.

Cost gates (real, hard, no silent skips):

  - Per-entity cap: `CONFIG.limits.dream_entity_max_cost_usd`. Pre-flight
    estimate from prompt-char count; reject if estimate > cap.
  - Per-run cap (piggyback / --all): `CONFIG.limits.dream_cycle_max_cost_per_run_usd`.
    Stop sweeping once cumulative cost crosses the cap.

Cooldown: `CONFIG.scheduling.dream_cooldown_days` (default 7). Entities with
`last_synthesized_at:` newer than that are skipped.

Provider: Claude Agent SDK only — never Ollama. (See feedback memory
`feedback_no_silent_provider_fallback`.)
"""

from __future__ import annotations

import os

os.environ.setdefault("CLAUDE_INVOKED_BY", "dream")

import argparse
import asyncio
import logging
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    query,
)

from core.config import CONFIG
from core.paths import (
    AREAS_DIR,
    INDEX_FILE,
    KNOWLEDGE_DIR,
    LOG_FILE,
    PEOPLE_DIR,
    PROJECTS_DIR,
    RAW_DIR,
    ROOT_DIR,
    DAILY_DIR,
)
from core.prompts import render
from core.sdk_helpers import StderrCapture, log_sdk_failure
from core.utils import now_iso, today_iso


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("dream")


# ── Constants ─────────────────────────────────────────────────────────

# Rough Opus pricing: input $15/Mtok, output $75/Mtok (Opus 4.7 published rates).
# Dream-cycle prompts are input-dominated (large corpus, small output).
# Estimate: input_chars / 4 chars/token × $15/Mtok + small fixed output budget.
# Conservative — actual cost can be 1.5-2× higher with tool-turn fan-out.
_INPUT_USD_PER_MTOK = 15.0
_OUTPUT_USD_PER_MTOK = 75.0
_OUTPUT_BUDGET_TOKENS = 6000  # generous ceiling for a State+Timeline rewrite
_CHARS_PER_TOKEN = 4.0  # English/German mix; conservative

# Map entity-kind (the folder slug) to the kind's directory + type-frontmatter
# value. Areas use the M005 areas-bucket folder (knowledge/areas/) and a
# flatter shape — dream-cycle still works because the prompt explicitly
# handles that case (no Action Items section).
_ENTITY_KINDS: dict[str, tuple[Path, str]] = {
    "people": (PEOPLE_DIR, "person"),
    "projects": (PROJECTS_DIR, "project"),
    "areas": (AREAS_DIR, "area"),
}


# ── Helpers ────────────────────────────────────────────────────────────


@dataclass
class EntityRef:
    slug: str
    kind: str  # "people" | "projects" | "areas"
    page: Path  # absolute
    type_value: str  # "person" | "project" | "area"

    @property
    def title(self) -> str:
        return self.slug.replace("-", " ").title()

    @property
    def link(self) -> str:
        return f"knowledge/{self.kind}/{self.slug}"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a markdown file into (frontmatter dict, body). Tolerant."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    block = text[4:end]
    body = text[end + 5 :]
    try:
        fm = yaml.safe_load(block) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, body


def _resolve_entity(slug: str) -> EntityRef | None:
    """Find the entity page under knowledge/{people,projects,areas}/<slug>.md."""
    for kind, (dir_, type_value) in _ENTITY_KINDS.items():
        page = dir_ / f"{slug}.md"
        if page.exists():
            return EntityRef(slug=slug, kind=kind, page=page, type_value=type_value)
    return None


def _list_all_entities() -> list[EntityRef]:
    """Walk knowledge/{people,projects,areas}/ for every entity page."""
    out: list[EntityRef] = []
    for kind, (dir_, type_value) in _ENTITY_KINDS.items():
        if not dir_.exists():
            continue
        for page in sorted(dir_.glob("*.md")):
            slug = page.stem
            out.append(
                EntityRef(slug=slug, kind=kind, page=page, type_value=type_value)
            )
    return out


# ── Cooldown ──────────────────────────────────────────────────────────


def _parse_iso_date(value: object) -> datetime | None:
    """Best-effort ISO date parse. Accepts date, datetime, or ISO string."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        # datetime.date — promote to UTC midnight
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
        except ValueError:
            return None
    return None


def _last_synth_age_days(entity: EntityRef, *, now: datetime | None = None) -> float | None:
    """Return age in days since last synthesis, or None if never synthesized."""
    if not entity.page.exists():
        return None
    fm, _body = _parse_frontmatter(entity.page.read_text(encoding="utf-8"))
    when = _parse_iso_date(fm.get("last_synthesized_at"))
    if when is None:
        return None
    ref = now or datetime.now(timezone.utc)
    return max(0.0, (ref - when).total_seconds() / 86400.0)


def is_within_cooldown(entity: EntityRef, *, cooldown_days: int | None = None) -> bool:
    """True iff the entity was synthesized within the cooldown window."""
    days = cooldown_days if cooldown_days is not None else CONFIG.scheduling.dream_cooldown_days
    if days <= 0:
        return False
    age = _last_synth_age_days(entity)
    return age is not None and age < days


# ── Corpus assembly ──────────────────────────────────────────────────


_SUBSTRATE_ROOTS: tuple[Path, ...] = (RAW_DIR, DAILY_DIR)


def _is_substrate_file(path: Path) -> bool:
    if path.suffix.lower() != ".md":
        return False
    rel = path.resolve()
    for root in _SUBSTRATE_ROOTS:
        try:
            rel.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def _mentions_entity(text: str, slug: str) -> bool:
    """Match slug as a whole word OR as the value of author/compiled_from."""
    pattern = re.compile(rf"(?<![a-z0-9_-]){re.escape(slug)}(?![a-z0-9_-])", re.IGNORECASE)
    return bool(pattern.search(text))


def collect_corpus(entity: EntityRef, *, vault_root: Path | None = None) -> list[Path]:
    """Greps every substrate file under raw/** and daily/** for slug mentions.

    Returns sorted-newest-first list of absolute paths. Walks the filesystem
    directly rather than shelling out to grep so it's deterministic in tests
    and works on any platform.
    """
    root = vault_root or ROOT_DIR
    found: list[tuple[float, Path]] = []
    for sub in (root / "raw", root / "daily"):
        if not sub.exists():
            continue
        for path in sub.rglob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if _mentions_entity(text, entity.slug):
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    mtime = 0.0
                found.append((mtime, path))
    found.sort(key=lambda t: t[0], reverse=True)
    return [p for _ts, p in found]


def render_corpus_block(
    paths: list[Path], *, vault_root: Path | None = None, max_chars_per_file: int = 8000
) -> str:
    """Render the corpus as a single markdown block for prompt embedding.

    Each file gets a `### path` header + a triple-fenced block of its
    content. Per-file truncation cap at `max_chars_per_file` to keep one
    pathological 500 KB substrate file from blowing the budget alone.
    """
    root = vault_root or ROOT_DIR
    chunks: list[str] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(path.relative_to(root))
        if len(text) > max_chars_per_file:
            text = text[:max_chars_per_file] + f"\n\n[... truncated at {max_chars_per_file} chars ...]\n"
        chunks.append(f"### `{rel}`\n\n```markdown\n{text}\n```\n")
    return "\n".join(chunks)


# ── Cost estimation ─────────────────────────────────────────────────


def estimate_cost_usd(prompt_chars: int) -> float:
    """Rough pre-flight cost estimate from prompt size + fixed output budget.

    Conservative — actual cost can run 1.5-2× higher when tool-turn fan-out
    re-reads articles. The estimate gates the SDK call BEFORE spend; the
    real cost is measured via ResultMessage.total_cost_usd after.
    """
    input_tokens = prompt_chars / _CHARS_PER_TOKEN
    input_cost = input_tokens * _INPUT_USD_PER_MTOK / 1_000_000.0
    output_cost = _OUTPUT_BUDGET_TOKENS * _OUTPUT_USD_PER_MTOK / 1_000_000.0
    return round(input_cost + output_cost, 4)


# ── Main entity-pass ──────────────────────────────────────────────


@dataclass
class DreamResult:
    entity: EntityRef
    corpus_count: int
    corpus_chars: int
    estimated_cost_usd: float
    actual_cost_usd: float
    input_tokens: int
    output_tokens: int
    sdk_result_text: str
    skipped: str | None = None  # None = success
    elapsed_s: float = 0.0


def _read_facts_md() -> str:
    """Lazy import — pulls in the FACTS_DIR walker."""
    from core.utils import read_hard_facts

    return read_hard_facts()


def _build_owner_block() -> str:
    """Same owner-block rendering as compile.py."""
    from compile import _build_owner_block as _from_compile

    return _from_compile()


def _build_prompt(entity: EntityRef, corpus_paths: list[Path], *, max_turns: int) -> tuple[str, int]:
    """Render dream_entity.md with the entity + corpus. Returns (prompt, total_chars)."""
    current_page = entity.page.read_text(encoding="utf-8") if entity.page.exists() else "(file does not exist yet — create it from the two-layer template)"
    corpus_block = render_corpus_block(corpus_paths)
    corpus_chars = len(corpus_block)
    title = current_page_title(current_page) or entity.title
    prompt = render(
        "dream_entity",
        entity_slug=entity.slug,
        entity_title=title,
        entity_type=entity.type_value,
        entity_page=str(entity.page.relative_to(ROOT_DIR)),
        current_page=current_page,
        corpus_block=corpus_block,
        corpus_count=len(corpus_paths),
        corpus_chars=corpus_chars,
        owner_block=_build_owner_block(),
        facts_md=_read_facts_md(),
        max_turns=max_turns,
        today=today_iso(),
        now=now_iso(),
        entity_link=entity.link,
    )
    return prompt, len(prompt)


def current_page_title(page_text: str) -> str | None:
    fm, _body = _parse_frontmatter(page_text)
    val = fm.get("title")
    return str(val) if val else None


async def dream_entity(
    entity: EntityRef,
    *,
    dry_run: bool = False,
    cost_cap_usd: float | None = None,
    max_turns: int | None = None,
) -> DreamResult:
    """Re-synthesize ONE entity page from the substrate corpus.

    Cost gate: pre-flight estimate; on overrun returns a DreamResult with
    `skipped="cost_cap_exceeded"` and zero spend (the SDK is NEVER called
    when the cap fires — no silent burn).
    """
    started = time.time()
    cap = cost_cap_usd if cost_cap_usd is not None else CONFIG.limits.dream_entity_max_cost_usd
    turns = max_turns if max_turns is not None else 20

    corpus_paths = collect_corpus(entity)
    log.info(
        "  entity=%s kind=%s — %d substrate files mention this slug",
        entity.slug, entity.kind, len(corpus_paths),
    )

    if not corpus_paths:
        log.warning(
            "  no substrate mentions %s — nothing to synthesize (skipping)",
            entity.slug,
        )
        return DreamResult(
            entity=entity, corpus_count=0, corpus_chars=0,
            estimated_cost_usd=0.0, actual_cost_usd=0.0,
            input_tokens=0, output_tokens=0, sdk_result_text="",
            skipped="no_substrate", elapsed_s=time.time() - started,
        )

    prompt, prompt_chars = _build_prompt(entity, corpus_paths, max_turns=turns)
    estimate = estimate_cost_usd(prompt_chars)
    log.info(
        "  prompt: %d chars (%.1f KB) — estimated cost $%.3f (cap $%.2f)",
        prompt_chars, prompt_chars / 1024, estimate, cap,
    )

    if cap > 0 and estimate > cap:
        msg = (
            f"COST_CAP_EXCEEDED: entity={entity.slug} estimate=${estimate:.3f} "
            f"> cap=${cap:.2f} (prompt={prompt_chars} chars, corpus={len(corpus_paths)} files). "
            "Reduce corpus by archiving old substrate, raise CONFIG.limits.dream_entity_max_cost_usd, "
            "or run with --no-cost-cap (not yet implemented — file the request)."
        )
        log.error("  %s", msg)
        return DreamResult(
            entity=entity, corpus_count=len(corpus_paths),
            corpus_chars=sum(len(p.read_text(encoding="utf-8", errors="replace")) for p in corpus_paths),
            estimated_cost_usd=estimate, actual_cost_usd=0.0,
            input_tokens=0, output_tokens=0, sdk_result_text=msg,
            skipped="cost_cap_exceeded", elapsed_s=time.time() - started,
        )

    if dry_run:
        log.info("  --dry-run: would invoke SDK with %d-char prompt", prompt_chars)
        return DreamResult(
            entity=entity, corpus_count=len(corpus_paths),
            corpus_chars=prompt_chars, estimated_cost_usd=estimate,
            actual_cost_usd=0.0, input_tokens=0, output_tokens=0,
            sdk_result_text="(dry-run)", skipped="dry_run",
            elapsed_s=time.time() - started,
        )

    # Real SDK call. Single attempt — dream is a periodic pass; if it fails,
    # the next pass picks the entity up again.
    model = CONFIG.models.compile_model
    log.info("  invoking %s (max_turns=%d, system=dream_entity_system)", model, turns)

    input_tokens = 0
    output_tokens = 0
    result_text = ""
    actual_cost = 0.0
    capture = StderrCapture()

    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                max_buffer_size=CONFIG.limits.sdk_max_buffer_size_mb * 1024 * 1024,
                cwd=str(ROOT_DIR),
                model=model,
                allowed_tools=[
                    "Read", "Glob", "Grep",
                    "Write(knowledge/**)",
                    "Edit(knowledge/**)",
                ],
                permission_mode="acceptEdits",
                max_turns=turns,
                system_prompt=render("dream_entity_system"),
                setting_sources=["project"],
                stderr=capture.callback,
            ),
        ):
            if isinstance(message, AssistantMessage) and message.usage:
                input_tokens += message.usage.get("input_tokens", 0)
                output_tokens += message.usage.get("output_tokens", 0)
            if isinstance(message, ResultMessage):
                result_text = message.result or ""
                actual_cost = float(getattr(message, "total_cost_usd", 0.0) or 0.0)
    except Exception as exc:  # noqa: BLE001 — classifier handles all paths
        log_sdk_failure(
            log,
            label=f"dream_entity:{entity.slug}",
            source=str(entity.page.relative_to(ROOT_DIR)),
            model=model,
            input_chars=prompt_chars,
            started=started,
            capture=capture,
            exc=exc,
        )
        return DreamResult(
            entity=entity, corpus_count=len(corpus_paths),
            corpus_chars=prompt_chars, estimated_cost_usd=estimate,
            actual_cost_usd=0.0, input_tokens=input_tokens, output_tokens=output_tokens,
            sdk_result_text=str(exc), skipped="sdk_failure",
            elapsed_s=time.time() - started,
        )

    elapsed = time.time() - started
    log.info(
        "  done: %d input + %d output tokens, actual cost $%.4f, elapsed %.1fs",
        input_tokens, output_tokens, actual_cost, elapsed,
    )
    return DreamResult(
        entity=entity, corpus_count=len(corpus_paths),
        corpus_chars=prompt_chars, estimated_cost_usd=estimate,
        actual_cost_usd=actual_cost, input_tokens=input_tokens,
        output_tokens=output_tokens, sdk_result_text=result_text,
        skipped=None, elapsed_s=elapsed,
    )


# ── Sweep across entities ─────────────────────────────────────────


async def dream_all_entities(
    *,
    cooldown_days: int | None = None,
    per_entity_cap: float | None = None,
    per_run_cap: float | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> list[DreamResult]:
    """Sweep all entities, oldest-synthesized first, respecting caps + cooldown."""
    cd = cooldown_days if cooldown_days is not None else CONFIG.scheduling.dream_cooldown_days
    run_cap = per_run_cap if per_run_cap is not None else CONFIG.limits.dream_cycle_max_cost_per_run_usd

    all_entities = _list_all_entities()
    # Filter out cooldown'd entities + sort by age (oldest synthesis first;
    # never-synthesized counts as infinity).
    ranked: list[tuple[float, EntityRef]] = []
    for ent in all_entities:
        if is_within_cooldown(ent, cooldown_days=cd):
            continue
        age = _last_synth_age_days(ent)
        score = age if age is not None else float("inf")
        ranked.append((score, ent))
    ranked.sort(key=lambda t: t[0], reverse=True)

    log.info(
        "Dream sweep: %d entities total, %d after cooldown filter (cooldown=%dd, run_cap=$%.2f)",
        len(all_entities), len(ranked), cd, run_cap,
    )

    results: list[DreamResult] = []
    cumulative = 0.0
    for idx, (_age, ent) in enumerate(ranked, 1):
        if limit is not None and idx > limit:
            log.info("Reached --limit=%d; stopping", limit)
            break
        if run_cap > 0 and cumulative >= run_cap:
            log.info(
                "Per-run cost cap reached ($%.2f >= $%.2f) — stopping after %d entities",
                cumulative, run_cap, idx - 1,
            )
            break
        log.info("[%d/%d] dream-entity %s", idx, len(ranked), ent.slug)
        res = await dream_entity(
            ent, dry_run=dry_run, cost_cap_usd=per_entity_cap,
        )
        results.append(res)
        cumulative += res.actual_cost_usd

    log.info(
        "Dream sweep finished: %d entities processed, cumulative cost $%.4f",
        len(results), cumulative,
    )
    return results


# ── CLI ───────────────────────────────────────────────────────────


async def _async_main() -> int:
    parser = argparse.ArgumentParser(description="Dream-cycle entity re-synthesis (M014)")
    sub = parser.add_subparsers(dest="cmd")

    p_one = sub.add_parser("entity", help="Re-synthesize one entity by slug")
    p_one.add_argument("slug", help="Entity slug (e.g. alex, emmett, yesterday-os)")
    p_one.add_argument("--dry-run", action="store_true", help="Print prompt + estimate, no SDK call")
    p_one.add_argument("--cost-cap", type=float, default=None, help="Override per-entity USD cap")
    p_one.add_argument("--max-turns", type=int, default=20, help="SDK max_turns budget")
    p_one.add_argument("--ignore-cooldown", action="store_true", help="Skip the last_synthesized_at gate")

    p_all = sub.add_parser("sweep", help="Sweep all entities (--all-entities)")
    p_all.add_argument("--dry-run", action="store_true")
    p_all.add_argument("--cooldown-days", type=int, default=None)
    p_all.add_argument("--per-entity-cap", type=float, default=None)
    p_all.add_argument("--per-run-cap", type=float, default=None)
    p_all.add_argument("--limit", type=int, default=None, help="Hard cap on entity count this run")

    p_pb = sub.add_parser("piggyback", help="Piggyback wrapper — runs sweep with config defaults")
    p_pb.add_argument("--limit", type=int, default=None)

    args = parser.parse_args()

    if args.cmd == "entity":
        ent = _resolve_entity(args.slug)
        if ent is None:
            log.error(
                "No entity page found for slug %r under knowledge/{people,projects,areas}/. "
                "Check the slug or create the page first via per-file compile.",
                args.slug,
            )
            return 2
        if not args.ignore_cooldown and is_within_cooldown(ent):
            age = _last_synth_age_days(ent)
            cooldown = CONFIG.scheduling.dream_cooldown_days
            log.info(
                "Skipping %s: last_synthesized_at is %.1f days old < cooldown %dd. "
                "Re-run with --ignore-cooldown to force.",
                ent.slug, age or 0.0, cooldown,
            )
            return 0
        res = await dream_entity(
            ent, dry_run=args.dry_run, cost_cap_usd=args.cost_cap,
            max_turns=args.max_turns,
        )
        if res.skipped == "cost_cap_exceeded":
            return 3
        if res.skipped == "sdk_failure":
            return 4
        return 0

    if args.cmd == "sweep":
        results = await dream_all_entities(
            cooldown_days=args.cooldown_days,
            per_entity_cap=args.per_entity_cap,
            per_run_cap=args.per_run_cap,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        # Non-zero exit if any entity hit a real failure (cost-cap or SDK)
        for r in results:
            if r.skipped in ("cost_cap_exceeded", "sdk_failure"):
                return 5
        return 0

    if args.cmd == "piggyback":
        results = await dream_all_entities(limit=args.limit)
        for r in results:
            if r.skipped == "sdk_failure":
                return 5
        return 0

    parser.print_help()
    return 1


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    sys.exit(main())
