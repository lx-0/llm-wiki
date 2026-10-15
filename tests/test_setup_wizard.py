"""The setup wizard in Python (M034-S02-T03) — `config_cli.wizard` (`wiki config wizard`) and
`setup_cli` (`wiki setup` = the wizard, then the hooks step).

The bash oracle holds end-to-end parity on the fixture vault (`setup-wizard`,
`setup-with-hooks`, `config-wizard-validates`); these tests hold the wizard's own logic with
the config store replaced and the answers scripted through `core/console`'s `fd=` seam.
"""

from __future__ import annotations

import os

import pytest

import config_cli
import setup_cli


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    values = {
        "models.ollama_url": "http://127.0.0.1:9",
        "models.compile_model": "claude-opus-4-8",
        "scheduling.compile_after_hour": "18",
        "features.procmail_execution": "True",
        "skills.global_install": "False",
    }
    writes: list[tuple[str, str]] = []

    def fake_set(key: str, value: str) -> bool:
        values[key] = value
        writes.append((key, value))
        print(f"set {key} = {value!r}")
        return True

    monkeypatch.setattr(config_cli, "_value", lambda key: values.get(key, "?"))
    monkeypatch.setattr(config_cli, "_set", fake_set)
    monkeypatch.setattr(config_cli, "_ollama_reachable", lambda url: False)
    values["_writes"] = writes  # type: ignore[assignment]
    return values


def _fd(*lines: str) -> int:
    r, w = os.pipe()
    os.write(w, "".join(lines).encode())
    os.close(w)
    return r


def test_all_defaults_keep_the_current_values(store, capsys):
    assert config_cli.wizard(fd=_fd("\n" * 6)) == 0
    writes = store["_writes"]
    # unchanged URL / model / hour are not written; the three switches always are
    assert [k for k, _ in writes] == [
        "features.procmail_execution",
        "features.curiosity_loop",
        "features.vision_screenshots",
        "skills.global_install",
    ]
    assert writes[0] == ("features.procmail_execution", "true")  # its current value: on
    assert writes[1] == ("features.curiosity_loop", "false")  # Ollama unreachable → no
    out = capsys.readouterr().out
    assert out.startswith(
        "wiki config — setup wizard\n6 questions. Skip with Enter to keep the current value.\n\n\n"
    )
    assert "! Ollama NOT reachable at http://127.0.0.1:9 — local-LLM features will fail." in out
    assert "Default OFF" not in out  # the default has been on since the first release
    assert out.rstrip().endswith(
        "✓ Wizard complete. Config written to " + str(config_cli.core_config.CONFIG_FILE) + "."
    )


def test_a_refused_url_is_asked_again_and_never_written(store, capsys):
    """The bash wrote the validator's warning into config.yaml (fixed in 0.7.10)."""
    config_cli.wizard(fd=_fd("ftp://x\n", "\n", "3\n", "25\n", "7\n", "y\n", "y\n", "y\n"))
    writes = dict(store["_writes"])
    assert "models.ollama_url" not in writes
    assert writes["models.compile_model"] == "claude-haiku-4-5"
    assert writes["scheduling.compile_after_hour"] == "7"
    assert writes["features.curiosity_loop"] == "true"
    err = capsys.readouterr().err
    assert "! Must start with http:// or https://" in err
    assert "! Hour must be 0–23" in err


def test_a_new_url_is_written_and_probed(store, monkeypatch, capsys):
    probed: list[str] = []
    monkeypatch.setattr(config_cli, "_ollama_reachable", lambda url: probed.append(url) or True)
    config_cli.wizard(fd=_fd("http://ollama.local:11434\n", "\n" * 5))
    assert dict(store["_writes"])["models.ollama_url"] == "http://ollama.local:11434"
    assert probed == ["http://ollama.local:11434"]
    out = capsys.readouterr().out
    assert "✓ Ollama reachable at http://ollama.local:11434" in out
    # reachable → the local-LLM question defaults to yes
    assert dict(store["_writes"])["features.curiosity_loop"] == "true"


def test_config_wizard_routes_to_the_wizard(store, monkeypatch):
    seen: list[int] = []
    monkeypatch.setattr(config_cli, "wizard", lambda *, fd=0: seen.append(fd) or 0)
    assert config_cli.main(["wizard"]) == 0
    assert seen == [0]


# ── wiki setup: the wizard, then the hooks step ──────────────────────────


def test_setup_runs_the_hooks_installer_in_process_on_yes(store, monkeypatch, capsys):
    """Hooks are Python since M034-S03-T05: the installer runs in-process, on setup's fd."""
    seen: list[int] = []
    monkeypatch.setattr(setup_cli.hooks_cli, "install", lambda *, fd=0: seen.append(fd) or 0)
    fd = _fd("\n" * 6, "y\n")
    assert setup_cli.setup(fd=fd) == 0
    assert seen == [fd]


def test_setup_skips_the_hooks_on_no(store, monkeypatch, capsys):
    monkeypatch.setattr(
        setup_cli.hooks_cli, "install", lambda **_: pytest.fail("no hooks install on no")
    )
    assert setup_cli.setup(fd=_fd("\n" * 6, "n\n")) == 0
    assert "Skipped hook install — run `wiki hooks install` later." in capsys.readouterr().out


def test_setup_returns_the_hooks_installers_exit_code(store, monkeypatch):
    monkeypatch.setattr(setup_cli.hooks_cli, "install", lambda **_: 3)
    assert setup_cli.setup(fd=_fd("\n" * 6, "y\n")) == 3
