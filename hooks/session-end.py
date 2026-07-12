#!/usr/bin/env python3
"""
Session end hook — extracts conversation context and spawns flush.py.

Reads the JSONL transcript, summarises the last N turns, stages it via
flush_pipeline, and spawns flush.py in the background to compile learnings.
Transcript walking + tool summarisation live in `_transcript.py`
(shared with `pre-compact.py`).
"""

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

MIN_TURNS_TO_FLUSH = 1

WIKI_DIR = Path(__file__).resolve().parent.parent  # .wiki/
ROOT = WIKI_DIR.parent
SCRIPTS_DIR = WIKI_DIR / "scripts"
LOGS_DIR = WIKI_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
FLUSH_SCRIPT = SCRIPTS_DIR / "flush.py"
LOG_FILE = LOGS_DIR / "flush.log"

sys.path.insert(0, str(SCRIPTS_DIR))
from core import flush_pipeline  # noqa: E402  staging owned by the pipeline module

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _transcript import build_context, read_transcript  # noqa: E402

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [hook] %(message)s",
)
log = logging.getLogger(__name__)


def capture_id_for_hook(hook_input: dict) -> str:
    """Return a unique flush identity for this hook invocation.

    Claude Code's SessionEnd is session-scoped, while Codex Stop is
    turn-scoped. Using Codex's turn_id prevents adjacent turns in one thread
    from colliding with flush.py's session-level deduplication window.
    """
    if hook_input.get("hook_event_name") == "Stop" and hook_input.get("turn_id"):
        return str(hook_input["turn_id"])
    return str(hook_input.get("session_id", "unknown"))


def background_popen_kwargs(platform_name: str = sys.platform) -> dict:
    """Return flags that keep the background flush alive after the hook exits."""
    if platform_name == "win32":
        create_no_window = 0x08000000
        return {"creationflags": create_no_window}
    return {"start_new_session": True}


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
    turn_id = hook_input.get("turn_id")
    capture_id = capture_id_for_hook(hook_input)
    transcript_path = hook_input.get("transcript_path", "")

    if not transcript_path:
        log.warning("No transcript_path in hook input, exiting.")
        return

    log.info(f"Processing session {session_id} capture {capture_id}")

    turns = read_transcript(transcript_path, turn_id=turn_id)
    log.info(f"Found {len(turns)} turns in transcript")

    if len(turns) < MIN_TURNS_TO_FLUSH:
        log.info(
            f"Only {len(turns)} turns (min {MIN_TURNS_TO_FLUSH}), skipping flush."
        )
        return

    context = build_context(turns)

    staged = flush_pipeline.stage("session-end", capture_id, context)
    context_file = staged.path
    log.info(f"Wrote context to {context_file}")

    # Spawn flush.py in background
    if not FLUSH_SCRIPT.exists():
        log.error(f"flush.py not found at {FLUSH_SCRIPT}")
        return

    # --project pins uv to .wiki/pyproject.toml regardless of the CWD the hook
    # was launched from. Without it, uv searches CWD upward for pyproject and
    # would fail since the vault root no longer carries one.
    cmd = [
        "uv",
        "run",
        "--project",
        str(WIKI_DIR),
        "python",
        str(FLUSH_SCRIPT),
        str(context_file),
        capture_id,
    ]

    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **background_popen_kwargs(),
    )
    log.info(f"Spawned flush.py for session {session_id} capture {capture_id}")


if __name__ == "__main__":
    main()
