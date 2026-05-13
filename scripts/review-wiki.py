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
from pathlib import Path

from core import ollama_client

from core.config import KNOWLEDGE_DIR, REPORTS_DIR, ROOT_DIR, now_iso, today_iso
from core.utils import get_article_word_count, list_wiki_articles, read_wiki_index

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("review")

from core.wiki_config import CONFIG  # noqa: E402
from core.prompts import render  # noqa: E402

DEFAULT_MODEL = CONFIG.models.classify_model

def review_article(article_path: Path, model: str) -> dict | None:
    """Send an article to the local LLM for review."""
    content = article_path.read_text(encoding="utf-8")
    rel = str(article_path.relative_to(KNOWLEDGE_DIR))
    word_count = get_article_word_count(article_path)

    prompt = render("review_wiki", article_content=content)

    try:
        raw = ollama_client.chat(prompt, model=model, timeout=300)
        review = ollama_client.parse_json_lenient(raw)
        review["article"] = rel
        review["word_count"] = word_count
        return review

    except json.JSONDecodeError:
        log.warning("Failed to parse JSON for %s: %s", rel, raw[:200])
        return {"article": rel, "word_count": word_count, "error": "JSON parse failed", "raw": raw[:300]}
    except Exception as e:
        log.error("Failed to review %s: %s", rel, e)
        return {"article": rel, "word_count": word_count, "error": str(e)}


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

    reviews = []
    for i, article in enumerate(articles, 1):
        rel = article.relative_to(KNOWLEDGE_DIR)
        print(f"[{i}/{len(articles)}] Reviewing {rel}...", end=" ", flush=True)
        review = review_article(article, args.model)
        if review:
            overall = review.get("overall", "?")
            verdict = review.get("verdict", "?")
            print(f"{overall}/5 ({verdict})")
            reviews.append(review)
        else:
            print("FAILED")

    # Generate and save report
    report = generate_report(reviews, args.model)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"wiki-review-{today_iso()}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved: {report_path}")

    # Also save raw JSON for further analysis
    json_path = REPORTS_DIR / f"wiki-review-{today_iso()}.json"
    json_path.write_text(json.dumps(reviews, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Raw data: {json_path}")

    # Summary
    valid = [r for r in reviews if "overall" in r]
    if valid:
        avg = sum(r["overall"] for r in valid) / len(valid)
        print(f"\nAverage quality: {avg:.1f}/5 across {len(valid)} articles")


if __name__ == "__main__":
    main()
