"""JSON the way jq 1.7 reads, compares and writes it — for the ports of the bash's jq work
(the agent configs, M034-S03; the seed, M034-S04), held to output the bash recorded.

- **Numbers keep their literal.** jq 1.7 holds a number as its decimal literal and writes it
  back as read (`1.50`, `1E+3`, `-0`). `loads` reads every number as `Decimal`, which follows
  the same General Decimal Arithmetic spec, and `render` writes `str(Decimal)`.
- **`same` is jq's `==`:** numbers by value (`1 == 1.0`), a boolean never equal to a number
  (Python's `True == 1` is).
- **`render` is `jq .`, `canonical` is `jq -S .`:** two-space indent, UTF-8 as is, DEL
  escaped as `\\u007f` (Python's encoder leaves it raw), keys sorted by code point for `-S`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

JsonPath = tuple[str | int, ...]  # a jq path: object keys and array indices


def loads(text: str) -> object:
    return json.loads(text, parse_float=Decimal, parse_int=Decimal)


def load(path: Path) -> object:
    return loads(path.read_text(encoding="utf-8"))


def render(value: object) -> str:
    """``value`` as `jq .` writes it, with a trailing newline."""
    return _dump(value, 0, sort=False) + "\n"


def canonical(value: object) -> str:
    """``value`` as `jq -S .` writes it — the seed's "same config" test compares these."""
    return _dump(value, 0, sort=True) + "\n"


def _string(text: str) -> str:
    return json.dumps(text, ensure_ascii=False).replace("\x7f", "\\u007f")


def _dump(value: object, level: int, *, sort: bool) -> str:
    inner = "  " * (level + 1)
    outer = "  " * level
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = sorted(value.items()) if sort else list(value.items())
        body = ",\n".join(
            f"{inner}{_string(key)}: {_dump(item, level + 1, sort=sort)}" for key, item in items
        )
        return "{\n" + body + "\n" + outer + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        body = ",\n".join(inner + _dump(item, level + 1, sort=sort) for item in value)
        return "[\n" + body + "\n" + outer + "]"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, Decimal | int):
        return str(value)
    if isinstance(value, float):
        return json.dumps(value)
    raise TypeError(f"not JSON: {type(value).__name__}")


def same(a: object, b: object) -> bool:
    """jq's `==`."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[key], b[key]) for key in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, dict | list) or isinstance(b, dict | list):
        return False
    return a == b


def leaf_paths(value: object, prefix: JsonPath = ()) -> Iterator[JsonPath]:
    """The paths to the text, number and boolean leaves, in document order — the bash's
    `leaf_paths`. jq's `paths(scalars)` would drop every false leaf (0.7.23); null leaves stay
    out on purpose."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaf_paths(item, (*prefix, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from leaf_paths(item, (*prefix, index))
    elif value is not None:
        yield prefix


def getpath(value: object, path: JsonPath) -> object:
    """jq's `try getpath($p) catch null`: None where ``value`` cannot follow ``path``."""
    for key in path:
        if isinstance(key, str) and isinstance(value, dict):
            value = value.get(key)
        elif isinstance(key, int) and isinstance(value, list):
            value = value[key] if key < len(value) else None
        else:
            return None
    return value


def setpath(value: object, path: JsonPath, new: object) -> object:
    """jq's `setpath`: a copy of ``value`` with ``new`` at ``path``, creating objects and
    arrays on the way — an array is padded with nulls up to the index."""
    if not path:
        return new
    key, rest = path[0], path[1:]
    if isinstance(key, str):
        obj = dict(value) if isinstance(value, dict) else {}
        obj[key] = setpath(obj.get(key), rest, new)
        return obj
    items = list(value) if isinstance(value, list) else []
    items.extend([None] * (key + 1 - len(items)))
    items[key] = setpath(items[key], rest, new)
    return items
