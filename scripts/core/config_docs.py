"""Config docs generator — schema-derived tables for docs/config.md +
config.example.yaml sync-check.

Third consumer of the `core.config_schema` seam (after `core.config`'s load()
and the migration's KEY_ADDITIONS derivation): the key/default/meaning tables
in `docs/config.md` are GENERATED from the dataclasses, so a default can never
rot in the docs again — the field comments in `config_schema.py` are the
single documentation source, and `tests/test_config_docs.py` diffs the
committed docs against a fresh generation (regenerate with
`uv run python scripts/core/config_docs.py --write`).

Side-effect-free like the schema itself: importing this module reads no vault
and touches no environment. The docs/example paths are parameters.

What is generated vs. hand-authored in docs/config.md:
- GENERATED (between the marker comments): every per-section key table.
- HAND-AUTHORED (outside the markers): intro, file-layout tables, the
  `personal.accounts` schema + reader-kind prose, the secrets table, and the
  editing-safety notes. Those are genuinely prose — only the key/default
  tables were the rot surface.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import MISSING, fields, is_dataclass
from pathlib import Path

# Standalone-script bootstrap (mirrors core/config.py): the generator is also
# invoked directly (`uv run python scripts/core/config_docs.py --write`), so
# `scripts/` must be on sys.path for the core.* import below.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config_schema import (  # noqa: E402
    Features,
    GraphView,
    Limits,
    Models,
    Personal,
    Publish,
    Scheduling,
    Skills,
    _default_piggybacks,
)

BEGIN_MARK = (
    "<!-- BEGIN GENERATED TABLES — scripts/core/config_docs.py. Do not edit by hand: "
    "edit the field comments in scripts/core/config_schema.py, then run "
    "`uv run python scripts/core/config_docs.py --write`. -->"
)
END_MARK = "<!-- END GENERATED TABLES -->"

_SECTIONS: tuple[tuple[str, type], ...] = (
    ("scheduling", Scheduling),
    ("models", Models),
    ("features", Features),
    ("limits", Limits),
    ("graph_view", GraphView),
    ("skills", Skills),
    ("personal", Personal),
    ("publish", Publish),
)

# Piggyback names that legitimately appear in config.example.yaml without a
# _default_piggybacks entry: operator-only knobs a consumer reads when the
# block is present. (scan_youtube self-caps via CONFIG.piggybacks.)
EXAMPLE_EXTRA_PIGGYBACKS: frozenset[str] = frozenset({"scan_youtube"})

# Schema keys deliberately NOT present in config.example.yaml.
#   personal.accounts — shown as a commented template instead: an explicit
#   bare `accounts:` line would parse to null and trip the load() type gate.
EXAMPLE_OMITTED_KEYS: frozenset[str] = frozenset({"personal.accounts"})


# ── Field-comment extraction ────────────────────────────────────────────

_FIELD_RE = re.compile(r"^    (\w+):\s*[^=]+(?:=.*)?$")


def _field_comments(cls: type) -> dict[str, str]:
    """Map field name → the `#` comment block documenting it in the source.

    A field's documentation is the run of full-line comments directly above it
    plus any trailing comment on the field line (and deeper-indented trailing
    comment lines directly after it). Blank lines and other statements reset
    the pending block.
    """
    import inspect

    src = inspect.getsource(cls)
    comments: dict[str, str] = {}
    pending: list[str] = []
    last_field: str | None = None
    for line in src.splitlines():
        stripped = line.strip()
        m = _FIELD_RE.match(line)
        if m and not stripped.startswith("#"):
            name = m.group(1)
            trailing = line.split("#", 1)[1].strip() if "#" in line else ""
            text = " ".join(pending)
            if trailing:
                text = f"{text} {trailing}".strip()
            comments[name] = text
            pending = []
            last_field = name
        elif stripped.startswith("#"):
            body = stripped.lstrip("#").strip()
            indent = len(line) - len(line.lstrip())
            if indent > 4 and last_field and not pending:
                # Deeper-indented trailing continuation of the previous field.
                comments[last_field] = f"{comments.get(last_field, '')} {body}".strip()
            else:
                pending.append(body)
        elif not stripped:
            pending = []
            last_field = None
        else:
            pending = []
            last_field = None
    return comments


_ABBREV_TAILS = ("e.g", "i.e", "vs", "etc", "cf", "incl")


def _sentences(text: str) -> list[str]:
    """Sentence spans of a comment block, tolerant of common abbreviations."""
    text = " ".join(text.split())
    out: list[str] = []
    start = 0
    for m in re.finditer(r"\.(?=\s)", text):
        tail = text[: m.start()].rsplit(" ", 1)[-1].lstrip("(").rstrip(".")
        # Abbreviations and enumeration markers ("1.", "2.") don't end sentences.
        if tail in _ABBREV_TAILS or tail.isdigit():
            continue
        out.append(text[start : m.end()].strip())
        start = m.end()
    rest = text[start:].strip()
    if rest:
        out.append(rest)
    return out


def _meaning(comment: str, *, max_len: int = 240) -> str:
    if not comment:
        return "—"
    parts = _sentences(comment)
    # A very short first sentence is usually just an arc label ("M014
    # dream-cycle.") — pull the next sentence in for actual meaning.
    summary = parts[0]
    if len(summary) < 45 and len(parts) > 1:
        summary = f"{summary} {parts[1]}"
    if len(summary) > max_len:
        summary = summary[:max_len].rsplit(" ", 1)[0].rstrip(",;:") + " …"
    return summary.replace("|", "\\|")


# ── Default rendering ───────────────────────────────────────────────────


def _plain(value: object) -> object:
    if isinstance(value, tuple):
        return [_plain(v) for v in value]
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def _default_for(cls: type, name: str) -> object:
    for f in fields(cls):
        if f.name != name:
            continue
        if f.default is not MISSING:
            return f.default
        if f.default_factory is not MISSING:  # type: ignore[misc]
            return f.default_factory()  # type: ignore[misc]
    raise KeyError(name)


def _fmt(value: object) -> str:
    """YAML-flavored literal for the Default column (json is a YAML subset)."""
    value = _plain(value)
    if is_dataclass(value) and not isinstance(value, type):
        return "*(nested — see below)*"
    return f"`{json.dumps(value, ensure_ascii=False)}`"


# ── Table generation ────────────────────────────────────────────────────


def _section_table(section: str, cls: type) -> str:
    comments = _field_comments(cls)
    lines = [f"## {section}", "", "| Key | Default | Meaning |", "|---|---|---|"]
    for f in fields(cls):
        default = _default_for(cls, f.name)
        if is_dataclass(default) and not isinstance(default, type):
            # Nested dataclass (scheduling.dream_priority): one row per leaf.
            nested_comments = _field_comments(type(default))
            lines.append(
                f"| `{section}.{f.name}.*` | *(nested)* | {_meaning(comments.get(f.name, ''))} |"
            )
            for nf in fields(type(default)):
                lines.append(
                    f"| `{section}.{f.name}.{nf.name}` | {_fmt(_default_for(type(default), nf.name))} "
                    f"| {_meaning(nested_comments.get(nf.name, ''))} |"
                )
        else:
            lines.append(
                f"| `{section}.{f.name}` | {_fmt(default)} | {_meaning(comments.get(f.name, ''))} |"
            )
    lines.append("")
    return "\n".join(lines)


def _piggybacks_table() -> str:
    lines = [
        "## piggybacks",
        "",
        "Recurring maintenance/collector tasks drained after `scheduling.compile_after_hour`",
        "(flush path) or at the end of every real `wiki compile`",
        "(`scheduling.piggybacks_on_compile`). Each entry takes `enabled` (bool),",
        "`cooldown_hours` (int), and optionally `max_per_run` (int). Defaults live in",
        "`core/config_schema.py:_default_piggybacks` — for Registry collectors the name",
        "is `CollectorSpec.name` and the cooldown is parity-tested against the SPEC.",
        "`max_per_run` appears only where a consumer reads it (built-in command",
        "templates + the self-capping screenshots/pictures collectors); the",
        "jamie/gmeet/calendar caps live in `limits.*_max_per_run` + the per-account",
        "sub-blocks instead.",
        "",
        "| Task | enabled | cooldown_hours | max_per_run |",
        "|---|---|---|---|",
    ]
    for name, task in _default_piggybacks().items():
        cap = str(task.max_per_run) if task.max_per_run is not None else "—"
        lines.append(
            f"| `piggybacks.{name}` | `{json.dumps(task.enabled)}` | {task.cooldown_hours} | {cap} |"
        )
    lines.append("")
    return "\n".join(lines)


def generate_tables() -> str:
    """The full generated region (marker to marker, inclusive)."""
    parts = [BEGIN_MARK, ""]
    for section, cls in _SECTIONS:
        parts.append(_section_table(section, cls))
        if section == "limits":
            parts.append(_piggybacks_table())
    parts.append(END_MARK)
    return "\n".join(parts)


def render_docs(existing_text: str) -> str:
    """Replace the generated region inside the committed docs text."""
    begin = existing_text.index(BEGIN_MARK)
    end = existing_text.index(END_MARK) + len(END_MARK)
    return existing_text[:begin] + generate_tables() + existing_text[end:]


# ── config.example.yaml sync-check ──────────────────────────────────────


def check_example(example_path: Path) -> list[str]:
    """Mismatches between config.example.yaml and the schema defaults.

    Returns human-readable problem strings; empty list = in sync. Checked:
    every schema leaf key is present with exactly the engine default (the
    example documents defaults — deviating values would silently change
    behavior on fresh installs, the curiosity_followup 24h-vs-6h incident);
    unknown keys are flagged; piggyback blocks must match _default_piggybacks
    (plus the EXAMPLE_EXTRA_PIGGYBACKS operator-only knobs).
    """
    import yaml

    problems: list[str] = []
    data = yaml.safe_load(example_path.read_text(encoding="utf-8")) or {}

    for section, cls in _SECTIONS:
        block = data.get(section)
        if not isinstance(block, dict):
            problems.append(f"missing section `{section}:`")
            continue
        schema_names = {f.name for f in fields(cls)}
        for f in fields(cls):
            dotted = f"{section}.{f.name}"
            if dotted in EXAMPLE_OMITTED_KEYS:
                continue
            if f.name not in block:
                problems.append(f"missing key `{dotted}`")
                continue
            expected = _plain(_default_for(cls, f.name))
            if is_dataclass(expected) and not isinstance(expected, type):
                from dataclasses import asdict

                expected = _plain(asdict(expected))
            if block[f.name] != expected:
                problems.append(
                    f"`{dotted}` = {block[f.name]!r} but the schema default is {expected!r}"
                )
        for key in block:
            if key not in schema_names:
                problems.append(f"unknown key `{section}.{key}` (not on the schema)")

    pb = data.get("piggybacks")
    if not isinstance(pb, dict):
        problems.append("missing section `piggybacks:`")
        return problems
    defaults = _default_piggybacks()
    for name, task in defaults.items():
        if name not in pb:
            problems.append(f"missing piggyback block `piggybacks.{name}`")
            continue
        expected_block: dict[str, object] = {
            "enabled": task.enabled,
            "cooldown_hours": task.cooldown_hours,
        }
        if task.max_per_run is not None:
            expected_block["max_per_run"] = task.max_per_run
        if pb[name] != expected_block:
            problems.append(
                f"`piggybacks.{name}` = {pb[name]!r} but the schema default is {expected_block!r}"
            )
    for name in pb:
        if name not in defaults and name not in EXAMPLE_EXTRA_PIGGYBACKS:
            problems.append(f"unknown piggyback `piggybacks.{name}` (no default, not a known extra)")
    return problems


# ── CLI ─────────────────────────────────────────────────────────────────


def _cli() -> int:
    import argparse

    repo_root = Path(__file__).resolve().parent.parent.parent
    parser = argparse.ArgumentParser(description="Regenerate / check the config reference docs")
    parser.add_argument("--docs", type=Path, default=repo_root / "docs" / "config.md")
    parser.add_argument("--example", type=Path, default=repo_root / "config.example.yaml")
    parser.add_argument("--write", action="store_true", help="Rewrite the generated docs region")
    parser.add_argument("--check", action="store_true", help="Exit 1 on docs/example drift")
    args = parser.parse_args()

    existing = args.docs.read_text(encoding="utf-8")
    rendered = render_docs(existing)
    example_problems = check_example(args.example)

    if args.write:
        if rendered != existing:
            args.docs.write_text(rendered, encoding="utf-8")
            print(f"rewrote generated region in {args.docs}")
        else:
            print("docs already current")
        for p in example_problems:
            print(f"config.example.yaml: {p}", file=sys.stderr)
        return 1 if example_problems else 0

    drift = rendered != existing
    if drift:
        print(
            f"{args.docs} is stale — run `uv run python scripts/core/config_docs.py --write`",
            file=sys.stderr,
        )
    for p in example_problems:
        print(f"config.example.yaml: {p}", file=sys.stderr)
    if not drift and not example_problems:
        print("docs + example in sync with the schema")
    return 1 if (drift or example_problems) else 0


if __name__ == "__main__":
    raise SystemExit(_cli())
