"""Process files dropped into inbox/ — categorize and move to the right raw/ subfolder.

Uses the local LLM (Ollama) to classify files, then moves them and optionally
triggers compilation.

Usage:
    uv run python scripts/process-inbox.py                    # process all, then compile
    uv run python scripts/process-inbox.py --no-compile       # process only, don't compile
    uv run python scripts/process-inbox.py --dry-run          # show what would happen
    uv run python scripts/process-inbox.py --model gemma3:4b  # use a different model
"""

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from core import ollama_client

from core.config import (
    RAW_ARTICLES_DIR,
    RAW_AUDIO_DIR,
    RAW_DIR,
    RAW_NOTES_DIR,
    RAW_PAPERS_DIR,
    RAW_TRANSCRIPTS_DIR,
    ROOT_DIR,
    today_iso,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("inbox")

from core.wiki_config import CONFIG

INBOX_DIR = ROOT_DIR / "inbox"
DEFAULT_MODEL = CONFIG.models.classify_model

# File extension → default category (no LLM needed)
EXTENSION_MAP = {
    ".mp3": "audio",
    ".m4a": "audio",
    ".wav": "audio",
    ".ogg": "audio",
    ".webm": "audio",
    ".pdf": "papers",
}

# Target directories per category
CATEGORY_DIRS = {
    "article": RAW_ARTICLES_DIR,
    "paper": RAW_PAPERS_DIR,
    "note": RAW_NOTES_DIR,
    "transcript": RAW_TRANSCRIPTS_DIR,
    "audio": RAW_AUDIO_DIR,
    "papers": RAW_PAPERS_DIR,
}

from core.prompts import render  # noqa: E402


def classify_file(file_path: Path, model: str) -> dict | None:
    """Use local LLM to classify a file."""
    content = ""
    try:
        if file_path.suffix in (".md", ".txt", ".html", ".htm", ".csv", ".json", ".yaml", ".yml"):
            content = file_path.read_text(encoding="utf-8", errors="replace")[:2000]
        elif file_path.suffix == ".pdf":
            # For PDFs, just use filename
            content = f"(PDF file, {file_path.stat().st_size / 1024:.0f} KB)"
        else:
            content = f"(Binary file: {file_path.suffix}, {file_path.stat().st_size / 1024:.0f} KB)"
    except Exception as e:
        content = f"(Could not read: {e})"

    prompt = render(
        "process_inbox_classify",
        filename=file_path.name,
        content_preview=content,
    )

    try:
        raw = ollama_client.chat(prompt, model=model)
        return ollama_client.parse_json_lenient(raw)
    except Exception as e:
        log.warning("LLM classification failed for %s: %s", file_path.name, e)
        return None


def add_frontmatter(file_path: Path, classification: dict) -> None:
    """Add YAML frontmatter to a markdown file if it doesn't have one."""
    if file_path.suffix not in (".md", ".txt", ".html", ".htm"):
        return

    content = file_path.read_text(encoding="utf-8", errors="replace")
    if content.startswith("---"):
        return  # Already has frontmatter

    tags = classification.get("tags", [])
    lang = classification.get("language", "de")
    summary = classification.get("summary", "")
    category = classification.get("category", "note")

    frontmatter = f"""---
type: {category}
date: {today_iso()}
origin: "inbox-drop"
tags: [{", ".join(tags)}]
language: {lang}
---

"""
    file_path.write_text(frontmatter + content, encoding="utf-8")


def process_inbox(model: str, dry_run: bool = False) -> list[dict]:
    """Process all files in inbox/."""
    if not INBOX_DIR.exists():
        log.info("No inbox directory at %s", INBOX_DIR)
        return []

    files = [f for f in INBOX_DIR.iterdir() if f.is_file() and not f.name.startswith(".")]
    if not files:
        log.info("Inbox is empty")
        return []

    log.info("Found %d files in inbox", len(files))
    results = []

    for file_path in sorted(files):
        ext = file_path.suffix.lower()
        log.info("Processing: %s", file_path.name)

        # ── HTML files → delegate to ingest-html.py ──
        if ext in (".html", ".htm"):
            log.info("  HTML detected → delegating to ingest-html.py (--mode both)")
            if dry_run:
                print(f"  {file_path.name} → ingest-html.py --mode both")
                results.append({"source": file_path.name, "category": "html-ingest", "target": "raw/articles/", "classification": {}})
                continue

            ingest_script = ROOT_DIR / "scripts" / "ingest-html.py"
            ret = subprocess.run(
                ["uv", "run", "python", str(ingest_script), str(file_path), "--mode", "both", "--model", model, "--no-compile"],
                cwd=str(ROOT_DIR),
                capture_output=True, text=True,
            )
            if ret.returncode == 0:
                # ingest-html.py handled everything — remove from inbox
                file_path.unlink(missing_ok=True)
                log.info("  Done (ingest-html handled it)")
                results.append({"source": file_path.name, "category": "html-ingest", "target": "raw/articles/", "classification": {}})
            else:
                log.error("  ingest-html.py failed: %s", ret.stderr[:200])
            continue

        # ── Extension-based shortcut (audio etc.) ──
        if ext in EXTENSION_MAP:
            category = EXTENSION_MAP[ext]
            classification = {
                "category": category,
                "suggested_name": file_path.stem.lower().replace(" ", "-"),
            }
            log.info("  Classified by extension: %s → %s", ext, category)
        else:
            # ── LLM classification for text files ──
            log.info("  Classifying with %s...", model)
            classification = classify_file(file_path, model)
            if not classification:
                classification = {"category": "note", "suggested_name": file_path.stem.lower().replace(" ", "-")}
                log.info("  LLM failed, defaulting to 'note'")
            else:
                log.info("  → %s (%s)", classification.get("category"), classification.get("summary", "")[:60])

        category = classification.get("category", "note")
        target_dir = CATEGORY_DIRS.get(category, RAW_NOTES_DIR)
        suggested_name = classification.get("suggested_name", file_path.stem)

        # Determine target filename
        if ext in (".md", ".txt"):
            target_name = f"{suggested_name}.md"
        else:
            target_name = file_path.name

        target_path = target_dir / target_name

        result = {
            "source": file_path.name,
            "category": category,
            "target": str(target_path.relative_to(ROOT_DIR)),
            "classification": classification,
        }

        if dry_run:
            print(f"  {file_path.name} → {target_path.relative_to(ROOT_DIR)}")
            results.append(result)
            continue

        # Add frontmatter if needed
        if ext in (".md", ".txt"):
            add_frontmatter(file_path, classification)

        # Move file
        target_dir.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            # Avoid overwriting — add timestamp
            target_name = f"{suggested_name}-{today_iso()}{target_path.suffix}"
            target_path = target_dir / target_name

        shutil.move(str(file_path), str(target_path))
        log.info("  Moved → %s", target_path.relative_to(ROOT_DIR))
        results.append(result)

    return results


def main():
    parser = argparse.ArgumentParser(description="Process inbox/ files")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--no-compile", action="store_true", help="Don't trigger compilation after processing")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    args = parser.parse_args()

    results = process_inbox(args.model, dry_run=args.dry_run)

    if not results:
        return

    print(f"\nProcessed {len(results)} files")
    for r in results:
        print(f"  {r['source']} → {r['category']} → {r['target']}")

    if args.dry_run or args.no_compile:
        return

    # Trigger compilation
    print("\nTriggering compilation...")
    compile_script = ROOT_DIR / "scripts" / "compile.py"
    subprocess.run(
        ["uv", "run", "python", str(compile_script)],
        cwd=str(ROOT_DIR),
    )


if __name__ == "__main__":
    main()
