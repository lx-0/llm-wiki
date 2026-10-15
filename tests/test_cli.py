"""Tests for scripts/cli.py — the table-driven `wiki` dispatcher.

These pin the three properties the inversion is supposed to guarantee and can
no longer be hand-drifted (C06):

1. Every catalog row is dispatchable — every `py` handler (and subroute) script
   exists; every `auth` service resolves to a real bootstrap function.
2. `wiki help` is complete — every command in the table appears, including the
   nine that the old bash help was blind to.
3. Dispatch policy is centralized — banner, subroute selection, refresh-after,
   and the OAuth argv path all behave as declared.
"""

from __future__ import annotations

import importlib
import subprocess

import pytest

import cli

# ── 1. Every row is dispatchable ────────────────────────────────────────


def test_command_names_unique():
    names = [c.name for c in cli.COMMANDS]
    assert len(names) == len(set(names)), "duplicate command names in COMMANDS"


def test_every_py_handler_script_exists():
    for c in cli.COMMANDS:
        if c.kind == "py" and c.handler is not None:
            assert (cli.SCRIPTS_DIR / c.handler).exists(), f"{c.name}: {c.handler} missing"
        for sub in c.subroutes:
            assert (cli.SCRIPTS_DIR / sub.script).exists(), (
                f"{c.name}/{sub.key}: {sub.script} missing"
            )


def test_backfill_command_only_dispatches_via_subroutes():
    """backfill has no default handler — bare invocation must show help, not run."""
    backfill = cli.BY_NAME["backfill"]
    assert backfill.handler is None
    assert backfill.subroutes, "backfill needs subroutes to dispatch anything"
    assert backfill.show_help_on_empty


def test_auth_registry_functions_exist():
    for service, (module_name, func_name) in cli.AUTH_SERVICES.items():
        module = importlib.import_module(module_name)
        assert hasattr(module, func_name), f"auth {service}: {module_name}.{func_name} missing"


# ── 2. Help is complete ─────────────────────────────────────────────────


def test_help_lists_every_command():
    text = cli.render_help()
    for c in cli.COMMANDS:
        assert c.name in text, f"{c.name} absent from `wiki help`"


def test_previously_invisible_commands_now_visible():
    """The nine commands the old bash help omitted must render now."""
    text = cli.render_help()
    for name in (
        "produce",
        "triage",
        "bridge",
        "backfill",
        "reconcile",
        "health-trends",
        "usage",
        "study",
        "analyze",
    ):
        assert name in text, f"{name} still invisible in help"


def test_every_py_command_has_help_text():
    for c in cli.COMMANDS:
        if c.kind == "py":
            assert c.help_text, f"{c.name}: py command without help_text (operator doc loss)"


# ── 3. Dispatch policy ──────────────────────────────────────────────────


@pytest.fixture
def spy(monkeypatch):
    """Capture child dispatch + refresh calls without spawning anything."""
    calls: dict[str, object] = {"child": None, "refreshed": False}

    def fake_child(script_rel, args):
        calls["child"] = (script_rel, list(args))
        return 0

    def fake_refresh():
        calls["refreshed"] = True

    monkeypatch.setattr(cli, "_run_child", fake_child)
    monkeypatch.setattr(cli, "refresh_dashboards", fake_refresh)
    return calls


def test_run_command_dispatches_child_with_args(spy, capsys):
    code = cli.run_command(cli.BY_NAME["compile"], ["--all"])
    assert code == 0
    assert spy["child"] == ("compile.py", ["--all"])
    # compile carries a banner
    assert "wiki compile" in capsys.readouterr().out


def test_refresh_after_runs_only_when_flagged(spy):
    cli.run_command(cli.BY_NAME["compile"], [])  # refresh_after=True
    assert spy["refreshed"] is True

    spy["refreshed"] = False
    cli.run_command(cli.BY_NAME["flush"], [])  # refresh_after=False (flush self-refreshes)
    assert spy["refreshed"] is False


