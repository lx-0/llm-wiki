"""Ingest HTML files into the knowledge base with content and/or visual analysis.

Two modes:
- content:  Extract text via html2text → Markdown in raw/articles/
- visual:   Screenshot the rendered page → Vision LLM describes layout/design → raw/notes/
- both:     Content extraction + visual analysis combined into one source file

The visual mode uses Playwright for screenshots and the local Ollama Vision LLM
(gemma4:e4b supports multimodal) for interpretation.

Usage:
    uv run python scripts/ingest-html.py page.html                    # content mode (default)
    uv run python scripts/ingest-html.py page.html --mode visual      # screenshot + vision
    uv run python scripts/ingest-html.py page.html --mode both        # content + visual
    uv run python scripts/ingest-html.py https://example.com          # URL works too
    uv run python scripts/ingest-html.py page.html --no-compile       # don't auto-compile
    uv run python scripts/ingest-html.py page.html --model gemma3:4b  # different model
"""

import argparse
import base64
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import html2text
import httpx

from core import ollama_client
from core.paths import RAW_ARTICLES_DIR, RAW_DIR, RAW_NOTES_DIR, ROOT_DIR, SCRIPTS_DIR, WIKI_DIR
from core.utils import today_iso
from core.config import CONFIG

from core.console import setup_console_logging
log = setup_console_logging("ingest-html")

DEFAULT_MODEL = CONFIG.models.vision_model


# ── Content extraction ────────────────────────────────────────────────

def extract_content(html: str) -> str:
    """Convert HTML to clean Markdown."""
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.body_width = 0
    h.skip_internal_links = True
    h.inline_links = True
    h.protect_links = True
    return h.handle(html)


# ── Visual analysis ───────────────────────────────────────────────────

def screenshot_html(source: str, output_path: Path) -> bool:
    """Take a screenshot of an HTML file or URL using Playwright."""
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})

            if source.startswith("http://") or source.startswith("https://"):
                page.goto(source, wait_until="networkidle", timeout=30000)
            else:
                file_url = f"file://{Path(source).resolve()}"
                page.goto(file_url, wait_until="networkidle", timeout=15000)

            page.screenshot(path=str(output_path), full_page=True)
            browser.close()
            log.info("Screenshot saved: %s", output_path)
            return True
    except Exception as e:
        log.error("Screenshot failed: %s", e)
        return False


def analyze_visual(image_path: Path, model: str, context: str = "") -> str | None:
    """Send screenshot to Vision LLM for layout/design analysis."""
    image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")

    prompt = f"""Analyze this webpage screenshot. Describe in detail:

1. **Layout & Structure**: How is the page organized? What sections exist? How is the visual hierarchy?
2. **Design Language**: Colors, typography, spacing, overall aesthetic. What brand/style does it convey?
3. **Key Information**: What are the main messages, CTAs, or data points visible?
4. **UX Patterns**: Navigation, forms, cards, tables — what UI patterns are used?
5. **Target Audience**: Who is this page for? What's the intent?

{f"Additional context: {context}" if context else ""}

Be thorough and specific. This analysis will be stored as knowledge."""

    try:
        content, _ = ollama_client.chat_vision(
            prompt, model=model, image_b64=image_data, timeout=300,
        )
        return content
    except Exception as e:
        log.error("Vision analysis failed: %s", e)
        return None


# ── Slug generation ───────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convert text to filename-safe slug."""
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:80]


def extract_title(html: str) -> str:
    """Extract <title> from HTML."""
    import re
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


# ── Main ingest logic ────────────────────────────────────────────────

