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
import time as _time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    query,
)

from core.paths import (
    CONCEPTS_DIR,
    DAILY_DIR,
    FACTS_DIR,
    INDEX_FILE,
    KNOWLEDGE_DIR,
    LOG_FILE,
    ROOT_DIR,
)
from core.utils import now_iso, today_iso
from core.config import CONFIG  # noqa: E402
from core.usage import LEDGER  # noqa: E402
from core.prompts import render  # noqa: E402
from core.sdk_helpers import StderrCapture, log_sdk_failure, make_path_scope_hook  # noqa: E402

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


def _apply_agent_options(capture: StderrCapture) -> ClaudeAgentOptions:
    """Sandboxed SDK options for the `apply()` agent (M028, issue #5).

    Non-destructive by construction: no `Bash` (the agent cannot `rm`/`git mv`),
    a PreToolUse path-scope hook constraining Write/Edit to the wiki's editable
    surfaces, `permission_mode="default"`, and a config-knob turn bound. Mirrors
    the safe `reconcile_fact()` pattern. Destructive ops (delete, rename) are
    engine-owned post-steps in later S01/S02 tasks, not agent actions.

    Scope note: writes are allowed across `knowledge/` (minus `facts/`),
    `daily/`, `index.md`, and the operations log; `knowledge/facts/` is
    write-protected via `denied_subpaths` (deny takes precedence over the
    allowed `knowledge/` root) — the fact files are the source of truth the
    agent must never edit.
    """
    return ClaudeAgentOptions(
        max_buffer_size=CONFIG.limits.sdk_max_buffer_size_mb * 1024 * 1024,
        cwd=str(ROOT_DIR),
        model=CONFIG.models.compile_model,
        allowed_tools=["Read", "Glob", "Grep", "Write", "Edit"],
        hooks={
            "PreToolUse": [
                HookMatcher(
                    matcher="Write|Edit",
                    hooks=[make_path_scope_hook(
                        [KNOWLEDGE_DIR, DAILY_DIR, INDEX_FILE, LOG_FILE],
                        denied_subpaths=[FACTS_DIR],
                    )],
                ),
            ],
        },
        permission_mode="default",
        max_turns=CONFIG.limits.correct_apply_max_turns,
        system_prompt={"type": "preset", "preset": "claude_code"},
        stderr=capture.callback,
    )


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
        # S01 has no engine-side delete executor yet — deletion is never
        # permitted. S02-T03 wires the real `--allow-delete` / disposition gate.
        deletion_allowed="false",
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
            options=_apply_agent_options(capture),
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
    LEDGER.record(model=CONFIG.models.compile_model, input_tokens=total_input_tokens, output_tokens=total_output_tokens)
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


# ── Strict concept-reconciliation path (concept-consistency-routine) ──
# Separate from apply(): same module + helpers, but a TIGHT scope. apply()
# is the broad operator-driven "propagate one fact across the whole vault"
# (acceptEdits + Bash + 50 turns). reconcile_fact() is the autonomous-routine
# primitive: writes locked to knowledge/concepts/ via a PreToolUse hook, no
# Bash, bounded turns; structural file-count gate lives in reconcile.py.
# apply() is left untouched.


@dataclass
class ReconcileResult:
    slug: str
    status: str            # ok | skipped | failed | dry_run
    cost_usd: float = 0.0
    files: list[str] = field(default_factory=list)
    detail: str = ""


async def reconcile_fact(
    slug: str,
    violating_files: list[str],
    *,
    dry_run: bool,
) -> ReconcileResult:
    """Reconcile the given concept files against one hard fact, strict-scoped.

    `violating_files` are vault-relative paths the caller (reconcile.py, from
    lint.check_facts_violations) already identified. The agent may only edit
    files under knowledge/concepts/ (enforced by the PreToolUse hook); the
    prompt forbids touching anything else, deleting, renaming, or editing
    provenance frontmatter. On success the fact is stamped `last_reconciled:`.
    """
    fact_path = FACTS_DIR / f"{slug}.md"
    if not fact_path.exists():
        return ReconcileResult(slug, "failed", detail=f"no such fact: {slug}")
    if not violating_files:
        return ReconcileResult(slug, "skipped", detail="no violating files")

    fact_text = fact_path.read_text(encoding="utf-8")
    files_block = "\n".join(f"- `{f}`" for f in violating_files)
    prompt = render(
        "reconcile_concept",
        fact_content=fact_text,
        fact_path=str(fact_path.relative_to(ROOT_DIR)),
        slug=slug,
        today=today_iso(),
        now=now_iso(),
        violating_files=files_block,
    )

    if dry_run:
        return ReconcileResult(
            slug, "dry_run", files=violating_files,
            detail=f"would reconcile {len(violating_files)} file(s)",
        )

    started = _time.time()
    capture = StderrCapture()
    cost = 0.0
    in_tok = out_tok = 0
    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                max_buffer_size=CONFIG.limits.sdk_max_buffer_size_mb * 1024 * 1024,
                cwd=str(ROOT_DIR),
                model=CONFIG.models.compile_model,
                allowed_tools=["Read", "Glob", "Grep", "Write", "Edit"],
                hooks={
                    "PreToolUse": [
                        HookMatcher(
                            matcher="Write|Edit",
                            hooks=[make_path_scope_hook([CONCEPTS_DIR, LOG_FILE])],
                        ),
                    ],
                },
                permission_mode="default",
                max_turns=CONFIG.limits.concept_reconcile_max_turns,
                system_prompt={"type": "preset", "preset": "claude_code"},
                stderr=capture.callback,
            ),
        ):
            if isinstance(message, AssistantMessage) and message.usage:
                in_tok += message.usage.get("input_tokens", 0)
                out_tok += message.usage.get("output_tokens", 0)
            if isinstance(message, ResultMessage):
                cost = message.total_cost_usd or 0.0
    except Exception as exc:
        log_sdk_failure(
            log,
            label=f"reconcile_fact:{slug}",
            source=f"fact:{slug}",
            model=CONFIG.models.compile_model,
            input_chars=len(prompt),
            started=started,
            capture=capture,
            exc=exc,
        )
        return ReconcileResult(slug, "failed", files=violating_files, detail="SDK call failed")

    LEDGER.record(model=CONFIG.models.compile_model, input_tokens=in_tok, output_tokens=out_tok)

    # Stamp the fact as reconciled (cooldown key). Re-read to avoid stomping.
    current_text = fact_path.read_text(encoding="utf-8")
    fm_now, _, body_now = _split_frontmatter(current_text)
    if fm_now:
        _backup(fact_path)
        fm_now["last_reconciled"] = now_iso()
        fm_now["updated"] = today_iso()
        _write_frontmatter(fact_path, fm_now, body_now)

    return ReconcileResult(slug, "ok", cost_usd=cost, files=violating_files, detail="reconciled")


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
