"""`wiki collect --account` honoring (collectors/cli.py).

The `--account` flag used to be parsed and dropped with a permanent
"not yet honored" note. It is now honored — forwarded to the collector's
run() — but ONLY for account substrates (SPEC.supports_account_loop), the
field's first real consumer. A singleton collector handed --account is an
operator error, surfaced loudly (exit 1) rather than silently ignored.
"""

from __future__ import annotations

import collectors as collectors_pkg
import pytest

from collectors import cli
from collectors.base import CollectorSpec, RunResult


def _fake_collector(name: str, *, account_loop: bool):
    class _Fake:
        SPEC = CollectorSpec(
            name=name,
            output_subfolder="raw/x",
            piggyback_default=False,
            supports_account_loop=account_loop,
        )
        last: dict = {}

        def is_configured(self) -> bool:
            return True

        def run(self, *, dry_run: bool = False, incremental: bool = False, account=None):
            _Fake.last = {"dry_run": dry_run, "incremental": incremental, "account": account}
            return RunResult(message="ok")

    return _Fake


def test_account_rejected_for_non_account_substrate(monkeypatch, capsys):
    fake = _fake_collector("tabs", account_loop=False)
    monkeypatch.setattr(collectors_pkg, "get_collector", lambda n: fake())

    with pytest.raises(SystemExit) as exc:
        cli._run_one("tabs", dry_run=False, incremental=False, account="work")

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "does not support --account" in err
    assert fake.last == {}  # run() never called


def test_account_forwarded_for_account_substrate(monkeypatch, capsys):
    fake = _fake_collector("email", account_loop=True)
    monkeypatch.setattr(collectors_pkg, "get_collector", lambda n: fake())

    with pytest.raises(SystemExit) as exc:
        cli._run_one("email", dry_run=False, incremental=True, account="work")

    assert exc.value.code == 0
    assert fake.last["account"] == "work"
    assert fake.last["incremental"] is True


def test_no_account_flag_runs_without_account(monkeypatch, capsys):
    fake = _fake_collector("email", account_loop=True)
    monkeypatch.setattr(collectors_pkg, "get_collector", lambda n: fake())

    with pytest.raises(SystemExit) as exc:
        cli._run_one("email", dry_run=True, incremental=False, account=None)

    assert exc.value.code == 0
    assert fake.last["account"] is None
