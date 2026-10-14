"""Manual flush must explain consumption and reject invalid calls before extraction."""

import asyncio

import pytest

import cli
import flush


@pytest.mark.parametrize("args,exit_code", [([], 2), (["--help"], 0)])
def test_manual_help_never_dispatches(monkeypatch, capsys, args, exit_code):
    def unexpected(*args):
        pytest.fail("help must not invoke the flush handler")

    monkeypatch.setattr(cli, "_run_child", unexpected)
    assert cli.run_command(cli.BY_NAME["flush"], args) == exit_code
    text = capsys.readouterr().out
    for important in ("context_file.md", "session_id", "deleted", "LLM cost", "disposable"):
        assert important in text


@pytest.mark.parametrize("suffix", [[], ["id", "unexpected-extra-argument"]])
def test_bad_arguments_preserve_input_before_any_work(tmp_path, monkeypatch, suffix):
    context = tmp_path / "original.md"
    context.write_text("Keep me")
    monkeypatch.setattr(flush.sys, "argv", ["flush.py", str(context), *suffix])
    monkeypatch.setattr(flush, "_is_duplicate", lambda _: pytest.fail("no work before validation"))
    with pytest.raises(SystemExit) as exc:
        asyncio.run(flush.main())
    assert exc.value.code == 2
    assert context.read_text() == "Keep me"


def test_hook_positional_arguments_remain_compatible(tmp_path):
    context = tmp_path / "staged-context.md"
    args = flush._parse_args([str(context), "session-123"])
    assert args.context_file == context
    assert args.session_id == "session-123"


def test_direct_bare_handler_shows_full_help(capsys):
    with pytest.raises(SystemExit) as exc:
        flush._parse_args([])
    assert exc.value.code == 2
    assert "disposable" in capsys.readouterr().err


def test_record_flush_merges_with_a_concurrent_hook(tmp_path, monkeypatch):
    """M033-S03-T05: parallel SessionEnd hooks write last-flush.json at once. A session
    another hook records while this one takes its stamp survives this one's write —
    the old load → stamp → whole-dict save of the stale snapshot dropped it."""
    import json
    import time

    last_flush = tmp_path / "last-flush.json"
    monkeypatch.setattr(flush, "LAST_FLUSH_FILE", last_flush)

    class _TimeWhileAnotherHookLands:
        """`time` stand-in: the first `time()` call is another hook landing its session."""

        def __init__(self):
            self.landed = False

        def time(self):
            if not self.landed:
                self.landed = True
                last_flush.write_text(json.dumps({"other-session": time.time()}), encoding="utf-8")
            return time.time()

        def __getattr__(self, name):
            return getattr(time, name)

    monkeypatch.setattr(flush, "time", _TimeWhileAnotherHookLands())

    flush._record_flush("this-session")

    on_disk = json.loads(last_flush.read_text(encoding="utf-8"))
    assert "other-session" in on_disk, "the concurrent hook's session was lost"
    assert "this-session" in on_disk
    assert flush._is_duplicate("other-session") is True
