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
from datetime import datetime
from pathlib import Path

from core import ollama_client

from core.paths import RAW_ARTICLES_DIR, RAW_DIR, RAW_INBOX_WIKI_DIR, RAW_NOTES_DIR, RAW_TRANSCRIPTS_DIR, ROOT_DIR, SCRIPTS_DIR, WIKI_DIR
from core.utils import today_iso

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("inbox")

from core.config import CONFIG

INBOX_DIR = ROOT_DIR / "inbox"
DEFAULT_MODEL = CONFIG.models.classify_model

# File extension → marker for binary-only intake (no LLM classify, no artifact —
# original wandert in T02 nach RAW_INBOX_WIKI_DIR und das war's).
EXTENSION_MAP = {
    ".mp3": "binary",
    ".m4a": "binary",
    ".wav": "binary",
    ".ogg": "binary",
    ".webm": "binary",
    ".pdf": "binary",
}

# Target directories for derived artifacts (Substrat-Zone). Original geht
# IMMER nach RAW_INBOX_WIKI_DIR — wird in T02 verdrahtet.
CATEGORY_DIRS = {
    "article": RAW_ARTICLES_DIR,
    "note": RAW_NOTES_DIR,
    "transcript": RAW_TRANSCRIPTS_DIR,
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


def _archive_to_inbox_wiki(file_path: Path) -> Path:
    """Move file (unmodified) to raw/inbox-wiki/ — the audit-zone archive.

    Filename collision → suffix with file's mtime-iso (deterministic, idempotent
    when the same file is re-dropped after edits).
    """
    RAW_INBOX_WIKI_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_INBOX_WIKI_DIR / file_path.name
    if dest.exists():
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%Y%m%dT%H%M%S")
        dest = RAW_INBOX_WIKI_DIR / f"{file_path.stem}-{mtime}{file_path.suffix}"
    shutil.move(str(file_path), str(dest))
    return dest


def process_inbox(model: str, dry_run: bool = False) -> list[dict]:
    """Two-zone intake: original → raw/inbox-wiki/ (audit), artifact → raw/<cat>/ (substrate)."""
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

        # ── HTML files → delegate to ingest-html.py, then archive original ──
        if ext in (".html", ".htm"):
            log.info("  HTML detected → delegating to ingest-html.py (--mode both)")
            if dry_run:
                print(f"  {file_path.name} → raw/articles/ (extract) + raw/inbox-wiki/ (original)")
                results.append({"source": file_path.name, "category": "html-ingest", "target": "raw/articles/", "classification": {}})
                continue

            ingest_script = ROOT_DIR / "scripts" / "ingest-html.py"
            ret = subprocess.run(
                ["uv", "run", "python", str(ingest_script), str(file_path), "--mode", "both", "--model", model, "--no-compile"],
                cwd=str(ROOT_DIR),
                capture_output=True, text=True,
            )
            if ret.returncode == 0:
                archived = _archive_to_inbox_wiki(file_path)
                log.info("  Done (ingest-html handled artifact; original → %s)", archived.relative_to(ROOT_DIR))
                results.append({"source": file_path.name, "category": "html-ingest", "target": "raw/articles/", "classification": {}})
            else:
                log.error("  ingest-html.py failed: %s", ret.stderr[:200])
            continue

        # ── Binary intake (audio/pdf/etc.) → archive-only, no artifact ──
        if ext in EXTENSION_MAP:
            log.info("  Binary intake (%s) → archive-only", ext)
            if dry_run:
                print(f"  {file_path.name} → raw/inbox-wiki/ (binary-only, no artifact)")
                results.append({"source": file_path.name, "category": "binary", "target": "raw/inbox-wiki/", "classification": {}})
                continue
            archived = _archive_to_inbox_wiki(file_path)
            log.info("  Archived → %s", archived.relative_to(ROOT_DIR))
            results.append({"source": file_path.name, "category": "binary", "target": str(archived.relative_to(ROOT_DIR)), "classification": {}})
            continue

        # ── md/txt → LLM classify, write artifact, archive original ──
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
        target_name = f"{suggested_name}.md"
        target_path = target_dir / target_name

        result = {
            "source": file_path.name,
            "category": category,
            "target": str(target_path.relative_to(ROOT_DIR)),
            "classification": classification,
        }

        if dry_run:
            print(f"  {file_path.name} → {target_path.relative_to(ROOT_DIR)} + raw/inbox-wiki/{file_path.name}")
            results.append(result)
            continue

        # Write derived artifact: copy original, then stamp with frontmatter
        target_dir.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            target_name = f"{suggested_name}-{today_iso()}.md"
            target_path = target_dir / target_name
        shutil.copy2(str(file_path), str(target_path))
        add_frontmatter(target_path, classification)

        # Archive original (unmodified) to inbox-wiki
        archived = _archive_to_inbox_wiki(file_path)

        log.info("  Artifact → %s; original → %s", target_path.relative_to(ROOT_DIR), archived.relative_to(ROOT_DIR))
        result["target"] = str(target_path.relative_to(ROOT_DIR))
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

    # Trigger compilation. compile.py lives in the engine (WIKI_DIR/scripts),
    # not in the vault (ROOT_DIR/scripts). Reuse the current venv's interpreter
    # via sys.executable so we don't depend on uv being on PATH.
    print("\nTriggering compilation...")
    compile_script = SCRIPTS_DIR / "compile.py"
    subprocess.run(
        [sys.executable, str(compile_script)],
        cwd=str(WIKI_DIR),
    )


if __name__ == "__main__":
    main()
