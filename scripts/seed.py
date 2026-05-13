"""
Seed the knowledge base with existing Claude Code memories from all projects.

Collects all memory files from ~/.claude/projects/*/memory/*.md,
groups them by project, and places them as source files in raw/memories/.
Run compile.py afterwards to compile them into wiki articles.

Usage:
    uv run python scripts/seed.py              # collect memories, then compile
    uv run python scripts/seed.py --dry-run    # show what would be collected
    uv run python scripts/seed.py --no-compile # collect only, don't auto-compile
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from core.config import RAW_DIR, ROOT_DIR, now_iso, today_iso

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
MEMORIES_DIR = RAW_DIR / "memories"


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


def decode_project_path(encoded: str) -> str:
    """Decode Claude's project directory name back to a readable name.

    Claude encodes absolute paths by replacing `/` with `-` (e.g.
    `-Users-<user>-Code-someorg-someproject`). We strip the common prefix
    components and keep the meaningful suffix.
    """
    parts = encoded.strip("-").split("-")

    skip = _skip_prefixes()
    meaningful = []
    found_meaningful = False
    for part in parts:
        if found_meaningful or part not in skip:
            found_meaningful = True
            meaningful.append(part)

    if not meaningful:
        meaningful = parts[-2:]  # fallback: last 2 parts

    return "-".join(meaningful)


def collect_memories(dry_run: bool = False) -> list[Path]:
    """Collect all memory files from all Claude Code projects."""
    if not CLAUDE_PROJECTS_DIR.exists():
        print("No Claude projects directory found at ~/.claude/projects/")
        return []

    created_files = []
    project_dirs = sorted(CLAUDE_PROJECTS_DIR.iterdir())

    for project_dir in project_dirs:
        memory_dir = project_dir / "memory"
        if not memory_dir.exists():
            continue

        memory_files = sorted(memory_dir.glob("*.md"))
        # Skip MEMORY.md (it's just an index)
        memory_files = [f for f in memory_files if f.name != "MEMORY.md"]

        if not memory_files:
            continue

        project_name = decode_project_path(project_dir.name)
        print(f"\n  Project: {project_name} ({len(memory_files)} memories)")

        if dry_run:
            for mf in memory_files:
                print(f"    {mf.name}")
            continue

        # Combine all memories from this project into one source file
        output_dir = MEMORIES_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{project_name}.md"

        lines = [
            "---",
            "type: memory-seed",
            f"date: {today_iso()}",
            f'origin: "~/.claude/projects/{project_dir.name}/memory/"',
            f"tags: [{project_name}, claude-memory, seed]",
            "language: de",
            "---",
            "",
            f"# Claude Code Memories: {project_name}",
            "",
            f"> Seeded from {len(memory_files)} memory files on {today_iso()}.",
            "",
        ]

        for mf in memory_files:
            content = mf.read_text(encoding="utf-8").strip()
            # Strip frontmatter from memory file for clean embedding
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    # Extract name from frontmatter
                    frontmatter = content[3:end]
                    name_match = re.search(r"name:\s*(.+)", frontmatter)
                    name = name_match.group(1).strip() if name_match else mf.stem
                    body = content[end + 3:].strip()
                else:
                    name = mf.stem
                    body = content
            else:
                name = mf.stem
                body = content

            lines.append(f"## {name}")
            lines.append("")
            lines.append(body)
            lines.append("")
            print(f"    + {mf.name}")

        output_file.write_text("\n".join(lines), encoding="utf-8")
        created_files.append(output_file)
        print(f"    → {output_file.relative_to(ROOT_DIR)}")

    return created_files


def main():
    parser = argparse.ArgumentParser(description="Seed knowledge base from Claude Code memories")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be collected")
    parser.add_argument("--no-compile", action="store_true", help="Collect only, don't auto-compile")
    args = parser.parse_args()

    print(f"Scanning {CLAUDE_PROJECTS_DIR} for memories...")

    created = collect_memories(dry_run=args.dry_run)

    if args.dry_run:
        # Count projects that have memories
        project_count = sum(
            1 for d in CLAUDE_PROJECTS_DIR.iterdir()
            if (d / "memory").exists()
            and any(f.name != "MEMORY.md" for f in (d / "memory").glob("*.md"))
        )
        print(f"\n[dry-run] Would create {project_count} source files in raw/memories/.")
        return

    if not created:
        print("\nNo memories found to seed.")
        return

    print(f"\nSeeded {len(created)} project memory files into raw/memories/")

    if args.no_compile:
        print("Skipping compilation (--no-compile). Run manually:")
        print("  uv run python scripts/compile.py")
        return

    print("\nStarting compilation...")
    compile_script = ROOT_DIR / "scripts" / "compile.py"
    subprocess.run(
        ["uv", "run", "python", str(compile_script)],
        cwd=str(ROOT_DIR),
    )


if __name__ == "__main__":
    main()
