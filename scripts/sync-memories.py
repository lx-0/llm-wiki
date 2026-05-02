"""
Sync Claude Code project memories and CLAUDE.md files into raw/memories/.

File-per-memory pattern (Option A):
- Each memory file → its own source: raw/memories/{project}__{memory_name}.md
- Each project's CLAUDE.md (from cwd in session jsonl) → raw/memories/{project}__CLAUDE.md
- Unchanged files produce identical output → compile hash detects no-change → skipped
- Removed memories are deleted from raw/memories/ (keeps the mirror clean)

Runs as a daily piggyback task.

Usage:
    uv run python scripts/sync-memories.py               # sync all
    uv run python scripts/sync-memories.py --dry-run     # show what would change
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

from config import RAW_DIR, today_iso

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
MEMORIES_DIR = RAW_DIR / "memories"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("sync-memories")

_GENERIC_WORKSPACE_DIRS = {
    "Code", "Workspace", "Projects", "projects",
    "src", "Documents", "Repos", "github", "git",
    "Sync", "data", "dev",
}


def _skip_prefixes() -> set[str]:
    """Path components to drop when extracting a project name from an encoded path.

    Auto-derives from the current user's home dir parts (e.g. {"Users", "<username>"} on macOS,
    {"home", "<username>"} on Linux) and unions with common workspace dir names. No hardcoded
    usernames.
    """
    home_parts = set(str(Path.home()).strip("/").split("/"))
    return home_parts | _GENERIC_WORKSPACE_DIRS


def decode_project_name(encoded: str) -> str:
    """Extract short readable name from encoded path."""
    parts = encoded.strip("-").split("-")
    skip = _skip_prefixes()
    meaningful: list[str] = []
    found = False
    for part in parts:
        if found or part not in skip:
            found = True
            meaningful.append(part)
    if not meaningful:
        meaningful = parts[-2:]
    return "-".join(meaningful)


def read_cwd_from_jsonl(project_dir: Path) -> Path | None:
    """Scan session JSONLs for a `cwd` field to find the actual project path."""
    for jsonl in sorted(project_dir.glob("*.jsonl"), reverse=True):
        try:
            with open(jsonl, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or '"cwd"' not in line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    cwd = entry.get("cwd")
                    if cwd:
                        return Path(cwd)
        except OSError:
            continue
    return None


def strip_frontmatter(content: str) -> tuple[str, str]:
    """Return (name, body) — name from frontmatter if present, else empty."""
    content = content.strip()
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            fm = content[3:end]
            m = re.search(r"^name:\s*(.+)$", fm, flags=re.MULTILINE)
            name = m.group(1).strip() if m else ""
            body = content[end + 3:].strip()
            return name, body
    return "", content


def write_memory_source(
    project: str,
    memory_stem: str,
    memory_name: str,
    body: str,
    origin: str,
    dry_run: bool,
) -> Path | None:
    out_path = MEMORIES_DIR / f"{project}__{memory_stem}.md"
    header = [
        "---",
        "type: memory-sync",
        f"date: {today_iso()}",
        f'origin: "{origin}"',
        f"project: {project}",
        f"tags: [{project}, claude-memory, sync]",
        "---",
        "",
        f"# {memory_name or memory_stem}",
        "",
        body,
        "",
    ]
    new_content = "\n".join(header)

    if out_path.exists() and out_path.read_text(encoding="utf-8") == new_content:
        return None  # unchanged

    if dry_run:
        log.info("  [dry-run] would write %s", out_path.name)
        return out_path

    MEMORIES_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(new_content, encoding="utf-8")
    return out_path


def sync(dry_run: bool = False) -> None:
    if not CLAUDE_PROJECTS_DIR.exists():
        log.error("No Claude projects dir at %s", CLAUDE_PROJECTS_DIR)
        return

    MEMORIES_DIR.mkdir(parents=True, exist_ok=True)
    existing = set(MEMORIES_DIR.glob("*.md"))
    written: set[Path] = set()

    changed = 0
    project_dirs = sorted(CLAUDE_PROJECTS_DIR.iterdir())

    for project_dir in project_dirs:
        if not project_dir.is_dir():
            continue

        project = decode_project_name(project_dir.name)
        if not project:
            continue

        # --- Memory files ---
        memory_dir = project_dir / "memory"
        if memory_dir.exists():
            for mf in sorted(memory_dir.glob("*.md")):
                if mf.name == "MEMORY.md":
                    continue  # index, not content
                content = mf.read_text(encoding="utf-8")
                name, body = strip_frontmatter(content)
                origin = f"~/.claude/projects/{project_dir.name}/memory/{mf.name}"
                result = write_memory_source(project, mf.stem, name, body, origin, dry_run)
                if result:
                    changed += 1
                    log.info("  [memory] %s__%s", project, mf.stem)
                written.add(MEMORIES_DIR / f"{project}__{mf.stem}.md")

        # --- Project agent docs (CLAUDE.md and/or AGENTS.md) ---
        cwd = read_cwd_from_jsonl(project_dir)
        if cwd and cwd.exists():
            for doc_name, slug in [("CLAUDE.md", "CLAUDE"), ("AGENTS.md", "AGENTS")]:
                doc_path = cwd / doc_name
                if doc_path.exists():
                    body = doc_path.read_text(encoding="utf-8").strip()
                    origin = str(doc_path)
                    result = write_memory_source(
                        project, slug, f"{doc_name} ({cwd.name})", body, origin, dry_run
                    )
                    if result:
                        changed += 1
                        log.info("  [%s] %s__%s", slug.lower(), project, slug)
                    written.add(MEMORIES_DIR / f"{project}__{slug}.md")

    # --- Cleanup: remove files that no longer exist at source ---
    stale = existing - written
    for s in stale:
        # Only delete files we manage (those with the project__name pattern)
        if "__" not in s.stem:
            continue
        if dry_run:
            log.info("  [dry-run] would delete stale %s", s.name)
        else:
            s.unlink()
            log.info("  [deleted stale] %s", s.name)

    log.info("Done. %d files changed, %d total managed, %d stale removed",
             changed, len(written), len(stale))


def main() -> None:
    p = argparse.ArgumentParser(description="Sync Claude Code memories into raw/memories/")
    p.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = p.parse_args()
    sync(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
