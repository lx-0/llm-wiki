#!/usr/bin/env python3
"""
Pre-compact hook — extracts conversation context and spawns flush.py.

Same shape as session-end but with a higher MIN_TURNS_TO_FLUSH so only
substantial conversations get flushed during compaction. Transcript walking
+ tool summarisation live in `_transcript.py` (shared with `session-end.py`).
"""

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

MIN_TURNS_TO_FLUSH = 5

WIKI_DIR = Path(__file__).resolve().parent.parent  # .wiki/
ROOT = WIKI_DIR.parent
SCRIPTS_DIR = WIKI_DIR / "scripts"
LOGS_DIR = WIKI_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
FLUSH_SCRIPT = SCRIPTS_DIR / "flush.py"
LOG_FILE = LOGS_DIR / "flush.log"

sys.path.insert(0, str(SCRIPTS_DIR))
import flush_pipeline  # noqa: E402  staging owned by the pipeline module

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _transcript import build_context, read_transcript  # noqa: E402

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [pre-compact] %(message)s",
)
log = logging.getLogger(__name__)


def main() -> None:
    # Recursion guard
    if os.environ.get("CLAUDE_INVOKED_BY"):
        log.debug("Recursion guard: CLAUDE_INVOKED_BY is set, exiting.")
        return

    # Read hook input from stdin
    try:
        raw_input = sys.stdin.read()
    except Exception as e:
        log.error(f"Failed to read stdin: {e}")
        return

    if not raw_input.strip():
        log.warning("Empty stdin, exiting.")
        return

    try:
        # Fix Windows-style unescaped backslashes in paths
        fixed = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r"\\\\", raw_input)
        hook_input = json.loads(fixed)
    except json.JSONDecodeError as e:
        log.error(f"Failed to parse hook input: {e}")
        return

    session_id = hook_input.get("session_id", "unknown")
    transcript_path = hook_input.get("transcript_path", "")

    if not transcript_path:
        log.warning("No transcript_path in hook input, exiting.")
        return

    log.info(f"Processing pre-compact for session {session_id}")

    turns = read_transcript(transcript_path)
    log.info(f"Found {len(turns)} turns in transcript")

    if len(turns) < MIN_TURNS_TO_FLUSH:
        log.info(
            f"Only {len(turns)} turns (min {MIN_TURNS_TO_FLUSH}), skipping flush."
        )
        return

    context = build_context(turns)

    staged = flush_pipeline.stage("pre-compact", session_id, context)
    context_file = staged.path
    log.info(f"Wrote context to {context_file}")

    # Spawn flush.py in background
    if not FLUSH_SCRIPT.exists():
        log.error(f"flush.py not found at {FLUSH_SCRIPT}")
        return

    # --project pins uv to .wiki/pyproject.toml regardless of CWD; see session-end.py.
    cmd = ["uv", "run", "--project", str(WIKI_DIR), "python", str(FLUSH_SCRIPT), str(context_file), session_id]

    kwargs: dict = {}
    if sys.platform == "win32":
        CREATE_NO_WINDOW = 0x08000000
        kwargs["creationflags"] = CREATE_NO_WINDOW

    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )
    log.info(f"Spawned flush.py for pre-compact session {session_id}")


if __name__ == "__main__":
    main()
