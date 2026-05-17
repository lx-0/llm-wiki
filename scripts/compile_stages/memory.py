"""Memory-substrate pre-pass: resolve project page + bootstrap Timeline section.

Runs Python-side before the SDK call so `compile_memories.md` can be truly
mechanical (Read → Edit-append, 2-3 turns max). Without this, the prompt
had to instruct Haiku to fuzzy-search across `knowledge/projects/` and
either burned turns hunting alternatives (original loose prompt, $0.35/chunk
at max_turns) or emitted `no_project_page` on most files (overcorrected
strict prompt — see incident 2026-05-17).

Two public entrypoints:

* `resolve_project_slug(source, frontmatter, vault_root)` — three-tier
  lookup (filename stem → frontmatter `project:` after path-prefix strip →
  filtered tags), then exact-match-then-unique-substring against
  `knowledge/projects/*.md`. Returns the matched project stem or None.

* `ensure_timeline_section(project_page)` — idempotent: appends an empty
  `## Timeline` heading if absent. Required because 38/61 project pages on
  the operator vault had no Timeline section, leaving the prompt's
  "Edit-append under the heading" instruction undefined.
"""

from __future__ import annotations

from pathlib import Path

# Tags that decorate memory files for routing but don't identify the project.
# Used to filter the tag-fallback candidates so we don't try to match
# "claude-memory" against `knowledge/projects/*.md`.
_UTILITY_TAGS = frozenset({"claude-memory", "memory", "sync", "seed"})


def _strip_path_prefix(s: str) -> str:
    """Strip the path-encoded prefix from a memory-sync `project:` value.

    The collector encodes the source file's full path as dash-separated
    segments. The slug we want is everything after the last `-projects-`
    marker (the standard `projects/` directory layout). Files outside a
    `projects/` tree fall back to a leading-dash strip so values like
    `-paperclip-playground` reduce to `paperclip-playground`.

    Examples:
        'home-alex-Code-WebDev-projects-lx-0-llm-wiki' → 'lx-0-llm-wiki'
        'home-alex-Code-WebDev-projects-yesterday-ai-openclaw' → 'yesterday-ai-openclaw'
        '-paperclip-playground' → 'paperclip-playground'
        'home-alex-Code-WebDev' → 'home-alex-Code-WebDev'  (no marker, as-is)
        '' → ''
    """
    if not s:
        return ""
    marker = "-projects-"
    idx = s.rfind(marker)
    if idx >= 0:
        return s[idx + len(marker):]
    return s.lstrip("-")


def _extract_tag_slugs(tags: object) -> list[str]:
    """Filter utility tags out of a frontmatter `tags:` list.

    Memory files tag themselves with `[<project-slug>, claude-memory, seed]`
    or `[<project-slug>, claude-memory, sync]`. We want the project slug,
    not the routing decoration.
    """
    if not isinstance(tags, list):
        return []
    return [t for t in tags if isinstance(t, str) and t and t not in _UTILITY_TAGS]


def resolve_project_slug(
    source: Path,
    frontmatter: dict,
    vault_root: Path,
) -> str | None:
    """Find the project page that this memory file should back-link to.

    Three-tier candidate generation:
      1. `source.stem`               — memory-seed naming (`yesterday-ai-openclaw.md`)
      2. `frontmatter["project"]`    — memory-sync (path-encoded; stripped)
      3. tags minus utility tags     — both substrates, last resort

    Match strategy (per-tier, but checked across all candidates):
      A. Exact: `knowledge/projects/<candidate>.md` exists → return candidate.
      B. Unique substring: exactly one project stem contains the candidate
         (or vice versa) → return that stem. Multiple matches → None
         (don't guess on ambiguous slugs like 'paperclip' which matches 8 pages).

    Returns:
        Project stem (filename without `.md`) on match, else None.
    """
    candidates: list[str] = []
    candidates.append(source.stem)
    raw_project = frontmatter.get("project", "")
    if isinstance(raw_project, str):
        candidates.append(_strip_path_prefix(raw_project))
    candidates.extend(_extract_tag_slugs(frontmatter.get("tags")))
    # De-dup while preserving order so the cheapest signal wins ties.
    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)

    projects_dir = vault_root / "knowledge" / "projects"
    if not projects_dir.is_dir():
        return None
    all_stems = sorted(p.stem for p in projects_dir.glob("*.md"))

    # Tier A: exact match across all candidates.
    stem_set = set(all_stems)
    for slug in ordered:
        if slug in stem_set:
            return slug

    # Tier B: unique substring match.
    for slug in ordered:
        matches = [s for s in all_stems if slug in s or s in slug]
        if len(matches) == 1:
            return matches[0]

    return None


def ensure_timeline_section(project_page: Path) -> None:
    """Append `## Timeline` to a project page if absent. Idempotent.

    The compile_memories prompt edits *under an existing Timeline heading*.
    Without this bootstrap, 62% of operator vault project pages would force
    the prompt into undefined behavior (either fabricate a section without
    correct positioning, or burn turns searching for one). Bootstrap runs
    Python-side so it's deterministic and cheap.
    """
    text = project_page.read_text(encoding="utf-8")
    if "## Timeline" in text:
        return
    new_text = text.rstrip() + "\n\n## Timeline\n"
    project_page.write_text(new_text, encoding="utf-8")
