"""The schema-2 JSON contracts — `wiki menu --json` and `wiki doctor --json`, typed once.

Every payload a consumer (the desktop app, an agent) parses is a `TypedDict` here: the
builders in `core/actions.py`, `core/health/`, `menu_context.py` and `doctor.py` return
these types, and `python -m core.contracts --write` generates the JSON Schemas
(`docs/contracts/menu.schema.json`, `docs/contracts/doctor.schema.json`) from them, which
both test suites validate their payloads against. `additionalProperties` is `false`
everywhere, so a key the engine adds without the types fails validation instead of
drifting past a consumer — add it here, regenerate, and bump `core.actions.SCHEMA` when
the change is consumer-visible.

Regenerate:  PYTHONPATH=scripts uv run python -m core.contracts --write
Check:       PYTHONPATH=scripts uv run python -m core.contracts --check
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
import types
from pathlib import Path
from typing import (
    Any,
    Literal,
    TypedDict,
    Union,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
)

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "contracts"
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


# ── The payloads ────────────────────────────────────────────────────────


class ActionJSON(TypedDict):
    """One action as consumers receive it (`menu --json` suggestions and tools, the desktop's
    buttons): the rendered title, the verb, the intent group, the argv `wiki` runs."""

    id: str
    title: str
    verb: str
    group: str
    argv: list[str]


class SuggestionJSON(ActionJSON):
    """A pending action with its count: `label` is the TUI's operator-term line, `priority`
    the declared order, `key` the menu number ("1".."N") assigned after the sort."""

    count: int
    label: str
    priority: int
    key: str


class StatusJSON(TypedDict, total=False):
    """The home screen's one-liner. Every key is optional: each probe can fail on its own
    and drops its key (`menu_context.build_status`)."""

    # `total=False`, not `NotRequired[...]`: under `from __future__ import annotations`
    # Python 3.12's TypedDict reads a string `NotRequired[int]` as required (measured).
    articles: int
    last_compile_ago: str
    ollama_reachable: bool


class MenuJSON(TypedDict):
    """`wiki menu --json`."""

    schema: Literal[2]
    status: StatusJSON
    suggestions: list[SuggestionJSON]
    tools: list[ActionJSON]


class CheckJSON(TypedDict):
    """One check in the schema-2 JSON (`wiki doctor --json`, the desktop's Health rows):
    the `CheckResult` fields in their order, `title` always set, plus `verb`."""

    id: str
    category: str
    severity: str
    message: str
    fix: str | None
    dispatch_args: list[str] | None
    details: dict[str, Any] | None
    title: str
    verb: str | None


class HealthSummaryJSON(TypedDict):
    """Check counts per severity (`core.health.health_summary`)."""

    critical: int
    warning: int
    info: int
    ok: int


class DoctorJSON(TypedDict):
    """`wiki doctor --json` / `wiki doctor --quick --json`."""

    schema: Literal[2]
    vault: str
    engine_revision: str
    summary: HealthSummaryJSON
    checks: list[CheckJSON]


#: The documents `--write` generates, by file stem.
PAYLOADS: dict[str, type] = {"menu": MenuJSON, "doctor": DoctorJSON}


# ── TypedDict → JSON Schema (draft 2020-12) ─────────────────────────────


def _describe(cls: type) -> str:
    return " ".join((inspect.getdoc(cls) or "").split())


def _object_schema(cls: type, defs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    hints = get_type_hints(cls)
    required: frozenset[str] = getattr(cls, "__required_keys__", frozenset())
    out: dict[str, Any] = {"type": "object"}
    if description := _describe(cls):
        out["description"] = description
    out["properties"] = {name: _type_schema(tp, defs) for name, tp in hints.items()}
    if names := [name for name in hints if name in required]:
        out["required"] = names
    out["additionalProperties"] = False
    return out


def _type_schema(tp: Any, defs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    origin = get_origin(tp)
    if tp is Any:
        return {}
    if tp is type(None):
        return {"type": "null"}
    if tp is bool:  # before int: bool is an int subclass, but a JSON boolean
        return {"type": "boolean"}
    if tp is int:
        return {"type": "integer"}
    if tp is float:
        return {"type": "number"}
    if tp is str:
        return {"type": "string"}
    if origin is Literal:
        values = list(get_args(tp))
        return {"const": values[0]} if len(values) == 1 else {"enum": values}
    if origin is Union or origin is types.UnionType:
        return {"anyOf": [_type_schema(arg, defs) for arg in get_args(tp)]}
    if origin is list:
        (item,) = get_args(tp)
        return {"type": "array", "items": _type_schema(item, defs)}
    if origin is dict:
        return {"type": "object"}
    if is_typeddict(tp):
        if tp.__name__ not in defs:
            defs[tp.__name__] = {}  # placeholder first: a type that refers to itself terminates
            defs[tp.__name__] = _object_schema(tp, defs)
        return {"$ref": f"#/$defs/{tp.__name__}"}
    raise TypeError(f"no JSON Schema mapping for {tp!r} — extend core.contracts._type_schema")


def schema_for(cls: type) -> dict[str, Any]:
    """The JSON Schema document for one payload `TypedDict` (nested ones under `$defs`)."""
    defs: dict[str, dict[str, Any]] = {}
    body = _object_schema(cls, defs)
    doc: dict[str, Any] = {"$schema": SCHEMA_DIALECT, "title": cls.__name__, **body}
    if defs:
        doc["$defs"] = dict(sorted(defs.items()))
    return doc


def render(cls: type) -> str:
    return json.dumps(schema_for(cls), indent=2, ensure_ascii=False) + "\n"


def stale(directory: Path = CONTRACTS_DIR) -> list[str]:
    """File names under `directory` that differ from what `--write` would produce."""
    out: list[str] = []
    for stem, cls in PAYLOADS.items():
        path = directory / f"{stem}.schema.json"
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != render(cls):
            out.append(path.name)
    return out


def write(directory: Path = CONTRACTS_DIR) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for stem, cls in PAYLOADS.items():
        path = directory / f"{stem}.schema.json"
        path.write_text(render(cls), encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate / check the schema-2 JSON Schemas")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="rewrite docs/contracts/*.schema.json")
    mode.add_argument("--check", action="store_true", help="exit 1 when a schema file is stale")
    args = parser.parse_args(argv)
    if args.write:
        for path in write():
            print(f"wrote {path}")
        return 0
    if out_of_date := stale():
        print(
            "stale: "
            + ", ".join(out_of_date)
            + " — run `PYTHONPATH=scripts uv run python -m core.contracts --write`",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
