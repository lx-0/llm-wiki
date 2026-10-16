"""The seed core (M034-S04-T02): `core.seed` and `core.jqjson`, held to the bash they replaced.

Each case's input went through the `lib/seed.sh` function Python replaces, composed the way
the seed composed it: `_apply_overlay` as `printf '%s\\n' "$(…)"` (what landed in the vault),
`_compute_overlay` with `--extract-custom`'s override count, `_json_canon`. The output was
recorded under tests/golden/seed/ before the bash was deleted (M034-S04-T05), and Python
must produce it byte for byte. An intended change re-records the golden from Python and says
why in its commit.

jq 1.7 keeps a number's literal (`1.50`, `1E+3`, `-0`), so `jqjson` reads numbers as
`Decimal` — the same General Decimal Arithmetic spec — and writes them back as read.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from core import jqjson, seed

from ._oracle import REPO_ROOT

GOLDEN = Path(__file__).resolve().parent / "golden" / "seed"
TEMPLATES = REPO_ROOT / "templates"
GRAPH = TEMPLATES / ".obsidian" / "graph.json"
QUICKADD = TEMPLATES / ".obsidian" / "plugins" / "quickadd" / "data.json"

# name → (base, overlay); a base that is a Path is a real template, overlay None = no file
APPLY: dict[str, tuple[object, object]] = {
    "graph-scale": (GRAPH, {"scale": 1.5}),
    "graph-no-overlay": (GRAPH, None),
    "quickadd-one-choice": (QUICKADD, {"choices": [{"name": "Neue Notiz (mine)"}]}),
    "nested-override-and-new-key": (
        {"a": {"b": 1, "c": 2}, "d": [1, 2]},
        {"a": {"c": 3, "e": 4}, "f": True},
    ),
    "sparse-array": (
        {"choices": [{"id": "x", "format": "a"}, {"id": "y", "format": "b"}]},
        {"choices": [None, {"format": "c"}]},
    ),
    "overlay-array-longer": ({"l": [1]}, {"l": [None, 2, 3]}),
    "overlay-null-keeps-base": ({"a": 1, "b": {"c": 2}}, {"a": None, "b": None}),
    "scalar-replaced-by-object": ({"search": "x"}, {"search": {"query": "q"}}),
    "object-replaced-by-scalar": ({"a": {"b": 1}}, {"a": 5}),
    "non-ascii": ({"label": "📝 Notiz", "tooltip": "für"}, {"tooltip": "über — neu"}),
    "number-literals": ('{"a": 1.50, "b": 1e3, "c": -0, "d": 1.0}\n', {"e": 2}),
}

# name → (base, current)
COMPUTE: dict[str, tuple[object, object]] = {
    "changed-scalar": ({"a": 1, "b": "x"}, {"a": 2, "b": "x"}),
    "added-key": ({"a": 1}, {"a": 1, "z": [1, {"k": "v"}]}),
    "nested-change": ({"a": {"b": {"c": 1, "d": 2}}}, {"a": {"b": {"c": 1, "d": 3}}}),
    "array-element": ({"l": [1, 2, 3]}, {"l": [1, 5, 3, 4]}),
    "removed-and-emptied": ({"a": 1, "b": {"c": 2}, "l": [1]}, {"b": {}, "l": []}),
    "bool-vs-number": ({"a": True, "b": 0}, {"a": 1, "b": False}),
    "int-vs-float": ({"a": 1, "b": 2.5}, {"a": 1.0, "b": 2.5}),
    "type-changed": ({"search": "x", "n": 1}, {"search": {"query": "q", "flags": [1]}, "n": 1}),
    "null-leaf": ({"a": 1}, {"a": None, "b": None}),
    "unchanged": (GRAPH, GRAPH),
    "graph-edited": (GRAPH, "graph-edited"),
}

# name → JSON text
CANON: dict[str, str] = {
    "reordered": '{"b": 1, "a": {"d": [3, {"z": 1, "y": 2}], "c": null}}',
    "keys-by-codepoint": '{"b": 1, "a": 2, "ä": 3, "Z": 4, "aa": 5, "a b": 6}',
    "strings": '{"ctl": "a\\u001bb\\u007fc\\td", "q": "\\"x\\\\", "u": "\\u2028 🌙 /"}',
    "numbers": '{"i": 30, "f": 0.1, "big": 12345678901234567890, "e": 1e-7, "t": 1.50}',
    "empties": '{"o": {}, "l": [], "n": [[], {}]}',
}


def _write(path: Path, value: object) -> Path:
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value == "graph-edited":
        data = json.loads(GRAPH.read_text(encoding="utf-8"))
        data["scale"] = 2
        data["colorGroups"][0]["color"]["rgb"] = 123
        value = data
    text = value if isinstance(value, str) else json.dumps(value, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def _inputs(tmp_path: Path, first: object, second: object) -> tuple[Path, Path]:
    one = _write(tmp_path / "one.json", first)
    two = tmp_path / "two.json" if second is None else _write(tmp_path / "two.json", second)
    return one, two


def _golden(name: str) -> str:
    path = GOLDEN / name
    assert path.exists(), f"{name}: the bash's record is missing (tests/golden/seed/)"
    return path.read_text(encoding="utf-8")


# ── Python, held to the bash's record ─────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(APPLY))
def test_python_derives_what_the_bash_wrote(tmp_path: Path, name: str) -> None:
    base, overlay = _inputs(tmp_path, *APPLY[name])
    assert seed.derive(base, overlay) == _golden(f"apply-{name}.json")


@pytest.mark.parametrize("name", sorted(COMPUTE))
def test_python_computes_the_overlay_the_bash_extracted(tmp_path: Path, name: str) -> None:
    base, current = _inputs(tmp_path, *COMPUTE[name])
    delta = seed.compute_overlay(jqjson.load(base), jqjson.load(current))
    text = jqjson.render(delta) + f"overrides: {seed.overrides(delta)}\n"
    assert text == _golden(f"compute-{name}.txt")


@pytest.mark.parametrize("name", sorted(CANON))
def test_python_canonical_form_is_the_bashs(name: str) -> None:
    assert jqjson.canonical(jqjson.loads(CANON[name])) == _golden(f"canon-{name}.json")


def test_extracting_then_deriving_gives_the_live_file_back(tmp_path: Path) -> None:
    """The overlay's promise: template ⊕ (live − template) == live, for what it expresses."""
    template = jqjson.load(GRAPH)
    live = json.loads(GRAPH.read_text(encoding="utf-8"))
    live["colorGroups"][1]["query"] = "tag:#mine"
    live["search"] = {"query": "q"}
    live["mine"] = [1, 2]
    live = jqjson.loads(json.dumps(live))
    overlay = seed.compute_overlay(template, live)
    assert jqjson.same(seed.apply_overlay(template, overlay), live)


