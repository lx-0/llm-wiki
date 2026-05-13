"""Tests for the agent-task framework (M004-S01).

Covers:
- agent_spec.parse_spec — happy + sad paths
- agent_spec.list_specs — discovery + ordering
- agent_task.cmd_list — empty + populated + invalid spec mix
- agent_task._update_last_run — writes back without clobbering body
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from core.agent_spec import (
    AgentSpec,
    ButtonSpec,
    SpecError,
    list_specs,
    parse_spec,
)


# ── helpers ───────────────────────────────────────────────────────────


def _write_spec(dirpath: Path, slug: str, frontmatter: str, body: str = "Body") -> Path:
    path = dirpath / f"agent_{slug}.md"
    path.write_text(f"---\n{frontmatter.strip()}\n---\n\n{body}\n", encoding="utf-8")
    return path


# ── parse_spec — happy path ──────────────────────────────────────────


def test_parse_spec_minimal_valid(tmp_path: Path) -> None:
    path = _write_spec(
        tmp_path, "demo",
        textwrap.dedent("""\
            id: demo
            title: "Demo task"
            allowed_tools: [Read, Edit]
            """),
    )
    spec = parse_spec(path)
    assert spec.id == "demo"
    assert spec.title == "Demo task"
    assert spec.allowed_tools == ["Read", "Edit"]
    assert spec.permission_mode == "acceptEdits"  # default
    assert spec.max_turns == 10  # default
    assert spec.cwd == "vault"  # default
    assert spec.button is None
    assert spec.last_run is False
    assert spec.body.strip() == "Body"


def test_parse_spec_full(tmp_path: Path) -> None:
    path = _write_spec(
        tmp_path, "full",
        textwrap.dedent("""\
            id: full
            title: "Full spec"
            description: "Tests every field"
            model: claude-haiku-4-5
            allowed_tools: [Read, Write, Glob]
            permission_mode: bypassPermissions
            max_turns: 5
            cwd: wiki
            button:
              label: "▶ Run full"
              style: primary
              tooltip: "Tooltip"
              shell_command_id: agent-full-custom
            """),
        body="Hello ${name}",
    )
    spec = parse_spec(path)
    assert spec.model == "claude-haiku-4-5"
    assert spec.permission_mode == "bypassPermissions"
    assert spec.max_turns == 5
    assert spec.cwd == "wiki"
    assert spec.button is not None
    assert spec.button.label == "▶ Run full"
    assert spec.button.style == "primary"
    assert spec.button.shell_command_id == "agent-full-custom"
    assert spec.render_body(name="World") == "Hello World"


def test_button_default_shell_command_id(tmp_path: Path) -> None:
    """When the button doesn't declare shell_command_id, it defaults to agent-<id>."""
    path = _write_spec(
        tmp_path, "auto",
        textwrap.dedent("""\
            id: auto
            title: "Auto"
            allowed_tools: [Read]
            button:
              label: "Auto"
            """),
    )
    spec = parse_spec(path)
    assert spec.button is not None
    assert spec.button.shell_command_id == "agent-auto"


# ── parse_spec — sad path ────────────────────────────────────────────


def test_parse_spec_no_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "agent_bad.md"
    path.write_text("just body, no fences\n")
    with pytest.raises(SpecError, match="frontmatter"):
        parse_spec(path)


def test_parse_spec_missing_required_id(tmp_path: Path) -> None:
    path = _write_spec(
        tmp_path, "noid",
        textwrap.dedent("""\
            title: "Has title but no id"
            allowed_tools: [Read]
            """),
    )
    with pytest.raises(SpecError, match="missing `id`"):
        parse_spec(path)


def test_parse_spec_missing_allowed_tools(tmp_path: Path) -> None:
    path = _write_spec(
        tmp_path, "notools",
        textwrap.dedent("""\
            id: notools
            title: "No tools"
            """),
    )
    with pytest.raises(SpecError, match="allowed_tools"):
        parse_spec(path)


