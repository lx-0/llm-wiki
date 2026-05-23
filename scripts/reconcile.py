"""Autonomous concept-reconciliation routine.

Signal-driven: it does NOT detect anything new. It consumes
`lint.check_facts_violations()` (concepts that contain a hard fact's
negation terms), groups the violations by fact, and runs the STRICT
`correct_apply.reconcile_fact()` per fact — writes locked to
knowledge/concepts/ via a PreToolUse hook, under per-fact + per-run cost
caps and a per-fact cooldown.

Strict policy (full rationale: .ytstack/backlog/concept-consistency-routine.md):
  - AUTO only the fact_violation class (fact is the authority). Concept↔concept
    contradictions + quality are PROPOSE-ONLY — left in the lint/dashboard
    surface, never auto-rewritten here.
  - Writes require either an explicit `--apply` AND `features.concept_reconciliation`
    on, or the piggyback (which only fires when the flag is on). Default is
    dry-run.
  - Scope is knowledge/concepts/ only; violating files are passed as ABSOLUTE
    paths so the PreToolUse path-scope hook (resolve-based) can't be defeated
    by a non-ROOT process cwd (the compile max_turns lesson, 2026-05-22).

Usage:
    wiki reconcile                 # dry-run plan (default, no writes)
    wiki reconcile --apply         # apply (requires features.concept_reconciliation)
    wiki reconcile --limit N       # cap facts processed this run
"""

import os

os.environ["CLAUDE_INVOKED_BY"] = "reconcile"

import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import yaml

from core.paths import FACTS_DIR, LOG_FILE, ROOT_DIR
from core.config import CONFIG  # noqa: E402
from core.utils import now_iso  # noqa: E402

import lint  # noqa: E402
from facts.correct_apply import ReconcileResult, reconcile_fact  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("reconcile")

# lint emits the slug backtick-wrapped as `facts/<slug>` (lint.check_facts_violations).
# Anchor on the backticks, not an ASCII char class: fact slugs can carry non-ASCII
# (e.g. `sidney-wach-ist-männlich`), and an `ä` stored NFD-decomposed (a + U+0308)
# silently truncates an `[A-Za-z0-9_-]+` capture mid-slug → "no such fact".
_FACT_SLUG_RE = re.compile(r"`facts/([^`]+)`")


def _fact_violations_by_slug() -> dict[str, list[str]]:
    """Group lint fact-violations by fact slug → list of ABSOLUTE concept paths.

    Strict scope: only `knowledge/concepts/` articles. `check_facts_violations`
    yields file paths relative to KNOWLEDGE_DIR (e.g. `concepts/foo.md`) and a
    detail string naming `facts/<slug>`.
    """
    out: dict[str, list[str]] = {}
    for iss in lint.check_facts_violations():
        rel = iss.get("file", "")
        if not rel.startswith("concepts/"):
            continue  # concepts-only scope (matches the write hook)
        m = _FACT_SLUG_RE.search(iss.get("detail", ""))
        if not m:
            continue
        slug = m.group(1)
        abs_path = str((ROOT_DIR / "knowledge" / rel).resolve())
        files = out.setdefault(slug, [])
        if abs_path not in files:
            files.append(abs_path)
    return out


def _read_frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    try:
        fm = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return {}
    return fm if isinstance(fm, dict) else {}


def _within_cooldown(slug: str, *, cooldown_days: int) -> bool:
    """True iff the fact was reconciled within the cooldown window."""
    ts = _read_frontmatter(FACTS_DIR / f"{slug}.md").get("last_reconciled")
    if not ts:
        return False
    try:
        when = datetime.fromisoformat(str(ts))
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - when).total_seconds() / 86400.0
    return age_days < cooldown_days


def _append_log_summary(lines: list[str]) -> None:
    """Prepend one newest-first block to knowledge/log.md."""
    block = f"## [{now_iso()}] reconcile | concept-consistency pass\n" + "\n".join(lines) + "\n\n"
    existing = LOG_FILE.read_text(encoding="utf-8") if LOG_FILE.exists() else "# Operations Log\n\n"
    if existing.startswith("# "):
        head, _, rest = existing.partition("\n")
        LOG_FILE.write_text(f"{head}\n\n{block}{rest.lstrip()}", encoding="utf-8")
    else:
        LOG_FILE.write_text(block + existing, encoding="utf-8")