# ── jq's comparisons ──────────────────────────────────────────────────────────


def test_same_is_jqs_equality() -> None:
    num = jqjson.loads
    assert jqjson.same(num("1"), num("1.0"))
    assert not jqjson.same(True, num("1"))
    assert not jqjson.same(num("0"), False)
    assert jqjson.same(None, None)
    assert not jqjson.same({"a": True}, {"a": num("1")})


def test_setpath_refuses_what_jq_refuses() -> None:
    """jq: `{} | setpath([0]; 1)` "Cannot index object with number", and so on — the bash's
    --extract-custom says "could not compute the drift" on it
    (tests/golden/bash/seed-extract-custom-config-now-a-list.txt)."""
    assert jqjson.setpath(None, (2,), 1) == [None, None, 1]
    for value, path in (({}, (0,)), ([], ("a",)), ("s", ("a",)), (1, (0,))):
        with pytest.raises(TypeError):
            jqjson.setpath(value, path, 1)
    with pytest.raises(TypeError):
        seed.compute_overlay(jqjson.load(GRAPH), jqjson.loads('[{"scale": 2}]'))


def test_numbers_keep_their_literal() -> None:
    value = jqjson.loads('{"a": 1.50, "b": 1e3, "c": -0, "d": 12345678901234567890}')
    assert value["a"] == Decimal("1.50")
    assert jqjson.render(value).split() == [
        "{",
        '"a":',
        "1.50,",
        '"b":',
        "1E+3,",
        '"c":',
        "-0,",
        '"d":',
        "12345678901234567890",
        "}",
    ]


# ── the walk ──────────────────────────────────────────────────────────────────


def test_the_walk_is_the_bash_seeds_order() -> None:
    """`seed-check-unseeded` lists every seedable file the way the bash walks them."""
    golden = (REPO_ROOT / "tests" / "golden" / "bash" / "seed-check-unseeded.txt").read_text(
        encoding="utf-8"
    )
    labels = re.findall(r"^! missing (.+) \(run `wiki seed` to install\)$", golden, re.M)
    assert labels
    assert [entry.label for entry in seed.walk(TEMPLATES)] == labels


def test_each_file_goes_where_the_bash_sent_it() -> None:
    kinds = {entry.label: entry.kind for entry in seed.walk(TEMPLATES)}
    obsidian = ".obsidian/plugins/"
    assert kinds[".obsidian/community-plugins.json"] == "plugin-list"
    assert kinds[".obsidian/appearance.json"] == "snippet-list"
    assert kinds[f"{obsidian}obsidian-meta-bind-plugin/data.json"] == "button-templates"
    assert kinds[f"{obsidian}obsidian-shellcommands/data.json"] == "shell-commands"
    assert kinds[".claude/.env.example"] == "env"
    overlays = {label for label, kind in kinds.items() if kind == "overlay"}
    assert overlays == {
        ".obsidian/app.json",
        ".obsidian/core-plugins.json",
        ".obsidian/graph.json",
        f"{obsidian}dataview/data.json",
        f"{obsidian}extended-graph/data.json",
        f"{obsidian}homepage/data.json",
        f"{obsidian}quickadd/data.json",
    }
    assert {kind for label, kind in kinds.items() if not label.endswith(".json")} <= {
        "copy",
        "env",
    }


def test_the_walk_skips_a_template_that_is_not_there(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    (tmp_path / "_dashboard-stats.md").write_text("a cache, never seeded", encoding="utf-8")
    assert [(entry.label, entry.kind) for entry in seed.walk(tmp_path)] == [("README.md", "copy")]
