"""The seed's pure core (M034-S04-T02) — what `wiki seed` walks and how it derives a config,
held to the output the bash `lib/seed.sh` recorded before it was deleted
(`tests/golden/seed/`, `tests/test_seed_core.py`).

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

import re
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


# ── The special merges (M034-S04-T03) ─────────────────────────────────────────
# Pure: each takes the parsed vault file and the engine's side and returns what to write and
# what to report; the reading, the messages and the writing are the command's. Held to the
# bash they replace by tests/test_seed_merges.py.


class ShapeError(ValueError):
    """JSON of a shape a merge does not expect — where jq errs, and the bash leaves the file
    as it is ("not in the shape seed expects")."""


def _list_in(value: object, key: str) -> object:
    """jq's `l`: the file itself (``key == ""``), or `.[$key] // []`."""
    if key == "":
        return value
    if value is None:
        return []
    if not isinstance(value, dict):
        raise ShapeError(f"not an object: cannot read {key!r}")
    item = value.get(key)
    return [] if item is None or item is False else item


def union_list(current: object, engine: object, key: str) -> tuple[object, list]:
    """`_merge_list_union` — community-plugins.json (``key == ""``: the file is the list) or a
    list under ``key`` (appearance.json's enabledCssSnippets). Returns the file to write and
    the engine entries it adds; ``(None, [])`` when there is nothing to add, so a current
    file stays as the operator wrote it. The union is jq's `unique` of both lists: sorted,
    duplicates gone. A list under ``key`` keeps its place in the object, or is appended."""
    have, want = _list_in(current, key), _list_in(engine, key)
    if not isinstance(have, list) or not isinstance(want, list):
        raise ShapeError(f"not a list: {key or 'the file'}")
    adding = jqjson.subtract(want, have)
    if not adding:
        return None, []
    merged = jqjson.unique(have + want)
    if key == "":
        return merged, adding
    return {**(current if isinstance(current, dict) else {}), key: merged}, adding


def engine_entries(template: object, key: str, generated: list) -> list:
    """A registry's engine entries: the template's list under ``key``, then the agent buttons'
    (``generated``, from `dashboard.agent_buttons` — the templates carry none of those)."""
    own = template.get(key) if isinstance(template, dict) else None
    return [*(own or []), *generated]


def _registry_list(value: object) -> list:
    """jq's `as_list`: the plugin's list, or the Shell commands plugin's legacy id-keyed
    object read the way the plugin migrates it (the key becomes the entry's `id`); anything
    else, no entries."""
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return []
    entries = []
    for entry_id, entry in value.items():
        if entry is not None and not isinstance(entry, dict):
            raise ShapeError(f"legacy entry {entry_id!r} is not an object")
        entries.append({**(entry or {}), "id": entry_id})
    return entries


def _entry_id(entry: object) -> object:
    """`.id` as jq reads it: null for null, an error for anything but an object."""
    if entry is None:
        return None
    if not isinstance(entry, dict):
        raise ShapeError("a registry entry is not an object")
    return entry.get("id")


def merge_registry(config: object, key: str, engine: list) -> tuple[object, list, list]:
    """`_merge_registry` — the engine's entries merged by id into the list under ``key``
    (Meta-Bind's `buttonTemplates`, Shell commands' `shell_commands`). An entry with an engine
    id takes the engine's fields in place, and the fields the engine does not ship stay (the
    plugin's own, the operator's). A missing engine entry is appended, and every other entry
    is left as it is. Returns ``(merged config, ids added, ids updated)``; the merged config
    equals ``config`` (canonically) when there is nothing to do."""
    if config is not None and not isinstance(config, dict):
        raise ShapeError("the config is not an object")
    current = _registry_list((config or {}).get(key))
    have = [_entry_id(entry) for entry in current]

    def engine_for(entry_id: object) -> dict | None:
        return next((e for e in engine if jqjson.same(e.get("id"), entry_id)), None)

    kept, updated = [], []
    for entry, entry_id in zip(current, have, strict=True):
        ours = engine_for(entry_id)
        if ours is None:
            kept.append(entry)
            continue
        merged_entry = {**(entry or {}), **ours}
        if not jqjson.same(merged_entry, entry):
            updated.append(entry_id)
        kept.append(merged_entry)
    new = [e for e in engine if not any(jqjson.same(e.get("id"), i) for i in have)]
    merged = {**(config or {}), key: kept + new}
    return merged, [e.get("id") for e in new], updated


# `.claude/.env.example`: active `KEY=` lines (the bash's `grep -oE '^[A-Z_][A-Z0-9_]*='`).
_ENV_KEY = re.compile(r"^([A-Z_][A-Z0-9_]*)=", re.MULTILINE)
_BLANK = re.compile(r"[ \t\v\f\r]*")  # awk's /^[[:space:]]*$/ on one line


def env_missing(template: str, current: str) -> list[str]:
    """`_merge_env_example`'s missing vars: the template's active `KEY=` names, sorted and
    unique (the bash's `sort -u`; code-point order here, the caller's locale there — the same
    for these upper-case names), that the operator's file has neither as `KEY=` nor as a
    commented `# KEY=`."""
    names = sorted(set(_ENV_KEY.findall(template)))
    return [
        name
        for name in names
        if not re.search(rf"^[ \t\v\f\r]*#?[ \t\v\f\r]*{name}=", current, re.MULTILINE)
    ]


def _env_stanza(template: str, name: str) -> str:
    """The awk stanza: the `#` lines right above the template's `NAME=` line, then that line.
    A blank line, or any other line, between them resets the comment block."""
    block: list[str] = []
    for line in template.split("\n"):
        if _BLANK.fullmatch(line):
            block = []
        elif line.startswith("#"):
            block.append(line)
        elif line.startswith(f"{name}="):
            return "\n".join([*block, line])
        else:
            block = []
    return f"{name}="


def env_appended(template: str, current: str, missing: list[str]) -> str:
    """The operator's file with each missing var's stanza appended, as the bash's
    `printf '\\n\\n%s\\n' "$stanza" >> "$dst"` does — the file itself left byte for byte."""
    return current + "".join(f"\n\n{_env_stanza(template, name)}\n" for name in missing)
