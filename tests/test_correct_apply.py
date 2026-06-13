"""Tests for `wiki correct apply` — the agentic fact-propagation path.

M028-S01: `apply()` must run sandboxed like `reconcile_fact()` — no Bash, a
PreToolUse path-scope hook, `permission_mode="default"`, and a config-knob
turn bound. The agent annotates; it can no longer shell out or delete.
"""

from __future__ import annotations


def test_apply_options_sandboxed() -> None:
    """`_apply_agent_options` returns a non-destructive, path-scoped config.

    Regression guard for issue #5: the wide-open `apply()` (Bash +
    acceptEdits + hardcoded 50 turns, no hook) deleted 17 articles. The
    sandboxed options make destruction structurally impossible.
    """
    from facts import correct_apply
    from core.config import CONFIG
    from core.sdk_helpers import StderrCapture

    opts = correct_apply._apply_agent_options(StderrCapture())

    # Bash is gone — the agent cannot `rm`/`git mv`.
    assert "Bash" not in opts.allowed_tools
    assert set(opts.allowed_tools) == {"Read", "Glob", "Grep", "Write", "Edit"}

    # Not acceptEdits — writes go through the hook.
    assert opts.permission_mode == "default"

    # Turn bound is a config knob, not a magic number.
    assert opts.max_turns == CONFIG.limits.correct_apply_max_turns

    # A PreToolUse Write|Edit hook is wired (path-scope).
    assert "PreToolUse" in (opts.hooks or {})
    assert opts.hooks["PreToolUse"], "PreToolUse hook list must be non-empty"


def _render_apply_prompt(deletion_allowed: str = "false") -> str:
    from core.prompts import render

    return render(
        "correct_apply",
        fact_content="---\nstatus: negation\n---\nWe did NOT win X.",
        fact_path="knowledge/facts/x.md",
        slug="x",
        today="2026-06-13",
        now="2026-06-13T12:00:00",
        deletion_allowed=deletion_allowed,
    )


def test_apply_prompt_supersedes_by_default() -> None:
    """M028-S01-T03: the negation branch annotates, it does not delete."""
    p = _render_apply_prompt()
    assert "status: superseded" in p
    assert "superseded_by" in p
    assert "outdated_since" in p
    # The load-bearing rule, verbatim.
    assert "outdated != false" in p
    # No-shell / engine-disposes contract.
    assert "no shell" in p.lower()


def test_apply_prompt_has_json_proposal_contract() -> None:
    """The agent emits a machine-readable `## Proposed actions` JSON block."""
    p = _render_apply_prompt()
    assert "## Proposed actions" in p
    for key in ("superseded", "renamed", "deleted"):
        assert f'"{key}"' in p


def test_apply_prompt_renders_deletion_gate() -> None:
    """`${deletion_allowed}` is threaded so S02 can gate deletion nomination."""
    assert "Deletion permitted: false" in _render_apply_prompt("false")
    assert "Deletion permitted: true" in _render_apply_prompt("true")


# ── _parse_proposed_actions (M028-S01-T04): the JSON proposal contract ──

_AGENT_OUTPUT = """## Applied summary

Superseded `knowledge/concepts/foo.md` (was true, now outdated).

## Proposed actions

```json
{
  "superseded": ["knowledge/concepts/foo.md"],
  "edited": [],
  "renamed": [{"from": "knowledge/projects/township.md", "to": "knowledge/projects/fleet.md"}],
  "deleted": []
}
```
"""


def test_parse_proposed_actions_extracts_json_block() -> None:
    from facts import correct_apply

    a = correct_apply._parse_proposed_actions(_AGENT_OUTPUT)
    assert a["superseded"] == ["knowledge/concepts/foo.md"]
    assert a["renamed"] == [
        {"from": "knowledge/projects/township.md", "to": "knowledge/projects/fleet.md"}
    ]
    assert a["deleted"] == []


def test_parse_proposed_actions_defaults_on_garbage() -> None:
    """No parseable JSON → all-empty, never raises (a bad agent run must not crash)."""
    from facts import correct_apply

    a = correct_apply._parse_proposed_actions("no json here, just prose")
    assert a == {"superseded": [], "edited": [], "renamed": [], "deleted": []}


def test_parse_proposed_actions_shape_guards_nonlist() -> None:
    """LLM lies about types — a scalar where a list is expected is coerced empty."""
    from facts import correct_apply

    a = correct_apply._parse_proposed_actions('{"deleted": "oops", "renamed": [{"bad": 1}]}')
    assert a["deleted"] == []          # scalar → []
    assert a["renamed"] == []          # malformed {from,to} dropped


# ── ground-truth reporting (M028-S01-T05) ──


