"""`wiki config` in Python (M034-S02-T02) — `scripts/config_cli.py`.

The bash oracle holds the end-to-end parity on the fixture vault (`config-*` goldens); these
tests hold the command's own logic: the argument checks, the unknown-subcommand path, the
interactive editor driven through `core/console`'s `fd=` seam, and the status probe — with the
config store replaced, so no test touches a real `config.yaml`.
"""

from __future__ import annotations

import os

import pytest

import config_cli


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """An in-memory config: `_keys` / `_value` / `_set` read and write this dict."""
    values = {
        "models.compile_model": "claude-opus-4-8",
        "models.dream_model": "claude-opus-4-8[1m]",
        "scheduling.compile_after_hour": "18",
    }

    def fake_set(key: str, value: str) -> bool:
        values[key] = value
        print(f"set {key} = {value!r}")
        return True

    monkeypatch.setattr(config_cli, "_keys", lambda: list(values))
    monkeypatch.setattr(config_cli, "_value", lambda key: values.get(key, "?"))
    monkeypatch.setattr(config_cli, "_set", fake_set)
    return values


def _fd(*lines: str) -> int:
    r, w = os.pipe()
    os.write(w, "".join(lines).encode())
    os.close(w)
    return r


@pytest.mark.parametrize(
    ("argv", "usage"),
    [
        (["get"], "usage: wiki config get KEY"),
        (["get", "a", "b"], "usage: wiki config get KEY"),
        (["set", "models.compile_model"], "usage: wiki config set KEY VALUE"),
    ],
)
def test_wrong_argument_counts_are_refused(capsys, argv, usage):
    assert config_cli.main(argv) == 1
    assert usage in capsys.readouterr().err


def test_an_unknown_subcommand_errors_and_shows_help(capsys):
    assert config_cli.main(["bogus"]) == 1
    captured = capsys.readouterr()
    assert "unknown: wiki config bogus" in captured.err
    assert captured.out.startswith("wiki config — manage tunable parameters")


def test_the_editor_exits_at_once(store, capsys):
    assert config_cli.edit(fd=_fd("8\n")) == 0
    captured = capsys.readouterr()
    assert captured.out == (
        "wiki config — edit\nPick a section, then a key. Enter on a key skips it.\n\n\n\n✓ Done.\n"
    )
    assert "  * 8) exit\nSection [8]: " in captured.err


def test_the_editor_sets_a_key_and_lists_fresh_values(store, capsys):
    assert config_cli.edit(fd=_fd("1\n2\nclaude-sonnet-4-6\n1\nb\n8\n")) == 0
    out = capsys.readouterr().out
    assert store["models.dream_model"] == "claude-sonnet-4-6"
    assert (
        "set models.dream_model = 'claude-sonnet-4-6'\n✓ models.dream_model = claude-sonnet-4-6"
        in out
    )
    # the second visit to the section shows the value just set
    assert out.count("models.dream_model") >= 3
    assert out.rstrip().endswith("✓ Done.")


def test_the_editor_skips_an_empty_value(store, capsys):
    assert config_cli.edit(fd=_fd("1\n1\n\n8\n")) == 0
    assert store["models.compile_model"] == "claude-opus-4-8"
    assert "skipped" in capsys.readouterr().out


@pytest.mark.parametrize(("pick", "message"), [("x", "Invalid pick."), ("9", "Out of range.")])
def test_the_editor_rejects_a_bad_pick(store, capsys, pick, message):
    assert config_cli.edit(fd=_fd("1\n", f"{pick}\n", "8\n")) == 0
    assert message in capsys.readouterr().out


def test_status_reports_an_unreachable_ollama(store, monkeypatch, capsys):
    monkeypatch.setattr(config_cli, "_ollama_reachable", lambda url: False)
    store["models.ollama_url"] = "http://127.0.0.1:9"
    assert config_cli.status() == 0
    out = capsys.readouterr().out
    assert out.startswith("wiki config — status\n\nconfig.yaml ")
    assert "! Ollama unreachable at http://127.0.0.1:9" in out


def test_status_reports_a_reachable_ollama(store, monkeypatch, capsys):
    monkeypatch.setattr(config_cli, "_ollama_reachable", lambda url: True)
    assert config_cli.status() == 0
    assert "✓ Ollama reachable" in capsys.readouterr().out