def test_no_banner_command_stays_quiet(spy, capsys):
    cli.run_command(cli.BY_NAME["triage"], ["--all"])  # banner=False
    assert capsys.readouterr().out == ""
    assert spy["child"] == ("triage.py", ["--all"])


@pytest.mark.parametrize("name", ["query", "usage", "publish"])
def test_json_invocation_prints_no_banner(spy, capsys, name):
    """`--json` is a machine-readable seam (the desktop parses `wiki query --json`
    stdout): the payload alone, so the dispatcher prints no banner for it — the human
    invocation of the same command keeps its banner. M033-S04-T06: the live `wiki
    query --brief --json` on the scratch vault returned `wiki query\\n\\n{…}`."""
    cli.run_command(cli.BY_NAME[name], ["x", "--json"])
    assert capsys.readouterr().out == ""
    assert spy["child"][1] == ["x", "--json"]

    cli.run_command(cli.BY_NAME[name], ["x"])
    assert f"wiki {name}" in capsys.readouterr().out


def test_subroute_correct_apply_selects_apply_script(spy, capsys):
    code = cli.run_command(cli.BY_NAME["correct"], ["apply", "some-slug", "--dry-run"])
    assert code == 0
    # "apply" is consumed; the rest passes to correct_apply.py
    assert spy["child"] == ("facts/correct_apply.py", ["some-slug", "--dry-run"])
    assert spy["refreshed"] is True
    assert "wiki correct apply" in capsys.readouterr().out


def test_subroute_backfill_selects_backfill_script(spy):
    cli.run_command(cli.BY_NAME["backfill"], ["picture-metadata", "--dry-run"])
    assert spy["child"] == ("backfill_picture_metadata.py", ["--dry-run"])


def test_backfill_bare_shows_help_exit_zero(spy, capsys):
    code = cli.run_command(cli.BY_NAME["backfill"], [])
    assert code == 0
    assert spy["child"] is None
    assert "wiki backfill" in capsys.readouterr().out


def test_backfill_unknown_subcommand_errors(spy, capsys):
    code = cli.run_command(cli.BY_NAME["backfill"], ["nonsense"])
    assert code == 1
    assert spy["child"] is None
    assert "unknown" in capsys.readouterr().err.lower()


def test_help_flag_intercepts_before_dispatch(spy, capsys):
    code = cli.run_command(cli.BY_NAME["compile"], ["--help"])
    assert code == 0
    assert spy["child"] is None
    out = capsys.readouterr().out
    assert "wiki compile" in out and "USAGE" in out


def test_query_bare_shows_help_exit_zero(spy):
    code = cli.run_command(cli.BY_NAME["query"], [])
    assert code == 0
    assert spy["child"] is None


def test_correct_bare_shows_help_exit_one(spy):
    code = cli.run_command(cli.BY_NAME["correct"], [])
    assert code == 1  # bare correct signals "provide a subcommand"
    assert spy["child"] is None


# ── OAuth argv path (no python -c injection) ─────────────────────────────


def test_run_auth_passes_account_id_as_argument(monkeypatch, capsys):
    captured: dict[str, str] = {}

    class _FakeModule:
        @staticmethod
        def gmail_auth_bootstrap(account_id):
            captured["arg"] = account_id
            return True, "ok"

    monkeypatch.setattr(cli.importlib, "import_module", lambda name: _FakeModule)
    # A shell-metacharacter-laden id must reach the function verbatim — proof it
    # is a function argument, never interpolated into source or a shell.
    hostile = "private'); import os; os.system('boom"
    code = cli.run_auth(["gmail", hostile])
    assert code == 0
    assert captured["arg"] == hostile
    assert "ok" in capsys.readouterr().out


def test_run_auth_maps_failure_to_exit_one(monkeypatch):
    class _FakeModule:
        @staticmethod
        def gmail_auth_bootstrap(account_id):
            return False, "no client json"

    monkeypatch.setattr(cli.importlib, "import_module", lambda name: _FakeModule)
    assert cli.run_auth(["gmail", "acct"]) == 1


