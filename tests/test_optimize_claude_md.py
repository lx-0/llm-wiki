"""optimize_claude_md stages its edit inside the engine's state dir and lets the agent
edit only that staged copy.

It used to stage at `<vault>/scripts/claude-md-staged.md` — a pre-split path no vault
has any more — so an opted-in run died with FileNotFoundError before the agent ran; and
it handed the agent Edit under `acceptEdits` with no path limit, over a prompt that
embeds the wiki index (distilled from substrate)."""

from __future__ import annotations

import asyncio


def test_optimize_stages_in_state_and_scopes_the_edit_to_the_staged_copy(tmp_path, monkeypatch):
    import core.usage as usage_mod
    import optimize_claude_md as ocm

    vault = tmp_path / "vault"
    vault.mkdir()  # a post-split vault: no scripts/ at its root
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# rules\n", encoding="utf-8")
    staging = vault / ".wiki" / "state" / "claude-md-staged.md"
    monkeypatch.setattr(ocm, "ROOT_DIR", vault)
    monkeypatch.setattr(ocm, "CLAUDE_MD", claude_md)
    monkeypatch.setattr(ocm, "BACKUP_DIR", vault / "raw" / "notes" / "claude-md-backups")
    monkeypatch.setattr(ocm, "STAGING_FILE", staging)
    monkeypatch.setattr(ocm, "read_wiki_index_compact", lambda: "")
    monkeypatch.setattr(ocm, "render", lambda *a, **kw: "prompt")
    monkeypatch.setattr(usage_mod, "LEDGER", usage_mod.UsageLedger())
    seen: dict = {}

    async def fake_query(*, prompt, options):
        seen["options"] = options
        seen["staged"] = staging.read_text(encoding="utf-8")
        return
        yield  # an async generator, like the SDK's query()

    monkeypatch.setattr(ocm, "query", fake_query)

    asyncio.run(ocm.optimize(dry_run=False))

    assert seen["staged"] == "# rules\n"  # staged before the agent ran
    options = seen["options"]
    assert options.permission_mode != "acceptEdits"
    assert options.mcp_servers == {}
    assert "strict-mcp-config" in options.extra_args
    [matcher] = options.hooks["PreToolUse"]
    [hook] = matcher.hooks

    def decision(path):
        hook_input = {"tool_name": "Edit", "tool_input": {"file_path": str(path)}}
        out = asyncio.run(hook(hook_input, None, None))
        return out["hookSpecificOutput"]["permissionDecision"]

    assert decision(staging) == "allow"
    assert decision(claude_md) == "deny"
    assert decision(vault / "knowledge" / "concepts" / "x.md") == "deny"
    # The agent changed nothing, so CLAUDE.md is untouched and the staged copy gone.
    assert claude_md.read_text(encoding="utf-8") == "# rules\n"
    assert not staging.exists()