def ingest(source: str, mode: str, model: str, compile: bool) -> Path | None:
    """Ingest an HTML file or URL."""

    # Resolve source
    is_url = source.startswith("http://") or source.startswith("https://")

    if is_url:
        log.info("Fetching URL: %s", source)
        try:
            resp = httpx.get(source, follow_redirects=True, timeout=30)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            log.error("Failed to fetch URL: %s", e)
            return None
        slug = slugify(urlparse(source).path.split("/")[-1] or urlparse(source).netloc)
        origin = source
    else:
        source_path = Path(source).resolve()
        if not source_path.exists():
            log.error("File not found: %s", source)
            return None
        html = source_path.read_text(encoding="utf-8", errors="replace")
        slug = slugify(source_path.stem)
        origin = str(source_path)

    title = extract_title(html) or slug
    log.info("Title: %s", title)
    if not slug or slug == "-":
        slug = slugify(title) or "untitled"

    parts = []
    parts.append("---")
    parts.append(f"type: article")
    parts.append(f"date: {today_iso()}")
    parts.append(f'origin: "{origin}"')
    parts.append(f"tags: [html, ingest]")
    parts.append(f"mode: {mode}")
    parts.append("---")
    parts.append("")
    parts.append(f"# {title}")
    parts.append("")

    # ── Content extraction ──
    if mode in ("content", "both"):
        log.info("Extracting content...")
        markdown = extract_content(html)
        parts.append("## Content")
        parts.append("")
        parts.append(markdown)
        parts.append("")

    # ── Visual analysis ──
    if mode in ("visual", "both"):
        log.info("Taking screenshot...")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            screenshot_path = Path(tmp.name)

        if screenshot_html(source if is_url else str(Path(source).resolve()), screenshot_path):
            log.info("Analyzing visual with %s...", model)
            context = f"Page title: {title}" if title else ""
            analysis = analyze_visual(screenshot_path, model, context)

            if analysis:
                parts.append("## Visual Analysis")
                parts.append("")
                parts.append(f"> Analyzed by {model} (local Ollama)")
                parts.append("")
                parts.append(analysis)
                parts.append("")

            # Save screenshot alongside the article
            screenshot_dest = RAW_ARTICLES_DIR / f"{slug}.png"
            import shutil
            shutil.move(str(screenshot_path), str(screenshot_dest))
            parts.append(f"## Screenshot")
            parts.append("")
            parts.append(f"![{title}]({slug}.png)")
            parts.append("")
        else:
            parts.append("## Visual Analysis")
            parts.append("")
            parts.append("> Screenshot failed — visual analysis skipped")
            parts.append("")

    # ── Save original HTML alongside ──
    RAW_ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    html_dest = RAW_ARTICLES_DIR / f"{slug}.html"
    if html_dest.exists():
        html_dest = RAW_ARTICLES_DIR / f"{slug}-{today_iso()}.html"
    html_dest.write_text(html, encoding="utf-8")
    log.info("Saved original HTML: %s", html_dest.relative_to(ROOT_DIR))

    # Reference the original HTML so the compiler can read it if needed
    html_rel = html_dest.relative_to(ROOT_DIR)
    parts.append("## Original Source")
    parts.append("")
    parts.append(f"The full original HTML is available at `{html_rel}`.")
    parts.append("Read it with the Read tool for additional context if the extracted content above is insufficient.")
    parts.append("")

    # Update origin in frontmatter to point to the saved HTML
    parts[3] = f'origin: "{html_rel}"'

    # ── Write enriched markdown ──
    output_path = RAW_ARTICLES_DIR / f"{slug}.md"
    if output_path.exists():
        output_path = RAW_ARTICLES_DIR / f"{slug}-{today_iso()}.md"

    output_path.write_text("\n".join(parts), encoding="utf-8")
    log.info("Saved: %s", output_path.relative_to(ROOT_DIR))

    # ── Compile ──
    # compile.py lives in the engine (WIKI_DIR/scripts), not the vault
    # (ROOT_DIR/scripts). Use sys.executable so we stay in the current venv.
    if compile:
        log.info("Triggering compilation...")
        compile_script = SCRIPTS_DIR / "compile.py"
        subprocess.run(
            [sys.executable, str(compile_script)],
            cwd=str(WIKI_DIR),
        )

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Ingest HTML files or URLs")
    parser.add_argument("source", help="Path to HTML file or URL")
    parser.add_argument(
        "--mode",
        choices=["content", "visual", "both"],
        default="content",
        help="Extraction mode (default: content)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model for visual analysis (default: {DEFAULT_MODEL})")
    parser.add_argument("--no-compile", action="store_true", help="Don't trigger compilation")
    args = parser.parse_args()

    result = ingest(args.source, args.mode, args.model, compile=not args.no_compile)
    if result:
        print(f"\nIngested: {result.relative_to(ROOT_DIR)}")
    else:
        print("Ingest failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
