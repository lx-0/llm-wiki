"""Review all wiki articles using a local LLM for quality assessment.

Reads every article in knowledge/, sends it to the local Ollama instance,
and produces a structured quality report with scores and suggestions.

Usage:
    uv run python scripts/review-wiki.py                    # review all articles
    uv run python scripts/review-wiki.py --model gemma3:4b  # use a different model
    uv run python scripts/review-wiki.py --limit 10         # only review 10 articles
    uv run python scripts/review-wiki.py --dry-run          # just list articles
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from core import ollama_client

from core.paths import KNOWLEDGE_DIR, REPORTS_DIR, ROOT_DIR
from core.utils import get_article_word_count, list_wiki_articles, now_iso, read_wiki_index, today_iso

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("review")

from core.config import CONFIG  # noqa: E402
from core.prompts import render  # noqa: E402

DEFAULT_MODEL = CONFIG.models.classify_model

def review_article(article_path: Path, model: str) -> dict | None:
    """Send an article to the local LLM for review."""
    content = article_path.read_text(encoding="utf-8")
    rel = str(article_path.relative_to(KNOWLEDGE_DIR))
    word_count = get_article_word_count(article_path)

    prompt = render("review_wiki", article_content=content)

    try:
        raw = ollama_client.chat(
            prompt, model=model, timeout=CONFIG.limits.review_ollama_timeout_s
        )
        review = ollama_client.parse_json_lenient(raw)
        review["article"] = rel
        review["word_count"] = word_count
        return review

    except json.JSONDecodeError:
        # kcma responded — the model just emitted unparseable output. NOT a
        # connectivity failure, so `error_kind=parse` does not count toward the
        # consecutive-failure abort (which is meant to catch a down server).
        log.warning("Failed to parse JSON for %s: %s", rel, raw[:200])
        return {"article": rel, "word_count": word_count,
                "error": "JSON parse failed", "error_kind": "parse", "raw": raw[:300]}
    except Exception as e:
        # Connection refused / read timeout / HTTP error — a transport-level
        # failure. `error_kind=ollama` so the caller can fail-fast when kcma is
        # down instead of grinding 1700×timeout.
        log.error("Failed to review %s: %s", rel, e)
        return {"article": rel, "word_count": word_count,
                "error": str(e), "error_kind": "ollama"}


def generate_report(reviews: list[dict], model: str) -> str:
    """Generate a markdown quality report."""
    valid = [r for r in reviews if "overall" in r]
    errors = [r for r in reviews if "error" in r]

    avg_overall = sum(r["overall"] for r in valid) / len(valid) if valid else 0
    avg_accuracy = sum(r["accuracy"] for r in valid) / len(valid) if valid else 0
    avg_depth = sum(r["depth"] for r in valid) / len(valid) if valid else 0
    avg_connections = sum(r["connections"] for r in valid) / len(valid) if valid else 0

    verdicts = {}
    for r in valid:
        v = r.get("verdict", "?")
        verdicts[v] = verdicts.get(v, 0) + 1

    lines = [
        f"# Wiki Quality Review — {today_iso()}",
        "",
        f"**Model:** {model} (local Ollama)",
        f"**Articles reviewed:** {len(reviews)}",
        f"**Successful:** {len(valid)} | **Errors:** {len(errors)}",
        "",
        "## Summary Scores",
        "",
        f"| Metric | Average |",
        f"|--------|---------|",
        f"| Overall | **{avg_overall:.1f}**/5 |",
        f"| Accuracy | {avg_accuracy:.1f}/5 |",
        f"| Depth | {avg_depth:.1f}/5 |",
        f"| Connections | {avg_connections:.1f}/5 |",
        "",
        "## Verdicts",
        "",
    ]
    for v, c in sorted(verdicts.items(), key=lambda x: -x[1]):
        lines.append(f"- **{v}**: {c} articles")

    # Top articles
    top = sorted(valid, key=lambda r: r.get("overall", 0), reverse=True)[:10]
    lines.append("")
    lines.append("## Top 10 Articles")
    lines.append("")
    lines.append("| Article | Overall | Accuracy | Depth | Connections | Verdict |")
    lines.append("|---------|---------|----------|-------|-------------|---------|")
    for r in top:
        lines.append(
            f"| `{r['article']}` | **{r.get('overall', '?')}** | "
            f"{r.get('accuracy', '?')} | {r.get('depth', '?')} | "
            f"{r.get('connections', '?')} | {r.get('verdict', '?')} |"
        )

    # Weakest articles
    weak = sorted(valid, key=lambda r: r.get("overall", 5))[:10]
    lines.append("")
    lines.append("## Weakest 10 Articles (Improvement Candidates)")
    lines.append("")
    lines.append("| Article | Overall | Verdict | Suggestion |")
    lines.append("|---------|---------|---------|------------|")
    for r in weak:
        lines.append(
            f"| `{r['article']}` | **{r.get('overall', '?')}** | "
            f"{r.get('verdict', '?')} | {r.get('suggestion', '')} |"
        )

    # Articles to archive
    archive = [r for r in valid if r.get("verdict") == "archive"]
    if archive:
        lines.append("")
        lines.append("## Archive Candidates")
        lines.append("")
        for r in archive:
            lines.append(f"- `{r['article']}` — {r.get('suggestion', '')}")

    # Articles to enrich
    enrich = [r for r in valid if r.get("verdict") == "enrich"]
    if enrich:
        lines.append("")
        lines.append("## Enrich Candidates")
        lines.append("")
        for r in enrich:
            lines.append(f"- `{r['article']}` — {r.get('missing', '')}")

    # Errors
    if errors:
        lines.append("")
        lines.append("## Review Errors")
        lines.append("")
        for r in errors:
            lines.append(f"- `{r['article']}` — {r.get('error', '?')}")

    # Full table
    lines.append("")
    lines.append("## All Articles")
    lines.append("")
    lines.append("| Article | Words | Overall | Accuracy | Depth | Conn. | Action. | Fresh. | Verdict |")
    lines.append("|---------|-------|---------|----------|-------|-------|---------|--------|---------|")
    for r in sorted(valid, key=lambda x: x.get("overall", 0), reverse=True):
        lines.append(
            f"| `{r['article']}` | {r.get('word_count', '?')} | "
            f"**{r.get('overall', '?')}** | {r.get('accuracy', '?')} | "
            f"{r.get('depth', '?')} | {r.get('connections', '?')} | "
            f"{r.get('actionability', '?')} | {r.get('freshness', '?')} | "
            f"{r.get('verdict', '?')} |"
        )

    return "\n".join(lines)


def _write_reports(reviews: list[dict], model: str) -> tuple[Path, Path]:
    """Write the markdown + raw-JSON report for `reviews`. Idempotent within a
    run (same dated filenames), so checkpoint calls overwrite the prior partial
    with the latest. Returns (md_path, json_path)."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORTS_DIR / f"wiki-review-{today_iso()}.md"
    md_path.write_text(generate_report(reviews, model), encoding="utf-8")
    json_path = REPORTS_DIR / f"wiki-review-{today_iso()}.json"
    json_path.write_text(
        json.dumps(reviews, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return md_path, json_path


def _sweep_deadline_s(review_max: int, piggyback_max: int) -> float:
    """Soft sweep deadline (seconds), always strictly under the piggyback hard
    wall-clock cap so the sweep self-terminates with a clean partial report
    before the runner kills it (which records a false `timeout`)."""
    return min(review_max, 0.9 * piggyback_max)


def main():
    parser = argparse.ArgumentParser(description="Review wiki articles with local LLM")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--limit", type=int, help="Max articles to review")
    parser.add_argument("--dry-run", action="store_true", help="Just list articles")
    args = parser.parse_args()

    articles = list_wiki_articles()
    if args.limit:
        articles = articles[:args.limit]

    print(f"Articles to review: {len(articles)}")
    print(f"Model: {args.model}")

    if args.dry_run:
        for a in articles:
            wc = get_article_word_count(a)
            print(f"  {a.relative_to(KNOWLEDGE_DIR)} ({wc} words)")
        return

    # Check Ollama connectivity
    if not ollama_client.is_reachable():
        print(f"ERROR: Cannot reach Ollama at {CONFIG.models.ollama_url}")
        print("Is the Ollama server reachable? Check `ollama serve` locally or your remote endpoint.")
        sys.exit(1)

    abort_n = CONFIG.limits.review_consecutive_failure_abort
    checkpoint_every = CONFIG.limits.review_checkpoint_every
    deadline_s = _sweep_deadline_s(
        CONFIG.limits.review_max_sweep_runtime_s,
        CONFIG.limits.piggyback_max_runtime_s,
    )
    started = time.time()

    reviews: list[dict] = []
    consecutive_ollama_failures = 0
    aborted = False

    for i, article in enumerate(articles, 1):
        # Soft deadline — self-terminate with a clean partial before the
        # piggyback runner's hard wall-clock cap kills us (false `timeout` +
        # lost final report). Checkpoints already persisted the work so far.
        if time.time() - started > deadline_s:
            _write_reports(reviews, args.model)
            log.info(
                "Sweep soft-deadline reached (%.0fs) — %d/%d reviewed, partial "
                "report written, exiting cleanly.",
                deadline_s, i - 1, len(articles),
            )
            print(
                f"\nDeadline reached after {i - 1}/{len(articles)} reviews — "
                f"partial report saved. (Next run continues the weekly cadence.)"
            )
            break
        rel = article.relative_to(KNOWLEDGE_DIR)
        print(f"[{i}/{len(articles)}] Reviewing {rel}...", end=" ", flush=True)
        review = review_article(article, args.model)
        reviews.append(review)

        if "error" in review:
            print(f"FAILED ({review.get('error_kind', '?')})")
            # Only transport-level (ollama) failures count toward fail-fast;
            # a parse failure means kcma IS up, so it resets the streak.
            if review.get("error_kind") == "ollama":
                consecutive_ollama_failures += 1
                if abort_n and consecutive_ollama_failures >= abort_n:
                    log.error(
                        "Aborting sweep after %d consecutive Ollama failures "
                        "(kcma down?). %d/%d articles reviewed.",
                        consecutive_ollama_failures, i, len(articles),
                    )
                    print(
                        f"\nABORTED: {consecutive_ollama_failures} consecutive "
                        f"Ollama failures — is kcma reachable? Partial report saved."
                    )
                    aborted = True
                    break
            else:
                consecutive_ollama_failures = 0
        else:
            print(f"{review.get('overall', '?')}/5 ({review.get('verdict', '?')})")
            consecutive_ollama_failures = 0

        # Incremental checkpoint so a later abort / kill / crash doesn't lose
        # the multi-hour partial sweep (report was previously written only at
        # end-of-loop).
        if checkpoint_every and i % checkpoint_every == 0:
            _write_reports(reviews, args.model)
            log.info("checkpoint: %d reviews persisted", len(reviews))

    md_path, json_path = _write_reports(reviews, args.model)
    print(f"\nReport saved: {md_path}")
    print(f"Raw data: {json_path}")

    # Summary
    valid = [r for r in reviews if "overall" in r]
    if valid:
        avg = sum(r["overall"] for r in valid) / len(valid)
        suffix = " (partial — sweep aborted)" if aborted else ""
        print(f"\nAverage quality: {avg:.1f}/5 across {len(valid)} articles{suffix}")
    if aborted:
        sys.exit(1)


if __name__ == "__main__":
    main()
