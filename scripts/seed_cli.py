"""`wiki seed` (M034-S04-T04) — re-apply the engine's templates to the vault.

The command around `core.seed`: the argv, the banner, a status line per file in the bash's
own words, the writes, `--extract-custom`, the dashboard's agent-button region, and the
dashboards refresh after a writing run. The bash `cmd_seed` / `lib/seed.sh` it replaces is
recorded in tests/golden/bash/seed-*.txt; every message, file and exit code there holds.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

from cli_help import H_SEED
from core import jqjson, seed
from core.console import banner, fail, info, ok, warn
from core.paths import ROOT_DIR, WIKI_DIR
from dashboard import agent_buttons

_PLAIN = re.compile(r"[A-Za-z0-9._/@+-]+")
_LISTS = {"plugin-list": ("", ""), "snippet-list": ("enabledCssSnippets", "snippet")}
_REGISTRIES = {"button-templates": "buttonTemplates", "shell-commands": "shell_commands"}
_INSTALL = "(run `wiki seed` to install)"
_LEFT = "left as it is (fix it, or remove it and rerun `wiki seed`)"
# Not derived from an overlay: the configs seed merges (bash `_extract_overlay`'s case).
_MERGED = {
    ".obsidian/community-plugins.json",
    ".obsidian/appearance.json",
    ".obsidian/plugins/obsidian-meta-bind-plugin/data.json",
    ".obsidian/plugins/obsidian-shellcommands/data.json",
}
_SEEDABLE = (
    "  seedable paths: README.md, AGENTS.md, dashboard.md, knowledge.base, triage.html,\n"
    "    workspace/todo.md, .claude/.env.example, .obsidian/*.json, .obsidian/snippets/*.css,\n"
    "    .obsidian/plugins/<p>/data.json, Templates/*.md, knowledge/MOCs/*.md,\n"
    "    reports/studies/<id>/manifest.yaml"
)


def _force_cmd(label: str) -> str:
    """The targeted overwrite for one file — the advice for one drifted file is never the
    whole-vault `wiki seed --force`. Quoted for the shell when the path needs it."""
    path = label if _PLAIN.fullmatch(label) else "'" + label.replace("'", "'\\''") + "'"
    return f"`wiki seed {path} --force`"


def _is_json(path: Path) -> bool:
    try:
        _load(path)
    except ValueError:
        return False
    return True


def _load(path: Path) -> object:
    """A JSON file as jq's `--slurpfile … $x[0]` reads it: an empty file is null."""
    text = path.read_text(encoding="utf-8")
    return jqjson.loads(text) if text.strip() else None


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _replace(path: Path, text: str) -> None:
    """The bash's `> "$dst.tmp" && mv "$dst.tmp" "$dst"`."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _copy(template: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, dst)


def _json_trouble(path: Path, label: str) -> None:
    """Why a file seed merges into could not be merged, and that it is left alone."""
    if _is_json(path):
        warn(f"{label} is not in the shape seed expects — {_LEFT}")
    else:
        warn(f"{label} is not valid JSON — {_LEFT}")


class Seeder:
    """One `wiki seed` run over the vault at ``root``."""

    def __init__(self, root: Path, wiki: Path, *, force: bool, check: bool) -> None:
        self.root = root
        self.wiki = wiki
        self.force = force
        self.check = check

    # ── copy: markdown, html, css, yaml (bash `_seed_file`) ──────────────────

    def copy(self, entry: seed.Entry) -> None:
        dst = self.root / entry.label
        label = entry.label
        same = dst.is_file() and dst.read_bytes() == entry.template.read_bytes()
        if self.check:
            if not dst.is_file():
                warn(f"missing {label} {_INSTALL}")
            elif same:
                ok(f"up-to-date {label}")
            else:
                info(
                    f"drifted {label} (engine template differs; {_force_cmd(label)} overwrites it)"
                )
            return
        if not dst.is_file():
            _copy(entry.template, dst)
            ok(f"seeded {label}")
        elif self.force:
            _copy(entry.template, dst)
            ok(f"overwrote {label} (--force)")
        elif same:
            info(f"kept existing {label} (up-to-date)")
        else:
            info(f"kept existing {label} (drifted from engine; {_force_cmd(label)} overwrites it)")

    # ── template ⊕ overlay (bash `_seed_json_overlay`) ───────────────────────

    def overlay(self, entry: seed.Entry) -> None:
        rel = entry.label
        dst = self.root / rel
        overlay = self.wiki / "custom" / rel
        has_overlay = overlay.is_file()
        if has_overlay and not _is_json(overlay):
            # never skip a broken overlay in silence: --force would re-derive the template
            # alone over the very file the overlay exists to keep
            warn(
                f"{rel} left as it is — its overlay .wiki/custom/{rel} is not valid JSON (fix the overlay)"
            )
            return
        desired = seed.derive(entry.template, overlay)
        tag = " (overlay applied)" if has_overlay else ""
        broken = dst.is_file() and not _is_json(dst)
        same = (
            dst.is_file()
            and not broken
            and _canonical(dst) == jqjson.canonical(jqjson.loads(desired))
        )
        if self.check:
            if not dst.is_file():
                warn(f"missing {rel} {_INSTALL}")
            elif broken:
                warn(f"{rel} is not valid JSON ({_force_cmd(rel)} re-derives it)")
            elif same:
                ok(f"up-to-date {rel}{tag}")
            elif has_overlay:
                info(
                    f"drifted {rel} (live ≠ template⊕overlay — `wiki seed {rel} --force` "
                    f"re-derives; or `wiki seed --extract-custom {rel}` to capture new edits)"
                )
            else:
                info(
                    f"drifted {rel} (uncaptured edits — `wiki seed --extract-custom {rel}` "
                    "makes them survive engine updates)"
                )
            return
        if not dst.is_file():
            _write(dst, desired)
            ok(f"seeded {rel}" + (" (+overlay)" if has_overlay else ""))
        elif same:
            info(f"kept existing {rel} (up-to-date{tag})")
        elif self.force:
            _write(dst, desired)
            ok(
                f"re-derived {rel} from template"
                + ("⊕overlay" if has_overlay else "")
                + " (--force)"
            )
        elif broken:
            warn(
                f"kept existing {rel} (not valid JSON — fix it, or {_force_cmd(rel)} re-derives it)"
            )
        elif has_overlay:
            info(
                f"kept existing {rel} (drifted from template⊕overlay; {_force_cmd(rel)} re-derives it)"
            )
        else:
            info(
                f"kept existing {rel} (drifted; `wiki seed --extract-custom {rel}` captures your "
                f"edits, then {_force_cmd(rel)} is safe)"
            )

    # ── a list the engine's entries are added to (bash `_merge_list_union`) ──

    def list_union(self, entry: seed.Entry) -> None:
        key, noun = _LISTS[entry.kind]
        label, dst = entry.label, self.root / entry.label
        if not dst.is_file():
            if self.check:
                warn(f"missing {label} {_INSTALL}")
            else:
                _copy(entry.template, dst)
                ok(f"seeded {label}")
            return
        try:
            merged, adding = seed.union_list(_load(dst), jqjson.load(entry.template), key)
        except (ValueError, seed.ShapeError):
            _json_trouble(dst, label)
            return
        if not adding:
            if self.check:
                ok(f"up-to-date {label}")
            else:
                info(f"kept existing {label} (up-to-date)")
            return
        names = ", ".join(_text(item) for item in adding)
        what = f"{noun}{'s' if ', ' in names else ''} {names}" if noun else names
        if self.check:
            info(f"drifted {label} (would enable {what})")
            return
        _replace(dst, jqjson.render(merged))
        ok(f"merged {label} (enabled {what})")

    # ── a button registry, by id (bash `_merge_registry`) ────────────────────

    def registry(self, entry: seed.Entry) -> None:
        key = _REGISTRIES[entry.kind]
        label, dst = entry.label, self.root / entry.label
        if not dst.is_file() and self.check:
            warn(f"missing {label} {_INSTALL}")
            return
        engine = seed.engine_entries(
            jqjson.load(entry.template), key, agent_buttons.registry_entries(key)
        )
        base = dst if dst.is_file() else entry.template
        try:
            if not base.read_text(encoding="utf-8").strip():
                # jq reads no input at all from an empty file — no merge, the shape trouble
                raise seed.ShapeError("empty")
            config = _load(base)
            merged, added, updated = seed.merge_registry(config, key, engine)
        except (ValueError, seed.ShapeError):
            _json_trouble(base, label)
            return
        if not dst.is_file():
            _write(dst, jqjson.render(merged))
            ok(f"seeded {label}")
            return
        if jqjson.canonical(merged) == jqjson.canonical(config):
            if self.check:
                ok(f"up-to-date {label}")
            else:
                info(f"kept existing {label} (up-to-date)")
            return
        verbs = ("would add", "would update") if self.check else ("added", "updated")
        parts = [f"{verbs[0]} {', '.join(added)}"] if added else []
        if updated:
            parts.append(f"{verbs[1]} {', '.join(updated)}")
        rewritten = "would be rewritten" if self.check else "rewritten"
        what = "; ".join(parts) or f"{rewritten} in the plugin's list form"
        if self.check:
            info(f"drifted {label} ({key}: {what})")
            return
        _replace(dst, jqjson.render(merged))
        ok(f"merged {label} ({key}: {what})")

    # ── .claude/.env.example (bash `_merge_env_example`) ─────────────────────

    def env(self, entry: seed.Entry) -> None:
        label, dst = entry.label, self.root / entry.label
        if not dst.is_file():
            if self.check:
                warn(f"missing {label} {_INSTALL}")
            else:
                _copy(entry.template, dst)
                ok(f"seeded {label}")
            return
        if self.force:
            _copy(entry.template, dst)
            ok(f"overwrote {label} (--force)")
            return
        template = entry.template.read_text(encoding="utf-8")
        current = dst.read_text(encoding="utf-8")
        missing = seed.env_missing(template, current)
        if not missing:
            if self.check:
                ok(f"up-to-date {label}")
            else:
                info(f"kept existing {label} (up-to-date — all engine vars present)")
            return
        names = " ".join(missing)
        if self.check:
            info(f"drifted {label} (engine adds: {names} — would append {len(missing)} stanza(s))")
            return
        with dst.open("a", encoding="utf-8") as out:
            out.write(seed.env_appended(template, current, missing)[len(current) :])
        ok(f"{label} — appended {len(missing)} engine var(s): {names}")

    # ── the dashboard's agent-button region (bash `_rewrite_dashboard_agent_buttons`) ──

    def dashboard_buttons(self) -> None:
        dashboard = self.root / "dashboard.md"
        if not dashboard.is_file():
            return
        try:
            if not agent_buttons.has_region(dashboard.read_text(encoding="utf-8")):
                info("dashboard.md has no agent-buttons region — left as it is")
            elif agent_buttons.update_dashboard(dashboard):
                ok("dashboard.md — agent-buttons region refreshed")
            else:
                info("dashboard.md — agent-buttons already up to date")
        except (OSError, ValueError):
            warn("dashboard.md — the agent-buttons region could not be refreshed")


def _text(item: object) -> str:
    """An item as jq's `join` writes it."""
    if item is None:
        return ""
    if isinstance(item, str):
        return item
    return jqjson.render(item).strip()


