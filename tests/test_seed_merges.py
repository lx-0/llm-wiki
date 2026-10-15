"""The seed's special merges (M034-S04-T03), pure in `core.seed`, held to the bash they replace.

Each case runs the `lib/seed.sh` merge on a copy of its fixture through a driver that
sources the library: `_merge_list_union`, `_merge_registry` (its agent entries stubbed to the
case's), `_merge_env_example`. The record is what the merge reports, from the same jq the
function runs, and the file as it left it, or `(unchanged)`. It is kept under
tests/golden/seed/merge-*.txt (`--snapshot-update`), and Python must reproduce it. The bash
half goes with lib/seed.sh in T05; the goldens stay.

The messages are not recorded here; `wiki seed`'s goldens hold them (tests/golden/bash/).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from core import jqjson, seed
from dashboard import agent_buttons

from ._oracle import REPO_ROOT, assert_matches_golden

GOLDEN = Path(__file__).resolve().parent / "golden" / "seed"
TEMPLATES = REPO_ROOT / "templates"
OBSIDIAN = TEMPLATES / ".obsidian"
PLUGINS = OBSIDIAN / "plugins"
SHELL = PLUGINS / "obsidian-shellcommands" / "data.json"
META_BIND = PLUGINS / "obsidian-meta-bind-plugin" / "data.json"
ENV = TEMPLATES / ".claude" / ".env.example"

_DRIVER = r"""
ok() { :; }; info() { :; }
warn() {
  case "$*" in
    *"is not valid JSON"*) echo "trouble: json" ;;
    *"is not in the shape"*) echo "trouble: shape" ;;
    *) echo "warn: $*" ;;
  esac
}
source "$1"; shift
case "$1" in
  list)
    adding="$(jq -r --arg key "$4" --slurpfile e "$2" "$_LIST_UNION_JQ"' (($e[0] | l) - l) | join(", ")' "$3" 2>/dev/null)" \
      && echo "reported: $adding"
    _merge_list_union "$2" "$3" "label" "$4" "" 0 ;;
  registry)
    generated="$5"
    _agent_entries() { cat "$generated"; }
    engine="$(jq --arg key "$4" --argjson gen "$(cat "$5")" '.[$key] + $gen' "$2")"
    if out="$(jq --arg key "$4" --argjson eng "$engine" "$_REGISTRY_MERGE_JQ" "$3" 2>/dev/null)"; then
      echo "added: $(jq -r '.added | join(", ")' <<<"$out")"
      echo "updated: $(jq -r '.updated | join(", ")' <<<"$out")"
    fi
    _merge_registry "$2" "$3" "label" "$4" "unused" "unused" 0 ;;
  env)
    _merge_env_example "$2" "$3" 0 0 ;;
