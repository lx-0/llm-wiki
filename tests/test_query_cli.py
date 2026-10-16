"""M033-S04-T06 — characterisation of `query.main` with a fake SDK stream and no vault:
the template + tool set per mode, the compile-role and domain notes, the flag conflicts,
the qa dedup guard, the prompt budget, the JSON payload and the state bump. Written before
the split; the SDK harness underneath is covered by test_sdk_run_harness.py."""

from __future__ import annotations

import asyncio
import json
import sys

import pytest
from claude_agent_sdk import ResultMessage

import query as query_cli
from core.config import CONFIG
from core.paths import ROOT_DIR
from core.usage import UsageLedger


@pytest.fixture
def env(tmp_path, monkeypatch):
    import core.usage as usage_mod

    monkeypatch.setattr(usage_mod, "LEDGER", UsageLedger())
    monkeypatch.setattr(query_cli, "read_wiki_index_compact", lambda: "INDEX-COMPACT")
    monkeypatch.setattr(query_cli, "read_hard_facts", lambda: "HARD-FACTS")
    monkeypatch.setattr(query_cli, "QA_DIR", tmp_path / "qa")
    monkeypatch.setattr(CONFIG.personal, "domains", ["company", "personal"])
    monkeypatch.setattr(CONFIG.limits, "query_max_prompt_chars", 200_000)
    bumps: list = []
    monkeypatch.setattr(query_cli, "update_state", bumps.append)
    rendered: dict = {}

    def _fake_render(name, **kw):
        rendered.update(kw, _template=name)
        return f"PROMPT[{name}] facts=<{kw['facts_md']}>"

    monkeypatch.setattr(query_cli, "render", _fake_render)
    seen: dict = {}

    async def _fake_query(*, prompt, options):
        seen.update(prompt=prompt, options=options)
        if seen.get("fail"):
            raise RuntimeError("sdk down")
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="s",
            total_cost_usd=0.001,
            usage={"input_tokens": 120, "output_tokens": 30},
            result="THE ANSWER",
        )

    monkeypatch.setattr(query_cli, "query", _fake_query)
    return tmp_path, rendered, seen, bumps


def _main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["query.py", *argv])
    asyncio.run(query_cli.main())


def _exit_code(monkeypatch, *argv) -> int:
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, *argv)
    return exc.value.code


# ── the three modes ──────────────────────────────────────────────────


def test_default_mode_renders_the_main_template_read_only(env, monkeypatch, capsys) -> None:
    _root, rendered, seen, bumps = env

    _main(monkeypatch, "What do I know about Hetzner?")

    assert rendered["_template"] == "query_main"
    assert rendered["index_md"] == "INDEX-COMPACT"
    assert rendered["question"] == "What do I know about Hetzner?"
    facts = rendered["facts_md"]
    assert facts.startswith("HARD-FACTS\n\n## compile_role filter\n\n")
    assert "SKIP it — it's archived hand-curated content" in facts
    assert "## domain filter" not in facts
    opts = seen["options"]
    assert list(opts.allowed_tools) == ["Read", "Glob", "Grep"]
    # Read-only for real (M034-S06-T07): the base toolset IS the three read tools, so
    # Write/Edit do not exist for this agent, and nothing auto-accepts an edit.
    assert list(opts.tools) == ["Read", "Glob", "Grep"]
    assert opts.max_turns == 15 and opts.permission_mode == "default"
    assert not opts.hooks
    assert opts.cwd == str(ROOT_DIR)
    assert opts.system_prompt == {"type": "preset", "preset": "claude_code"}
    assert seen["prompt"].startswith("PROMPT[query_main]")
    assert capsys.readouterr().out == "\nTHE ANSWER\n"
    [bump] = bumps
    state: dict = {"query_count": 2}
    bump(state)
    assert state["query_count"] == 3 and state["last_query"][:4] == "2026"


def test_brief_mode_renders_the_brief_template(env, monkeypatch, capsys) -> None:
    _root, rendered, seen, _bumps = env

    _main(monkeypatch, "Hetzner?", "--brief")

    assert rendered["_template"] == "query_brief"
    assert set(rendered) == {"_template", "index_md", "facts_md", "question"}
    assert list(seen["options"].allowed_tools) == ["Read", "Glob", "Grep"]
    assert list(seen["options"].tools) == ["Read", "Glob", "Grep"]
    assert seen["options"].permission_mode == "default"
    assert capsys.readouterr().out == "\nTHE ANSWER\n"