def _canonical(path: Path) -> str:
    return jqjson.canonical(_load(path))


def seed_vault(root: Path, wiki: Path, *, force: bool, check: bool, only: str | None) -> bool:
    """Seed every template (or the one ``only`` names) in the bash's order. Returns False
    when ``only`` matched nothing."""
    seeder = Seeder(root, wiki, force=force, check=check)
    wanted = only.removeprefix("/") if only else None  # the bash's `${only#/}`
    hit = False
    for entry in seed.walk(wiki / "templates"):
        if wanted is not None and entry.label != wanted:
            continue
        hit = True
        if entry.kind == "copy":
            seeder.copy(entry)
        elif entry.kind == "overlay":
            seeder.overlay(entry)
        elif entry.kind in _LISTS:
            seeder.list_union(entry)
        elif entry.kind in _REGISTRIES:
            seeder.registry(entry)
        else:
            seeder.env(entry)
    if not check and (wanted is None or wanted == "dashboard.md"):
        seeder.dashboard_buttons()
        hit = hit or wanted == "dashboard.md"
    return wanted is None or hit


def extract_custom(root: Path, wiki: Path, rel: str) -> int:
    """`--extract-custom`: capture a JSON config's drift from its template into the overlay
    `.wiki/custom/<rel>`, so a `--force` re-derives it instead of losing it."""
    template, dst = wiki / "templates" / rel, root / rel
    overlay = wiki / "custom" / rel
    if rel in _MERGED:
        fail(f"{rel} is merged by seed, not derived from an overlay — there is nothing to capture")
        return 1
    if not (rel.startswith(".obsidian/") and rel.endswith(".json")):
        fail(f"'{rel}' is not overlay-managed (overlays are for the JSON configs under .obsidian/)")
        return 1
    if not template.is_file():
        fail(f"no engine template for '{rel}' (not an overlay-managed file)")
        return 1
    if not dst.is_file():
        fail(f"no live file at {dst}")
        return 1
    if not _is_json(dst):
        fail(f"{rel} is not valid JSON — there is no drift to capture (fix it first)")
        return 1
    try:
        delta = seed.compute_overlay(_load(template), _load(dst))
    except TypeError:
        fail(f"could not compute the drift of {rel}")
        return 1
    if delta == {}:
        info(f"{rel} already matches the engine template — no overlay needed")
        return 0
    _write(overlay, jqjson.render(delta))
    ok(f"extracted overlay → .wiki/custom/{rel} ({seed.overrides(delta)} override(s))")
    info(
        f"from now on edit .wiki/custom/{rel} (not the live file); "
        f"`wiki seed {rel} --force` re-derives"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    force = check = extract = False
    only: str | None = None
    for arg in args:
        if arg == "--force":
            force = True
        elif arg == "--check":
            check = True
        elif arg == "--extract-custom":
            extract = True
        elif arg in ("-h", "--help", "help"):
            print(H_SEED)
            return 0
        elif arg.startswith("--"):
            fail(f"unknown flag: {arg}")
            return 1
        elif only is not None:
            fail(f"wiki seed takes at most one path (got '{only}' and '{arg}')")
            return 1
        else:
            only = arg
    if check and force:
        fail("--check and --force are mutually exclusive")
        return 1
    if not (ROOT_DIR / ".obsidian").is_dir():
        # the bash `wiki` guards every command so; seed writes a whole vault's templates, so
        # it guards itself too (cli.main called straight from a test once seeded the
        # checkout's parent)
        print(
            f"wiki: {ROOT_DIR} is not an Obsidian vault (no .obsidian/ directory).\n"
            "    The engine only runs against real vaults — install it as <vault>/.wiki/\n"
            "    and invoke `wiki` from there.",
            file=sys.stderr,
        )
        return 1
    if extract:
        if not only:
            fail("usage: wiki seed --extract-custom <vault-relative-path>")
            return 1
        banner("wiki seed --extract-custom", only)
        return extract_custom(ROOT_DIR, WIKI_DIR, only)
    mode = "audit (read-only)" if check else "overwrite mode" if force else "additive mode"
    banner("wiki seed", f"{mode} · only: {only}" if only else mode)
    templates = WIKI_DIR / "templates"
    if not templates.is_dir():
        warn(f"no templates dir at {templates}")
        return 1
    if not seed_vault(ROOT_DIR, WIKI_DIR, force=force, check=check, only=only):
        fail(f"no seedable template matches '{only}' — nothing done.")
        print(_SEEDABLE, file=sys.stderr)
        return 1
    if not check:
        from cli import refresh_dashboards

        refresh_dashboards()
    return 0


if __name__ == "__main__":
    sys.exit(main())