def test_parse_porcelain_classifies_codes() -> None:
    from facts import correct_apply

    out = (
        " M knowledge/concepts/foo.md\n"
        " D knowledge/concepts/gone.md\n"
        "?? knowledge/concepts/new.md\n"
        "R  knowledge/projects/old.md -> knowledge/projects/new.md\n"
    )
    d = correct_apply._parse_porcelain(out)
    assert d["modified"] == ["knowledge/concepts/foo.md"]
    assert d["deleted"] == ["knowledge/concepts/gone.md"]
    assert d["created"] == ["knowledge/concepts/new.md"]
    assert d["renamed"] == ["knowledge/projects/old.md -> knowledge/projects/new.md"]


def test_delta_from_snapshot(tmp_path) -> None:
    from facts import correct_apply

    keep = tmp_path / "keep.md"
    gone = tmp_path / "gone.md"
    keep.write_text("a", encoding="utf-8")
    gone.write_text("b", encoding="utf-8")
    before = correct_apply._snapshot([tmp_path])
    gone.unlink()
    keep.write_text("a-changed-longer", encoding="utf-8")
    (tmp_path / "new.md").write_text("c", encoding="utf-8")
    after = correct_apply._snapshot([tmp_path])

    d = correct_apply._delta_from_snapshot(before, after)
    assert str(gone) in d["deleted"]
    assert str(keep) in d["modified"]
    assert str(tmp_path / "new.md") in d["created"]


def test_divergence_fires_when_real_deletes_exceed_declared() -> None:
    from facts import correct_apply

    actions = {"superseded": [], "edited": [], "renamed": [], "deleted": ["a.md"]}
    delta = {"created": [], "modified": [], "deleted": ["a.md", "b.md", "c.md"], "renamed": []}
    warnings = correct_apply._divergence(actions, delta, executed_renames=[])
    assert warnings, "must warn when files vanished beyond what was declared"
    assert any("vanish" in w.lower() or "deleted" in w.lower() for w in warnings)


def test_divergence_silent_when_counts_match() -> None:
    from facts import correct_apply

    actions = {"superseded": ["a.md"], "edited": [], "renamed": [], "deleted": []}
    delta = {"created": [], "modified": ["a.md"], "deleted": [], "renamed": []}
    assert correct_apply._divergence(actions, delta, executed_renames=[]) == []


def test_divergence_does_not_flag_engine_rename_as_deletion() -> None:
    """A rename shows as delete(old)+create(new) in a snapshot/unstaged tree —
    the engine knows it renamed, so it must NOT raise a deletion alarm."""
    from facts import correct_apply

    actions = {"superseded": [], "edited": [], "renamed":
               [{"from": "knowledge/projects/township.md", "to": "knowledge/projects/fleet.md"}],
               "deleted": []}
    delta = {"created": ["knowledge/projects/fleet.md"], "modified": [],
             "deleted": ["knowledge/projects/township.md"], "renamed": []}
    executed = [{"from": "knowledge/projects/township.md", "to": "knowledge/projects/fleet.md"}]
    assert correct_apply._divergence(actions, delta, executed_renames=executed) == []