async def run(*, apply: bool, limit: int | None) -> int:
    dry_run = not apply

    by_slug = _fact_violations_by_slug()
    if not by_slug:
        log.info("No fact-violations in knowledge/concepts/ — nothing to reconcile.")
        return 0

    cooldown_days = CONFIG.scheduling.concept_reconcile_cooldown_days
    per_fact_cap = CONFIG.limits.concept_reconcile_per_fact_max_cost_usd
    per_run_cap = CONFIG.limits.concept_reconcile_max_cost_per_run_usd

    # Deterministic order: most-violating facts first.
    candidates = sorted(by_slug.items(), key=lambda kv: len(kv[1]), reverse=True)
    total_facts = len(candidates)
    n_files = sum(len(v) for v in by_slug.values())
    log.info(
        "%d fact(s) violated across %d concept file(s). mode=%s caps: per-fact $%.2f / per-run $%.2f",
        total_facts, n_files, "DRY-RUN" if dry_run else "APPLY", per_fact_cap, per_run_cap,
    )

    results: list[ReconcileResult] = []
    spent = 0.0
    processed = 0
    for slug, files in candidates:
        if limit is not None and processed >= limit:
            log.info("  --limit %d reached; stopping.", limit)
            break
        if _within_cooldown(slug, cooldown_days=cooldown_days):
            log.info("  %s: within cooldown (%dd) — skipping", slug, cooldown_days)
            continue
        if not dry_run and spent >= per_run_cap:
            log.warning("  per-run cap $%.2f reached ($%.4f spent) — stopping sweep", per_run_cap, spent)
            break
        log.info("  reconciling fact %s → %d concept file(s)", slug, len(files))
        res = await reconcile_fact(slug, files, dry_run=dry_run, per_fact_cap_usd=per_fact_cap)
        results.append(res)
        spent += res.cost_usd
        processed += 1
        log.info("    %s — %s (%s)%s", slug, res.status, res.detail,
                 f" ${res.cost_usd:.4f}" if res.cost_usd else "")

    ok = [r for r in results if r.status == "ok"]
    skipped = [r for r in results if r.status in ("skipped", "dry_run")]
    failed = [r for r in results if r.status == "failed"]
    log.info(
        "reconcile done: %d ok · %d skipped/dry · %d failed · $%.4f spent",
        len(ok), len(skipped), len(failed), spent,
    )

    if apply and ok:
        _append_log_summary([
            f"- Facts auto-reconciled: {len(ok)} ({', '.join(r.slug for r in ok)})",
            f"- Concept files touched: {sum(len(r.files) for r in ok)}",
            f"- Cost: ${spent:.4f}",
            "- Propose-only (contradictions / quality): see `wiki lint` / the lint dashboard — not auto-applied.",
        ])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous concept-reconciliation routine.")
    parser.add_argument("--apply", action="store_true",
                        help="actually edit (requires features.concept_reconciliation); default is dry-run")
    parser.add_argument("--dry-run", action="store_true",
                        help="explicit dry-run (the default; --apply overrides nothing if both given — dry-run wins)")
    parser.add_argument("--limit", type=int, default=None, help="max facts to process this run")
    args = parser.parse_args()

    if args.dry_run:
        args.apply = False  # explicit dry-run wins over --apply (safety)

    if args.apply and not CONFIG.features.concept_reconciliation:
        log.warning(
            "features.concept_reconciliation is OFF — refusing to --apply. "
            "Review with `wiki reconcile` (dry-run), then flip the flag in config.yaml to enable."
        )
        return asyncio.run(run(apply=False, limit=args.limit))

    return asyncio.run(run(apply=args.apply, limit=args.limit))


if __name__ == "__main__":
    sys.exit(main())
