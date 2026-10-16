"""The line-based prompt helpers on `core/console` (M034-S02-T01) — the Python counterpart of
the bash `lib/ui.sh` (deleted in M034-S05-T03) that the config / setup / hooks / update ports
use.

Answers are scripted through an `os.pipe()`, the way the bash oracle pipes them into `wiki`.
They are read byte by byte, never through `sys.stdin`: on a pipe, `sys.stdin.readline()`
buffers ahead and swallows the answers a child started after the prompt must read
(`wiki setup` → `wiki hooks install`, M034 reassessment after S01).
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from core import console

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def answers() -> Iterator[Callable[..., int]]:
    """``answers("y\\n", "x\\n")`` → a read fd holding those lines, then EOF."""
    fds: list[int] = []

    def make(*lines: str) -> int:
        r, w = os.pipe()
        os.write(w, "".join(lines).encode())
        os.close(w)
        fds.append(r)
        return r

    yield make
    for fd in fds:
        with contextlib.suppress(OSError):
            os.close(fd)


# ── read_line ─────────────────────────────────────────────────────────────


def test_read_line_reads_one_line_and_leaves_the_rest(answers):
    fd = answers("first\n", "second\n")
    assert console.read_line(fd) == "first"
    assert os.read(fd, 100) == b"second\n"  # nothing read ahead


def test_read_line_at_eof(answers):
    assert console.read_line(answers("no newline")) == "no newline"
    assert console.read_line(answers()) is None


# ── confirm ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("line", "default", "expected"),
    [
        ("y\n", True, True),
        ("n\n", True, False),
        ("J\n", False, True),  # German "ja"
        ("yes\n", False, True),
        ("x\n", True, False),  # anything not y/j is no, as in bash
        ("\n", True, True),
        ("\n", False, False),
        ("", True, True),  # EOF takes the default
    ],
)
def test_confirm(answers, line, default, expected):
    out = io.StringIO()
    assert console.confirm("Install?", default=default, fd=answers(line), out=out) is expected
    assert out.getvalue() == f"Install? {'[Y/n]' if default else '[y/N]'} "


def test_a_child_after_a_prompt_reads_its_own_answer(answers):
    """The load-bearing one: Python takes exactly its line; the child gets the next."""
    fd = answers("y\n", "second-answer\n")
    assert console.confirm("Install?", fd=fd, out=io.StringIO()) is True
    child = subprocess.run(
        ["sh", "-c", 'read -r x; printf "%s" "$x"'],
        stdin=fd,
        capture_output=True,
        text=True,
        check=True,
    )
    assert child.stdout == "second-answer"


# ── ask ───────────────────────────────────────────────────────────────────


def test_ask_returns_the_line_or_the_default(answers):
    out = io.StringIO()
    assert console.ask("URL", default="http://x", fd=answers("http://y\n"), out=out) == "http://y"
    assert out.getvalue() == "URL [http://x]: "
    assert console.ask("URL", default="http://x", fd=answers("\n"), out=io.StringIO()) == "http://x"
    assert console.ask("Name", fd=answers(""), out=io.StringIO()) == ""


def test_ask_repeats_until_the_validator_accepts(answers):
    out = io.StringIO()
    value = console.ask(
        "Hour", default="18", validate=str.isdigit, fd=answers("x\n", "20\n"), out=out
    )
    assert value == "20"
    assert out.getvalue() == "Hour [18]: Hour [18]: "


def test_ask_does_not_loop_at_eof(answers):
    """No input means no further answer will come: the default, not an endless re-ask."""
    assert (
        console.ask("Hour", default="x", validate=str.isdigit, fd=answers(), out=io.StringIO())
        == "x"
    )


# ── select_one / select_many ──────────────────────────────────────────────

OPTIONS = ["claude", "codex", "gemini"]


@pytest.mark.parametrize(
    ("line", "expected"),
    [("3\n", "gemini"), ("\n", "codex"), ("9\n", "codex"), ("x\n", "codex"), ("", "codex")],
)
def test_select_one(answers, line, expected):
    assert (
        console.select_one("Agent", OPTIONS, default=2, fd=answers(line), out=io.StringIO())
        == expected
    )


def test_select_one_renders_the_numbered_list(answers):
    out = io.StringIO()
    console.select_one("Agent", OPTIONS, default=2, fd=answers("\n"), out=out)
    assert out.getvalue() == "    1) claude\n  * 2) codex\n    3) gemini\nAgent [2]: "


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("\n", ["claude", "gemini"]),
        ("", ["claude", "gemini"]),
        ("2 3\n", ["codex", "gemini"]),
        ("1 x 9 2\n", ["claude", "codex"]),  # junk and out-of-range tokens are skipped
        ("x\n", []),
    ],
)
def test_select_many(answers, line, expected):
    chosen = console.select_many(
        "Agents", OPTIONS, defaults=["claude", "gemini"], fd=answers(line), out=io.StringIO()
    )
    assert chosen == expected


def test_select_many_renders_the_defaults(answers):
    out = io.StringIO()
    console.select_many("Agents", OPTIONS, defaults=["codex"], fd=answers("\n"), out=out)
    assert out.getvalue() == (
        "    1) claude\n  * 2) codex\n    3) gemini\n"
        "Agents (space-separated numbers, Enter for defaults marked *): "
    )


# ── pause ─────────────────────────────────────────────────────────────────


def test_pause_reads_exactly_one_line(answers):
    fd = answers("\n", "next\n")
    out = io.StringIO()
    console.pause(fd=fd, out=out)
    assert out.getvalue() == "Press Enter to continue "
    assert console.read_line(fd) == "next"


# ── output order ──────────────────────────────────────────────────────────


def test_what_is_printed_before_a_prompt_shows_before_it_on_one_pipe():
    """`wiki hooks install 2>&1 | tee log`: stdout is block-buffered into a pipe and the
    prompt goes to stderr unbuffered, so the status table printed before the agent picker
    came out after it (seen on scratch, M034-S03-T05). A prompt flushes stdout first."""
    script = (
        "import os, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from core import console\n"
        "print('the table')\n"
        "r, w = os.pipe(); os.write(w, b'1\\n'); os.close(w)\n"
        "console.select_one('Install scope', ['user', 'project'], 1, fd=r)\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONUNBUFFERED"}
    out = subprocess.run(
        [sys.executable, "-c", script, str(SCRIPTS)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
        env=env,
    ).stdout
    assert out.index("the table") < out.index("Install scope")