def test_parse_spec_unknown_tool(tmp_path: Path) -> None:
    path = _write_spec(
        tmp_path, "wrongtool",
        textwrap.dedent("""\
            id: wrongtool
            title: "Wrong tool"
            allowed_tools: [Read, Telepathy]
            """),
    )
    with pytest.raises(SpecError, match=r"unknown allowed_tools.*Telepathy"):
        parse_spec(path)


def test_parse_spec_invalid_permission_mode(tmp_path: Path) -> None:
    path = _write_spec(
        tmp_path, "perm",
        textwrap.dedent("""\
            id: perm
            title: "Bad permission"
            allowed_tools: [Read]
            permission_mode: yolo
            """),
    )
    with pytest.raises(SpecError, match="permission_mode"):
        parse_spec(path)


def test_parse_spec_invalid_button_style(tmp_path: Path) -> None:
    path = _write_spec(
        tmp_path, "btnstyle",
        textwrap.dedent("""\
            id: btnstyle
            title: "Bad style"
            allowed_tools: [Read]
            button:
              label: "X"
              style: rainbow
            """),
    )
    with pytest.raises(SpecError, match=r"button.style"):
        parse_spec(path)


def test_parse_spec_max_turns_out_of_range(tmp_path: Path) -> None:
    path = _write_spec(
        tmp_path, "turns",
        textwrap.dedent("""\
            id: turns
            title: "Turns"
            allowed_tools: [Read]
            max_turns: 0
            """),
    )
    with pytest.raises(SpecError, match="max_turns"):
        parse_spec(path)


def test_parse_spec_malformed_yaml(tmp_path: Path) -> None:
    path = tmp_path / "agent_yaml.md"
    path.write_text("---\nid: yaml\n  title: bad indent\nallowed_tools: [Read]\n---\nbody\n")
    with pytest.raises(SpecError, match="YAML"):
        parse_spec(path)


# ── list_specs ────────────────────────────────────────────────────────


def test_list_specs_empty_dir(tmp_path: Path) -> None:
    assert list_specs(tmp_path) == []


def test_list_specs_skips_non_agent_files(tmp_path: Path) -> None:
    _write_spec(
        tmp_path, "real",
        "id: real\ntitle: R\nallowed_tools: [Read]",
    )
    (tmp_path / "compile_main.md").write_text("not an agent")
    (tmp_path / "agent_real.md.bak").write_text("backup file")
    specs = list_specs(tmp_path)
    assert [s.id for s in specs] == ["real"]


def test_list_specs_sorted(tmp_path: Path) -> None:
    for slug in ["zebra", "alpha", "mango"]:
        _write_spec(
            tmp_path, slug,
            f"id: {slug}\ntitle: {slug}\nallowed_tools: [Read]",
        )
    specs = list_specs(tmp_path)
    assert [s.id for s in specs] == ["alpha", "mango", "zebra"]


# ── render_body ───────────────────────────────────────────────────────


def test_render_body_no_vars() -> None:
    spec = AgentSpec(
        id="x", title="x", body="static body", allowed_tools=["Read"],
    )
    assert spec.render_body() == "static body"


def test_render_body_substitutes() -> None:
    spec = AgentSpec(
        id="x", title="x",
        body="hello ${who} on ${day}", allowed_tools=["Read"],
    )
    assert spec.render_body(who="alex", day="2026-05-02") == "hello alex on 2026-05-02"


# ── _update_last_run integration ──────────────────────────────────────


def test_update_last_run_preserves_body(tmp_path: Path) -> None:
    """Writing last_run: <iso> back to frontmatter must not damage the prompt body."""
    from agent_task import _update_last_run

    path = _write_spec(
        tmp_path, "demo",
        textwrap.dedent("""\
            id: demo
            title: "Demo"
            allowed_tools: [Read]
            """),
        body="Multi-line\nprompt body\n\nwith blank lines.",
    )
    spec = parse_spec(path)
    _update_last_run(spec)

    text = path.read_text(encoding="utf-8")
    assert "last_run:" in text
    assert "Multi-line" in text
    assert "with blank lines." in text
    # Re-parse, frontmatter still valid:
    spec2 = parse_spec(path)
    assert isinstance(spec2.last_run, str)
    assert spec2.last_run.startswith("20")
