"""The seed's pure core (M034-S04-T02) — what `lib/seed.sh` walks and how it derives a config,
held to output the bash recorded (`tests/golden/seed/`, `tests/test_seed_core.py`).

- `walk` lists the files `wiki seed` puts into a vault, in the bash's order, each with the
  way it is seeded. Only the listed templates are seeded: the `_dashboard-*.md` caches are
  producer outputs, never templates, and a missing template is skipped.
- A JSON config the engine owns and the operator tunes is derived as **template ⊕ overlay**:
  the operator's delta lives in `<vault>/.wiki/custom/<path>`, the live file is `derive`d.
  `apply_overlay` is the bash's element-wise deep merge, `compute_overlay` its leaf diff
  (what `--extract-custom` captures).
- A copied file (markdown, html, css, yaml) is the same as its template byte for byte. The
  bash's `_files_equivalent` also had a `jq -S` branch for `.json`, but it was dead: a JSON
  template reaches the copy only through the no-jq fallback, and that branch needed jq.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core import jqjson

# How each file is seeded (the bash function that does it):
#   copy               _seed_file             copy if missing, --force overwrites
#   overlay            _seed_json_overlay     template ⊕ the operator's overlay
#   plugin-list        _merge_list_union      community-plugins.json: the engine's added
#   snippet-list       _merge_list_union      appearance.json's enabledCssSnippets, the same
#   button-templates   _merge_registry        Meta-Bind's buttonTemplates, by id
#   shell-commands     _merge_registry        Shell commands' shell_commands, by id
#   env                _merge_env_example     .claude/.env.example, per-variable append
_TOP_LEVEL_LISTS = {"community-plugins.json": "plugin-list", "appearance.json": "snippet-list"}
_REGISTRIES = {
    "plugins/obsidian-meta-bind-plugin/data.json": "button-templates",
    "plugins/obsidian-shellcommands/data.json": "shell-commands",
}


@dataclass(frozen=True)
class Entry:
    template: Path
    label: str  # the vault-relative path: what seed prints, what `wiki seed <path>` names
    kind: str


def _glob(directory: Path, pattern: str) -> list[Path]:
    """A shell glob: sorted, files only, no dotfiles (`*` skips them in bash, not in
    pathlib)."""
    if not directory.is_dir():
        return []
    found = (path for path in directory.glob(pattern) if path.is_file())
    return sorted(
        path
        for path in found
        if not any(part.startswith(".") for part in path.relative_to(directory).parts)
    )


def walk(templates: Path) -> list[Entry]:
    """The files `wiki seed` writes, in the order `seed_vault_templates` walks them."""
    entries: list[Entry] = []

    def add(template: Path, label: str, kind: str = "copy") -> None:
        if template.is_file():
            entries.append(Entry(template, label, kind))

    add(templates / "README.md", "README.md")
    add(templates / "AGENTS.example.md", "AGENTS.md")
    for name in ("dashboard.md", "knowledge.base", "triage.html"):
        add(templates / name, name)
    for folder in ("Templates", "knowledge/MOCs"):
        for path in _glob(templates / folder, "*.md"):
            add(path, f"{folder}/{path.name}")
    add(templates / "workspace" / "todo.md", "workspace/todo.md")
    obsidian = templates / ".obsidian"
    if obsidian.is_dir():
        for path in _glob(obsidian, "*.json"):
            add(path, f".obsidian/{path.name}", _TOP_LEVEL_LISTS.get(path.name, "overlay"))
        for path in _glob(obsidian / "snippets", "*.css"):
            add(path, f".obsidian/snippets/{path.name}")
        # `find … -name '*.json' | LC_ALL=C sort`: every depth, dotfiles included, sorted
        # as whole path strings (not by parts: `a-b/x` sorts before `a/x`).
        plugins = obsidian / "plugins"
        if plugins.is_dir():
            found = (path for path in plugins.rglob("*.json") if path.is_file())
            for path in sorted(found, key=lambda p: p.as_posix()):
                rel = path.relative_to(obsidian).as_posix()
                add(path, f".obsidian/{rel}", _REGISTRIES.get(rel, "overlay"))
    for manifest in _glob(templates / "reports" / "studies", "*/manifest.yaml"):
        add(manifest, f"reports/studies/{manifest.parent.name}/manifest.yaml")
    add(templates / ".claude" / ".env.example", ".claude/.env.example", "env")
    return entries


def apply_overlay(base: object, overlay: object) -> object:
    """``base`` ⊕ ``overlay``: objects merge key by key (the base's keys keep their places,
    new ones are appended), arrays element by element (by index — not jq's `*`, which
    replaces a whole array with a sparse overlay one), an overlay `null` keeps the base,
    anything else from the overlay wins."""
    if overlay is None:
        return base
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        for key, value in overlay.items():
            merged[key] = apply_overlay(base.get(key), value)
        return merged
    if isinstance(base, list) and isinstance(overlay, list):
        return [
            apply_overlay(
                base[i] if i < len(base) else None, overlay[i] if i < len(overlay) else None
            )
            for i in range(max(len(base), len(overlay)))
        ]
    return overlay


def compute_overlay(base: object, current: object) -> object:
    """The minimal overlay: every leaf of ``current`` that differs from ``base``, set into
    `{}` (arrays padded with nulls, which `apply_overlay` reads as "keep"). A removed key or
    an emptied container is not expressed — overlays only override."""
    delta: object = {}
    for path in jqjson.leaf_paths(current):
        value = jqjson.getpath(current, path)
        if not jqjson.same(jqjson.getpath(base, path), value):
            delta = jqjson.setpath(delta, path, value)
    return delta


def overrides(delta: object) -> int:
    """The count `--extract-custom` reports."""
    return sum(1 for _ in jqjson.leaf_paths(delta))


def derive(template: Path, overlay: Path) -> str:
    """The text seed writes for an overlay-managed config: template ⊕ overlay as jq renders
    it, or — no overlay file — the template as it is, ending in one newline (the bash's
    `printf '%s\\n' "$(cat …)"`). An empty overlay file reads as no overlay content, as jq's
    `--slurpfile` reads it, but the result is still rendered."""
    if not overlay.is_file():
        return template.read_text(encoding="utf-8").rstrip("\n") + "\n"
    text = overlay.read_text(encoding="utf-8")
    delta = jqjson.loads(text) if text.strip() else None
    return jqjson.render(apply_overlay(jqjson.load(template), delta))
