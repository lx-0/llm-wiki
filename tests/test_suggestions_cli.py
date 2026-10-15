"""M033-S04-T06 — characterisation of `suggestions.cli.main` over a tmp suggestions dir:
listing, per-action approve / reject with their stamps and exit codes, the scripted
interactive review, and the execute pass (dry-run vs real). Written before the split;
load / save / resolve / the action executors are covered by test_suggestions.py."""

from __future__ import annotations

import builtins
import copy
import sys

import pytest

from core.config import CONFIG
from suggestions import cli

SUGGESTION = {
    "target": "test-billing",
    "rationale": "Invoices pile up in INBOX",
    "actions": [
        {
            "type": "imap-move",
            "account": "work",
            "search": ["FROM", "billing@hetzner.com"],
            "source_folder": "INBOX",
            "target_folder": "INBOX/Hetzner",
        },
        {
            "type": "create-rule",
            "rule": {
                "name": "Hetzner",
                "condition": "OR (from,is,billing@hetzner.com)",
                "folder": "INBOX/Hetzner",
                "action": "Move to folder",
            },
        },
    ],
}


@pytest.fixture
def env(tmp_path, monkeypatch):
    d = tmp_path / "raw" / "suggestions"
    monkeypatch.setattr(cli, "RAW_SUGGESTIONS_DIR", d)
    monkeypatch.setattr(cli, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(CONFIG.personal, "primary_account", "work")
    monkeypatch.setattr(CONFIG.personal, "accounts", {"work": {"filter": {"kind": "imap"}}})
    d.mkdir(parents=True)
    path = d / "test-billing.yaml"
    cli.save_suggestion(path, copy.deepcopy(SUGGESTION))
    return d, path


def _main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["suggestions", *argv])
    cli.main()


def _statuses(path):
    return [a.get("status", "pending") for a in cli.load_suggestion(path)["actions"]]


def test_no_suggestions_is_a_message(env, monkeypatch, capsys) -> None:
    _d, path = env
    path.unlink()

    _main(monkeypatch)

    assert capsys.readouterr().out == "No suggestions in raw/suggestions/\n"


def test_list_describes_every_action(env, monkeypatch, capsys) -> None:
    _main(monkeypatch, "--list")

    out = capsys.readouterr().out
    for needle in (
        "File: test-billing.yaml",
        "Target: test-billing",
        "Rationale: Invoices pile up in INBOX",
        "  Action 1 [⏳ pending]: imap-move (account: work)",
        "    Search: ['FROM', 'billing@hetzner.com']",
        "    From: INBOX → To: INBOX/Hetzner",
        "  Action 2 [⏳ pending]: create-rule (account: work)",
        "    Account: work  Filter kind: imap",
        "    Rule:     Hetzner",
        "    Condition: OR (from,is,billing@hetzner.com)",
        "    Action:   Move to folder → INBOX/Hetzner",
    ):
        assert needle in out, needle


def test_approve_flips_one_action_and_stamps_it(env, monkeypatch, capsys) -> None:
    _d, path = env

    _main(monkeypatch, "--approve", "test-billing", "1")

    actions = cli.load_suggestion(path)["actions"]
    assert actions[0]["status"] == "approved" and actions[0]["reviewed"][:4] == "2026"
    assert "status" not in actions[1]
    out = capsys.readouterr().out
    assert "Approved action 1 in test-billing.yaml:" in out
    assert "  Action 1 [✅ approved]: imap-move (account: work)" in out


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (("--approve", "test-billing"), "Usage: --approve <file> <action_number>"),
        (("--approve", "test-billing", "9"), "Action 9 not found (file has 2 actions)"),
        (("--approve", "nope", "1"), "Not found: nope"),
        (("--reject", "test-billing"), "Usage: --reject <file> <action_number>"),
        (("--reject", "test-billing", "0"), "Usage: --reject <file> <action_number>"),
        (("--reject", "test-billing", "9"), "Action 9 not found (file has 2 actions)"),
    ],
)
def test_bad_approve_and_reject_calls_exit_1(env, monkeypatch, capsys, argv, message) -> None:
    _d, path = env

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, *argv)

    assert exc.value.code == 1
    assert message in capsys.readouterr().out
    assert _statuses(path) == ["pending", "pending"]


def test_approving_a_decided_action_exits_1(env, monkeypatch, capsys) -> None:
    _main(monkeypatch, "--approve", "test-billing", "1")

    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, "--approve", "test-billing", "1")

    assert exc.value.code == 1
    assert "Action 1 is already 'approved'" in capsys.readouterr().out


def test_reject_flips_one_action(env, monkeypatch, capsys) -> None:
    _d, path = env

    _main(monkeypatch, "--reject", "test-billing", "2")

    actions = cli.load_suggestion(path)["actions"]
    assert actions[1]["status"] == "rejected" and actions[1]["reviewed"][:4] == "2026"
    assert "Rejected action 2 in test-billing.yaml" in capsys.readouterr().out


def test_review_walks_pending_actions_with_the_operator(env, monkeypatch, capsys) -> None:
    _d, path = env
    answers = iter(["a", "r"])
    monkeypatch.setattr(builtins, "input", lambda prompt: next(answers))

    _main(monkeypatch, "--review", "test-billing")

    assert _statuses(path) == ["approved", "rejected"]
    out = capsys.readouterr().out
    assert "Reviewing: test-billing" in out and "    → Approved" in out and "    → Rejected" in out

    answers = iter(["q"])
    _main(monkeypatch, "--list")
    capsys.readouterr()
    _main(monkeypatch, "--review", "test-billing")
    out = capsys.readouterr().out
    assert "(already approved, skipping)" in out and "(already rejected, skipping)" in out
    assert "Review aborted." not in out  # nothing pending → the loop never asked


def test_review_skip_and_quit(env, monkeypatch, capsys) -> None:
    _d, path = env
    answers = iter(["x", "s", "q"])
    monkeypatch.setattr(builtins, "input", lambda prompt: next(answers))

    _main(monkeypatch, "--review", "test-billing")

    assert _statuses(path) == ["pending", "pending"]
    out = capsys.readouterr().out
    assert "    → Skipped" in out and "Review aborted." in out


def test_execute_runs_approved_actions_and_marks_them(env, monkeypatch, capsys) -> None:
    _d, path = env
    data = cli.load_suggestion(path)
    data["actions"][0]["status"] = "approved"
    cli.save_suggestion(path, data)
    executed: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        cli,
        "execute_action",
        lambda action, dry_run=True: executed.append((action["type"], dry_run)) or True,
    )

    _main(monkeypatch, "--dry-run")
    assert executed == [("imap-move", True)] and _statuses(path) == ["approved", "pending"]
    out = capsys.readouterr().out
    assert "File: test-billing.yaml — Action 1: imap-move" in out and "→ Executed" not in out

    _main(monkeypatch)
    actions = cli.load_suggestion(path)["actions"]
    assert executed[-1] == ("imap-move", False)
    assert actions[0]["status"] == "executed" and actions[0]["executed"][:4] == "2026"
    assert "    → Executed" in capsys.readouterr().out


def test_nothing_approved_says_so(env, monkeypatch, capsys) -> None:
    _main(monkeypatch)

    out = capsys.readouterr().out
    assert "No approved actions to execute." in out
    assert "Use --review <file> to approve individual actions first." in out