def test_apply_golden_supersede_renames_deletes_nothing(tmp_path, monkeypatch, caplog) -> None:
    """Issue-#5 golden: a sandboxed apply over a fixture vault annotates/renames
    via the engine but deletes ZERO articles, and stamps the fact applied."""
    import asyncio
    from facts import correct_apply
    from claude_agent_sdk import ResultMessage

    vault = tmp_path
    knowledge = vault / "knowledge"
    facts = knowledge / "facts"
    facts.mkdir(parents=True)
    (knowledge / "projects").mkdir()
    (knowledge / "concepts").mkdir()
    old = knowledge / "projects" / "township.md"
    old.write_text("# Township\n\nold strategy\n", encoding="utf-8")
    ref = knowledge / "concepts" / "foo.md"
    ref.write_text("See [[../projects/township]] for details.\n", encoding="utf-8")
    index = knowledge / "index.md"
    index.write_text("- [[projects/township]] — the project\n", encoding="utf-8")
    fact = facts / "ssot.md"
    fact.write_text(
        "---\ntype: fact\nstatus: disambiguation\napplied: false\n---\n\nTownship is now Fleet.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(correct_apply, "ROOT_DIR", vault)
    monkeypatch.setattr(correct_apply, "FACTS_DIR", facts)
    monkeypatch.setattr(correct_apply, "KNOWLEDGE_DIR", knowledge)
    monkeypatch.setattr(correct_apply, "INDEX_FILE", index)
    monkeypatch.setattr(correct_apply.LEDGER, "record", lambda **k: None)

    agent_out = (
        "## Applied summary\nRenamed township → fleet.\n\n"
        "## Proposed actions\n```json\n"
        '{"superseded": [], "edited": [],'
        ' "renamed": [{"from": "knowledge/projects/township.md", "to": "knowledge/projects/fleet.md"}],'
        ' "deleted": []}\n```\n'
    )

    async def fake_query(*, prompt, options):  # noqa: ARG001
        yield ResultMessage(
            subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
            num_turns=1, session_id="t", total_cost_usd=0.0,
            usage={"input_tokens": 1, "output_tokens": 1}, result=agent_out,
        )

    monkeypatch.setattr(correct_apply, "query", fake_query)

    import logging as _logging
    caplog.set_level(_logging.WARNING, logger="correct-apply")
    rc = asyncio.run(correct_apply.apply("ssot", dry_run=False))
    assert rc == 0
    # The engine rename must NOT trip the issue-#5 deletion alarm.
    assert "vanished with no accounting" not in caplog.text
    # Engine performed the rename.
    assert not old.exists()
    assert (knowledge / "projects" / "fleet.md").exists()
    assert "[[../projects/fleet]]" in ref.read_text(encoding="utf-8")
    # ZERO deletions — the article that merely *mentions* the term survives.
    assert ref.exists()
    # Fact stamped applied (no longer False).
    stamped = fact.read_text(encoding="utf-8")
    assert "applied: false" not in stamped.lower()


# ── delete executor (M028-S02-T01): nominated → .trash, never unlink ──


def _delete_vault(tmp_path, monkeypatch):
    from facts import correct_apply

    vault = tmp_path
    knowledge = vault / "knowledge"
    (knowledge / "concepts").mkdir(parents=True)
    doomed = knowledge / "concepts" / "false-claim.md"
    doomed.write_text("# False claim\n", encoding="utf-8")
    index = knowledge / "index.md"
    index.write_text(
        "- [[concepts/false-claim]] — bogus\n- [[concepts/keep]] — real\n", encoding="utf-8"
    )
    monkeypatch.setattr(correct_apply, "ROOT_DIR", vault)
    monkeypatch.setattr(correct_apply, "KNOWLEDGE_DIR", knowledge)
    monkeypatch.setattr(correct_apply, "INDEX_FILE", index)
    return correct_apply, vault, knowledge, doomed, index


def test_execute_deletes_moves_to_trash_when_allowed(tmp_path, monkeypatch) -> None:
    mod, vault, knowledge, doomed, index = _delete_vault(tmp_path, monkeypatch)
    actions = {"superseded": [], "edited": [], "renamed": [],
               "deleted": ["knowledge/concepts/false-claim.md"]}

    executed = mod._execute_deletes(actions, vault, allowed=True)

    assert executed == ["knowledge/concepts/false-claim.md"]
    assert not doomed.exists()                      # gone from original location
    trashed = list((vault / ".trash").rglob("false-claim.md"))
    assert trashed, "file must be recoverable under .trash/"
    # index row dropped, sibling kept
    idx = index.read_text(encoding="utf-8")
    assert "false-claim" not in idx
    assert "concepts/keep" in idx


def test_execute_deletes_noop_when_gate_off(tmp_path, monkeypatch) -> None:
    mod, vault, knowledge, doomed, index = _delete_vault(tmp_path, monkeypatch)
    actions = {"superseded": [], "edited": [], "renamed": [],
               "deleted": ["knowledge/concepts/false-claim.md"]}

    executed = mod._execute_deletes(actions, vault, allowed=False)

    assert executed == []
    assert doomed.exists()                          # gate off → nothing deleted
    assert not (vault / ".trash").exists()


def test_execute_deletes_skips_outside_knowledge(tmp_path, monkeypatch) -> None:
    mod, vault, knowledge, doomed, index = _delete_vault(tmp_path, monkeypatch)
    actions = {"superseded": [], "edited": [], "renamed": [], "deleted": ["raw/notes/x.md"]}

    executed = mod._execute_deletes(actions, vault, allowed=True)
    assert executed == []                           # never delete outside knowledge/


# ── deletion gate (M028-S02-T02) ──


def test_deletion_allowed_resolution() -> None:
    from facts import correct_apply

    assert correct_apply._deletion_allowed({}, True) is True            # CLI flag
    assert correct_apply._deletion_allowed({"disposition": "delete"}, False) is True  # fact field
    assert correct_apply._deletion_allowed({}, False) is False          # neither
    assert correct_apply._deletion_allowed({"disposition": "supersede"}, False) is False


def test_apply_allow_delete_trashes_nominated(tmp_path, monkeypatch) -> None:
    """End-to-end: with the gate ON, a nominated factually-false article is trashed."""
    import asyncio
    from facts import correct_apply
    from claude_agent_sdk import ResultMessage

    vault = tmp_path
    knowledge = vault / "knowledge"
    facts = knowledge / "facts"
    facts.mkdir(parents=True)
    (knowledge / "concepts").mkdir()
    bogus = knowledge / "concepts" / "bogus.md"
    bogus.write_text("# Bogus event that never happened\n", encoding="utf-8")
    (knowledge / "index.md").write_text("- [[concepts/bogus]] — x\n", encoding="utf-8")
    fact = facts / "neverhappened.md"
    fact.write_text("---\ntype: fact\nstatus: negation\napplied: false\n---\n\nThat never happened.\n", encoding="utf-8")

    monkeypatch.setattr(correct_apply, "ROOT_DIR", vault)
    monkeypatch.setattr(correct_apply, "FACTS_DIR", facts)
    monkeypatch.setattr(correct_apply, "KNOWLEDGE_DIR", knowledge)
    monkeypatch.setattr(correct_apply, "INDEX_FILE", knowledge / "index.md")
    monkeypatch.setattr(correct_apply.LEDGER, "record", lambda **k: None)

    agent_out = (
        "## Proposed actions\n```json\n"
        '{"superseded": [], "edited": [], "renamed": [],'
        ' "deleted": ["knowledge/concepts/bogus.md"]}\n```\n'
    )

    async def fake_query(*, prompt, options):  # noqa: ARG001
        # the gate must reach the prompt
        assert "Deletion permitted: true" in prompt
        yield ResultMessage(
            subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
            num_turns=1, session_id="t", total_cost_usd=0.0,
            usage={"input_tokens": 1, "output_tokens": 1}, result=agent_out,
        )

    monkeypatch.setattr(correct_apply, "query", fake_query)

    # force=True bypasses the clean-git-tree guard (tested separately) — this test
    # exercises the gate + executor on a non-git tmp vault.
    rc = asyncio.run(correct_apply.apply("neverhappened", dry_run=False, allow_delete=True, force=True))
    assert rc == 0
    assert not bogus.exists()
    assert list((vault / ".trash").rglob("bogus.md")), "must be recoverable in .trash"


# ── dirty/non-git tree guard (M028-S02-T03) ──


def _git_init(path) -> None:
    import subprocess
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", "init"], check=True,
    )