esac
"""

GENERATED = [
    {"id": "agent-a", "alias": "Wiki: agent a", "icon": "lucide-bot"},
    {"id": "agent-b", "alias": "Wiki: agent b", "icon": "lucide-bot"},
]

# name → (template, the vault's file before; a str is written as is, else as JSON)
LISTS: dict[str, tuple[Path, str, object]] = {
    "plugins-current": (OBSIDIAN / "community-plugins.json", "", "template"),
    "plugins-one-missing-beside-own": (
        OBSIDIAN / "community-plugins.json",
        "",
        ["dataview", "mine", "quickadd", "obsidian-tasks-plugin"],
    ),
    "plugins-unsorted-gets-one": (
        OBSIDIAN / "community-plugins.json",
        "",
        [
            "quickadd",
            "zzz-own",
            "dataview",
            "obsidian-charts",
            "homepage",
            "heatmap-calendar",
            "obsidian-excalidraw-plugin",
            "obsidian-meta-bind-plugin",
            "obsidian-tasks-plugin",
        ],
    ),
    "plugins-duplicates": (
        OBSIDIAN / "community-plugins.json",
        "",
        ["dataview", "dataview", "mine"],
    ),
    "plugins-not-a-list": (OBSIDIAN / "community-plugins.json", "", {"dataview": True}),
    "plugins-not-json": (OBSIDIAN / "community-plugins.json", "", '["dataview",\n'),
    "snippets-own-and-theme": (
        OBSIDIAN / "appearance.json",
        "enabledCssSnippets",
        {"cssTheme": "Minimal", "enabledCssSnippets": ["mine"]},
    ),
    "snippets-no-key": (OBSIDIAN / "appearance.json", "enabledCssSnippets", {"theme": "obsidian"}),
    "snippets-current": (
        OBSIDIAN / "appearance.json",
        "enabledCssSnippets",
        '{"enabledCssSnippets":["wiki-dashboard","mine"],"accentColor":""}\n',
    ),
    "snippets-not-a-list": (
        OBSIDIAN / "appearance.json",
        "enabledCssSnippets",
        {"enabledCssSnippets": "mine"},
    ),
}

_OWN = {"id": "my-own", "alias": "Mine", "platform_specific_commands": {"default": "x"}}
REGISTRIES: dict[str, tuple[Path, str, object]] = {
    "shell-own-beside-stale": (
        SHELL,
        "shell_commands",
        {"settings_version": "0.23.0", "shell_commands": [_OWN, {"id": "agent-b", "alias": "old"}]},
    ),
    "shell-plugin-fields-kept": (
        SHELL,
        "shell_commands",
        {
            "shell_commands": [
                {
                    "id": "wiki-lint",
                    "alias": "Wiki: lint (structural)",
                    "icon": "lucide-shield-check",
                    "debounce": None,
                    "execution_notification_mode": None,
                },
                {"id": "agent-a", "alias": "Wiki: agent a", "icon": "lucide-bot", "debounce": None},
            ]
        },
    ),
    "shell-legacy-object-form": (
        SHELL,
        "shell_commands",
        {"shell_commands": {"wiki-compile": {"alias": "old"}, "my-own": {"alias": "Mine"}}},
    ),
    "shell-entry-without-id": (
        SHELL,
        "shell_commands",
        {"shell_commands": [{"alias": "no id"}, _OWN]},
    ),
    "shell-entry-not-an-object": (SHELL, "shell_commands", {"shell_commands": ["x", _OWN]}),
    "shell-key-holds-text": (SHELL, "shell_commands", {"shell_commands": "x", "other": 1}),
    "shell-not-json": (SHELL, "shell_commands", '{"shell_commands": [\n'),
    "buttons-own-and-changed-engine": (
        META_BIND,
        "buttonTemplates",
        {
            "devMode": True,
            "buttonTemplates": [
                {"id": "btn-note", "label": "an operator's label", "hidden": True},
                {"id": "btn-mine", "label": "Mine", "actions": []},
            ],
        },
    ),
}

# name → the vault's .env.example (a function of the template's text)
ENVS: dict[str, object] = {
    "env-current": lambda t: t,
    "env-one-missing": lambda t: (
        "\n".join(line for line in t.splitlines() if line != "EXA_API_KEY=") + "\n"
    ),
    "env-commented-counts": lambda t: t.replace("EXA_API_KEY=", "# EXA_API_KEY=old"),
    "env-only-two-vars": lambda t: "OPENAI_API_KEY=sk\nNAS_HOST=x",
}


def _vault_file(tmp_path: Path, template: Path, before: object) -> Path:
    path = tmp_path / "vault.json"
    if before == "template":
        path.write_bytes(template.read_bytes())
    elif isinstance(before, str):
        path.write_text(before, encoding="utf-8")
    else:
        path.write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
    return path


def _bash(*args: object) -> str:
    run = subprocess.run(
        ["bash", "-c", _DRIVER, "driver", str(REPO_ROOT / "lib" / "seed.sh"), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    return run.stdout


def _record(report: str, path: Path, before: bytes) -> str:
    after = path.read_bytes()
    file = "(unchanged)\n" if after == before else after.decode("utf-8")
    return report + "--- file ---\n" + file


def _golden(name: str) -> str:
    path = GOLDEN / name
    assert path.exists(), f"{name} not recorded — run tests/test_seed_merges.py --snapshot-update"
    return path.read_text(encoding="utf-8")


def _trouble(exc: Exception) -> str:
    return "trouble: json\n" if isinstance(exc, json.JSONDecodeError) else "trouble: shape\n"


# ── the bash, recorded (deleted with lib/seed.sh in T05) ──────────────────────


@pytest.mark.parametrize("name", sorted(LISTS))
def test_bash_list_union_is_recorded(request, tmp_path: Path, name: str) -> None:
    template, key, before = LISTS[name]
    path = _vault_file(tmp_path, template, before)
    original = path.read_bytes()
    report = _bash("list", template, path, key)
    assert_matches_golden(request, f"merge-{name}.txt", _record(report, path, original), GOLDEN)


@pytest.mark.parametrize("name", sorted(REGISTRIES))
def test_bash_registry_merge_is_recorded(request, tmp_path: Path, name: str) -> None:
    template, key, before = REGISTRIES[name]
    path = _vault_file(tmp_path, template, before)
    generated = tmp_path / "generated.json"
    generated.write_text(json.dumps(GENERATED), encoding="utf-8")
    original = path.read_bytes()
    report = _bash("registry", template, path, key, generated)
    assert_matches_golden(request, f"merge-{name}.txt", _record(report, path, original), GOLDEN)


@pytest.mark.parametrize("name", sorted(ENVS))
def test_bash_env_append_is_recorded(request, tmp_path: Path, name: str) -> None:
    path = tmp_path / ".env.example"
    path.write_text(ENVS[name](ENV.read_text(encoding="utf-8")), encoding="utf-8")
    original = path.read_bytes()
    report = _bash("env", ENV, path)
    assert_matches_golden(request, f"merge-{name}.txt", _record(report, path, original), GOLDEN)


# ── Python, held to the record ─────────────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(LISTS))
def test_python_list_union_matches_the_bash(tmp_path: Path, name: str) -> None:
    template, key, before = LISTS[name]
    text = _vault_file(tmp_path, template, before).read_text(encoding="utf-8")
    try:
        merged, adding = seed.union_list(jqjson.loads(text), jqjson.load(template), key)
    except (json.JSONDecodeError, seed.ShapeError) as exc:
        expected = _trouble(exc) + "--- file ---\n(unchanged)\n"
    else:
        report = "reported: " + ", ".join(map(str, adding)) + "\n"
        file = "(unchanged)\n" if merged is None else jqjson.render(merged)
        expected = report + "--- file ---\n" + file
    assert expected == _golden(f"merge-{name}.txt")


@pytest.mark.parametrize("name", sorted(REGISTRIES))
def test_python_registry_merge_matches_the_bash(tmp_path: Path, name: str) -> None:
    template, key, before = REGISTRIES[name]
    text = _vault_file(tmp_path, template, before).read_text(encoding="utf-8")
    engine = seed.engine_entries(jqjson.load(template), key, jqjson.loads(json.dumps(GENERATED)))
    try:
        config = jqjson.loads(text)
        merged, added, updated = seed.merge_registry(config, key, engine)
    except (json.JSONDecodeError, seed.ShapeError) as exc:
        expected = _trouble(exc) + "--- file ---\n(unchanged)\n"
    else:
        report = f"added: {', '.join(added)}\nupdated: {', '.join(updated)}\n"
        same = jqjson.canonical(merged) == jqjson.canonical(config)
        expected = report + "--- file ---\n" + ("(unchanged)\n" if same else jqjson.render(merged))
    assert expected == _golden(f"merge-{name}.txt")


@pytest.mark.parametrize("name", sorted(ENVS))
def test_python_env_append_matches_the_bash(name: str) -> None:
    template = ENV.read_text(encoding="utf-8")
    current = ENVS[name](template)
    missing = seed.env_missing(template, current)
    file = seed.env_appended(template, current, missing) if missing else "(unchanged)\n"
    assert "--- file ---\n" + file == _golden(f"merge-{name}.txt")


# ── jq's set operations ───────────────────────────────────────────────────────


def test_unique_sorts_the_way_jq_does() -> None:
    values = jqjson.loads(
        '["b", 1, null, true, false, "a", [1], {"x":1}, 1.0, "B", [0, 5], {"a":2}]'
    )
    expected = '[null,false,true,1,"B","a","b",[0,5],[1],{"a":2},{"x":1}]'
    assert json.dumps(json.loads(jqjson.render(jqjson.unique(values))), separators=(",", ":")) == (
        expected
    )


def test_subtract_is_jqs_minus() -> None:
    engine = jqjson.loads('["dataview", "quickadd", "homepage", 1]')
    current = jqjson.loads('["quickadd", "x", 1.0, "dataview"]')
    assert jqjson.subtract(engine, current) == ["homepage"]


def test_the_registries_get_the_templates_entries_then_the_agent_buttons() -> None:
    for template, key, generated in (
        (SHELL, "shell_commands", agent_buttons.shell_commands_entries()),
        (META_BIND, "buttonTemplates", agent_buttons.meta_bind_templates()),
    ):
        config = jqjson.load(template)
        engine = seed.engine_entries(config, key, agent_buttons.registry_entries(key))
        ids = [entry["id"] for entry in engine]
        assert ids == [e["id"] for e in config[key]] + [e["id"] for e in generated]
