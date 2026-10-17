"""The bridge LaunchAgent template, as an operator installs it.

launchd starts an agent with PATH=/usr/bin:/bin:/usr/sbin:/sbin — no uv — and the bootstrap
dies "uv not found" before `wiki bridge sync` runs, so the plist names uv's directory. The
bootstrap finds its engine and vault from its own path; the agent runs `<vault>/.wiki/wiki`
(M034-S06-T07).
"""

from __future__ import annotations

import plistlib
import re
from pathlib import Path

TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "templates"
    / ".launchd"
    / "com.llm-wiki.bridge.plist.template"
)


def _parts() -> tuple[str, str]:
    comment, body = TEMPLATE.read_text(encoding="utf-8").split("-->", 1)
    return comment, body


def test_the_agent_puts_uv_on_its_path():
    env = plistlib.loads(TEMPLATE.read_bytes())["EnvironmentVariables"]
    entries = env["PATH"].split(":")
    assert entries[0] == "__UV_DIR__"
    assert "/usr/bin" in entries and "/bin" in entries


def test_every_placeholder_is_explained_in_the_install_steps():
    comment, body = _parts()
    placeholders = set(re.findall(r"__[A-Z_]+__", body))
    assert placeholders, "the template has placeholders to fill"
    assert sorted(p for p in placeholders if p not in comment) == []


def test_the_example_binary_is_the_vaults_engine():
    comment, _body = _parts()
    assert "/.wiki/wiki" in comment