def test_tree_safe_non_git(tmp_path, monkeypatch) -> None:
    from facts import correct_apply
    monkeypatch.setattr(correct_apply, "KNOWLEDGE_DIR", tmp_path / "knowledge")
    safe, reason = correct_apply._tree_safe_for_deletion(tmp_path)
    assert safe is False and "git" in reason.lower()


def test_tree_safe_clean_then_dirty(tmp_path, monkeypatch) -> None:
    from facts import correct_apply
    knowledge = tmp_path / "knowledge"
    (knowledge / "concepts").mkdir(parents=True)
    (knowledge / "concepts" / "a.md").write_text("# A\n", encoding="utf-8")
    (knowledge / "facts").mkdir()
    monkeypatch.setattr(correct_apply, "KNOWLEDGE_DIR", knowledge)
    _git_init(tmp_path)

    assert correct_apply._tree_safe_for_deletion(tmp_path)[0] is True
    # an uncommitted FACT is fine (excluded) …
    (knowledge / "facts" / "f.md").write_text("x", encoding="utf-8")
    assert correct_apply._tree_safe_for_deletion(tmp_path)[0] is True
    # … an uncommitted ARTICLE is not
    (knowledge / "concepts" / "a.md").write_text("# A changed\n", encoding="utf-8")
    assert correct_apply._tree_safe_for_deletion(tmp_path)[0] is False


def test_apply_refuses_deletion_on_unsafe_tree(tmp_path, monkeypatch) -> None:
    import asyncio
    from facts import correct_apply

    facts = tmp_path / "knowledge" / "facts"
    facts.mkdir(parents=True)
    (facts / "f.md").write_text("---\ntype: fact\nstatus: negation\n---\n\nx\n", encoding="utf-8")
    monkeypatch.setattr(correct_apply, "ROOT_DIR", tmp_path)        # not a git repo
    monkeypatch.setattr(correct_apply, "FACTS_DIR", facts)
    monkeypatch.setattr(correct_apply, "KNOWLEDGE_DIR", tmp_path / "knowledge")

    called = {"spawned": False}

    async def fake_query(*, prompt, options):  # noqa: ARG001
        called["spawned"] = True
        yield None

    monkeypatch.setattr(correct_apply, "query", fake_query)

    rc = asyncio.run(correct_apply.apply("f", dry_run=False, allow_delete=True))
    assert rc == 3                          # refused
    assert called["spawned"] is False       # no paid agent run
    # …but --force bypasses the guard (will spawn; we only assert it gets past the gate)
    rc2 = asyncio.run(correct_apply.apply("f", dry_run=False, allow_delete=True, force=True))
    assert called["spawned"] is True