def test_run_auth_unknown_service_errors(capsys):
    assert cli.run_auth(["dropbox", "acct"]) == 1
    assert "unknown auth service" in capsys.readouterr().err


def test_run_auth_no_account_id_shows_help(capsys):
    assert cli.run_auth(["gmail"]) == 0
    assert "wiki auth" in capsys.readouterr().out


# ── main() routing ──────────────────────────────────────────────────────


def test_main_help_renders_catalog(capsys):
    assert cli.main(["help"]) == 0
    assert "Knowledge ops" in capsys.readouterr().out


def test_main_unknown_command_errors(capsys):
    assert cli.main(["frobnicate"]) == 1
    assert "unknown command" in capsys.readouterr().err


def test_main_refuses_bash_native_commands(capsys):
    """bash-native commands (setup/hooks/…, until their M034 port) are dispatched by the
    bash layer; reaching cli.main with one is an error, not a silent no-op."""
    assert cli.main(["setup"]) == 1
    assert "unknown command" in capsys.readouterr().err


def test_main_auth_routes(monkeypatch):
    seen: dict[str, list[str]] = {}

    def fake_auth(rest):
        seen["rest"] = rest
        return 0

    monkeypatch.setattr(cli, "run_auth", fake_auth)
    assert cli.main(["auth", "gmail", "acct"]) == 0
    assert seen["rest"] == ["gmail", "acct"]


def test_main_refresh_dashboards(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(cli, "refresh_dashboards", lambda: called.__setitem__("n", called["n"] + 1))
    assert cli.main(["refresh-dashboards"]) == 0
    assert called["n"] == 1


# ── Home & status, ported from bash (M034-S01-T05) ──────────────────────


def test_bare_entry_opens_the_menu_on_a_terminal(spy, monkeypatch):
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    assert cli.main([]) == 0
    assert spy["child"] == ("menu.py", [])


def test_bare_entry_prints_help_without_a_terminal(spy, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_interactive", lambda: False)
    assert cli.main([]) == 0
    assert spy["child"] is None
    assert "Knowledge ops" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("name", "handler"),
    [("menu", "menu.py"), ("doctor", "doctor.py"), ("version", "engine_version.py")],
)
def test_home_and_status_commands_run_their_handler_without_a_banner(spy, capsys, name, handler):
    """The bash wrappers printed no banner; the handlers print their own output."""
    assert cli.main([name]) == 0
    assert spy["child"] == (handler, [])
    assert capsys.readouterr().out == ""


def test_menu_json_runs_the_payload_without_a_banner(spy, capsys):
    """The desktop parses `wiki menu --json` stdout: the payload alone."""
    assert cli.main(["menu", "--json"]) == 0
    assert spy["child"] == ("menu_context.py", [])
    assert capsys.readouterr().out == ""


def test_menu_refuses_an_argument_it_does_not_route(spy, capsys):
    assert cli.main(["menu", "bogus"]) == 1
    assert spy["child"] is None
    assert "unknown: wiki menu bogus (try 'wiki menu help')" in capsys.readouterr().err


def test_doctor_passes_its_flags_through(spy):
    assert cli.main(["doctor", "--quick", "--json"]) == 0
    assert spy["child"] == ("doctor.py", ["--quick", "--json"])


def _git(repo, *args: str) -> str:
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    return subprocess.run(
        ["git", "-C", str(repo), *identity, *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def test_engine_version_reports_revision_tag_and_origin(tmp_path):
    import engine_version

    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "engine")
    _git(tmp_path, "remote", "add", "origin", "https://example.invalid/engine.git")
    rev = _git(tmp_path, "rev-parse", "--short", "HEAD")

    assert engine_version.report(tmp_path) == [
        f"revision     {rev}",
        "origin       https://example.invalid/engine.git",
    ]

    _git(tmp_path, "tag", "v9.9.9")
    assert engine_version.report(tmp_path)[1] == "tag          v9.9.9"


def test_engine_version_outside_a_checkout(tmp_path):
    import engine_version

    assert engine_version.report(tmp_path) == ["! Not a git checkout. Cannot report version."]