def test_file_back_mode_enables_writes_and_guards_the_qa_slug(env, monkeypatch, caplog) -> None:
    root, rendered, seen, _bumps = env

    _main(monkeypatch, "What do I know about Hetzner?", "--file-back")

    assert rendered["_template"] == "query_file_back"
    assert rendered["today"][:4] == "2026" and rendered["now"][:4] == "2026"
    opts = seen["options"]
    assert list(opts.allowed_tools) == ["Read", "Glob", "Grep", "Write", "Edit"]
    assert list(opts.tools) == ["Read", "Glob", "Grep", "Write", "Edit"]  # no Bash
    assert (root / "qa").is_dir()
    # AGENTS.md's three layers (M034-S06-T07): a PreToolUse path scope instead of
    # acceptEdits, and the vault's project settings so its CLAUDE.md reaches the agent.
    assert opts.permission_mode == "default"
    assert list(opts.setting_sources) == ["project"]
    [matcher] = opts.hooks["PreToolUse"]
    [hook] = matcher.hooks

    def decision(path) -> str:
        out = asyncio.run(
            hook({"tool_name": "Write", "tool_input": {"file_path": str(path)}}, "t", None)
        )
        return out["hookSpecificOutput"]["permissionDecision"]

    assert decision(root / "qa" / "new-answer.md") == "allow"
    assert decision(query_cli.KNOWLEDGE_DIR / "index.md") == "allow"
    assert decision(query_cli.LOG_FILE) == "allow"
    assert decision(query_cli.KNOWLEDGE_DIR / "concepts" / "x.md") == "deny"
    assert decision(ROOT_DIR / ".wiki" / "config.yaml") == "deny"

    (root / "qa" / "what-do-i-know-about-hetzner.md").write_text("# existing\n", encoding="utf-8")
    assert _exit_code(monkeypatch, "What do I know about Hetzner?", "--file-back") == 3
    assert (
        "qa/ already has 1 note(s) matching slug `what-do-i-know-about-hetzner*.md`" in caplog.text
    )

    seen.clear()
    _main(monkeypatch, "What do I know about Hetzner?", "--file-back", "--force")
    assert seen["prompt"].startswith("PROMPT[query_file_back]")


# ── notes + flags ────────────────────────────────────────────────────


def test_include_final_only_and_domain_notes(env, monkeypatch) -> None:
    _root, rendered, _seen, _bumps = env

    _main(monkeypatch, "Hetzner?", "--include-final-only", "--domain", "company")

    facts = rendered["facts_md"]
    assert "Include articles regardless of compile_role (operator requested" in facts
    assert "## domain filter" in facts and "value is exactly `company`" in facts


@pytest.mark.parametrize(
    "argv",
    [
        ("Hetzner?", "--brief", "--file-back"),
        ("Hetzner?", "--json", "--file-back"),
        ("Hetzner?", "--domain", "nope"),
    ],
)
def test_flag_conflicts_and_unknown_domains_exit_2(env, monkeypatch, caplog, argv) -> None:
    _root, rendered, _seen, _bumps = env

    assert _exit_code(monkeypatch, *argv) == 2
    assert rendered == {}
    assert "mutually exclusive" in caplog.text or "is not in CONFIG.personal.domains" in caplog.text


def test_any_domain_is_accepted_when_none_are_configured(env, monkeypatch) -> None:
    _root, rendered, _seen, _bumps = env
    monkeypatch.setattr(CONFIG.personal, "domains", [])

    _main(monkeypatch, "Hetzner?", "--domain", "whatever")

    assert "value is exactly `whatever`" in rendered["facts_md"]


# ── output + failure ─────────────────────────────────────────────────


def test_json_mode_prints_the_four_key_payload(env, monkeypatch, capsys) -> None:
    _main(monkeypatch, "Hetzner?", "--json", "--brief")

    assert json.loads(capsys.readouterr().out) == {
        "question": "Hetzner?",
        "answer": "THE ANSWER",
        "input_tokens": 120,
        "output_tokens": 30,
    }


def test_sdk_failure_and_oversized_prompt_exit_1(env, monkeypatch, caplog) -> None:
    _root, _rendered, seen, bumps = env

    seen["fail"] = True
    assert _exit_code(monkeypatch, "Hetzner?") == 1
    assert bumps == []

    seen.clear()
    monkeypatch.setattr(CONFIG.limits, "query_max_prompt_chars", 10)
    assert _exit_code(monkeypatch, "Hetzner?") == 1
    assert "compact index" in caplog.text and seen == {}
