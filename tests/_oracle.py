"""Behaviour oracle (M033): one deterministic fixture vault and golden snapshots of the
operator-facing payloads — `wiki menu --json` (menu_context), `wiki doctor --quick --json`
and `cli.py help`.

A refactor slice is "byte-identical" when tests/test_oracle_payloads.py runs green without
`--snapshot-update`. An intentional wording change regenerates the goldens in the same
commit, so the change shows up in the diff where a reviewer sees it.

Determinism rules (every one of them is a flake that was reasoned about, not observed):
  * the fixture's "last compile" is a fixed day in the past, so every source counts as
    changed and the compile state reads as stalled on any calendar day;
  * entity pages are either never synthesized or synthesized on that same past day, so
    the dream-overdue count never flips at a cooldown boundary;
  * today's `daily/sessions/<today>.md` is deliberately absent, so "flush missing" is 1
    on every day;
  * HOME, PATH, the API-key env and the interpreter prefix are pinned by
    `patch_engine_paths`, and TCP connects raise, so no check can see the machine;
  * free-text fields are normalised (digits → N, tmp paths → placeholders) because the
    checks humanise ages — "N minutes ago" is stable, "3 minutes ago" is not.
"""

from __future__ import annotations

import difflib
import json
import re
import socket
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "oracle"
UPDATE_FLAG = "--snapshot-update"
UPDATE_HINT = f"uv run pytest tests/test_oracle_payloads.py {UPDATE_FLAG}"

# A compile that happened long ago: every fixture source is newer, the compile state is
# stalled, and nothing depends on the day the test runs.
LAST_COMPILE_ISO = "2026-01-01T09:00:00"

_DIGITS = re.compile(r"\d+")


# ── fixture vault ─────────────────────────────────────────────────────────────


def _article(title: str, type_: str, body: str, **extra: str) -> str:
    lines = [f"title: {title}", f"type: {type_}", "summary: fixture article for the behaviour oracle"]
    lines.extend(f"{key}: {value}" for key, value in extra.items())
    return "---\n" + "\n".join(lines) + "\n---\n\n# " + title + "\n\n" + body + "\n"


def build_fixture_vault(root: Path) -> Path:
    """Write a small, fully deterministic vault under ``root`` and return its path."""
    vault = root / "vault-fixture"
    knowledge = vault / "knowledge"
    for sub in ("concepts", "people", "projects", "areas", "facts", "connections"):
        (knowledge / sub).mkdir(parents=True)
    (knowledge / "concepts" / "local-llms.md").write_text(
        _article("Local LLMs", "concept", "Models that run on the operator's own hardware."),
        encoding="utf-8",
    )
    (knowledge / "concepts" / "behaviour-oracle.md").write_text(
        _article("Behaviour oracle", "concept", "A golden snapshot the refactors must not change."),
        encoding="utf-8",
    )
    # never synthesized → counts as overdue on every day
    (knowledge / "people" / "sam-rivera.md").write_text(
        _article("Sam Rivera", "person", "A persona from the learnability panel."),
        encoding="utf-8",
    )
    # synthesized on the fixed past day → overdue on every day as well
    (knowledge / "projects" / "llm-wiki.md").write_text(
        _article(
            "llm-wiki",
            "project",
            "The engine itself.",
            last_synthesized_at="2026-01-01T09:00:00+00:00",
        ),
        encoding="utf-8",
    )
    (knowledge / "index.md").write_text(
        "# Index\n\n| Article | Summary |\n| --- | --- |\n"
        "| [[concepts/local-llms]] | Models on own hardware |\n"
        "| [[concepts/behaviour-oracle]] | The golden snapshot |\n"
        "| [[people/sam-rivera]] | A persona |\n"
        "| [[projects/llm-wiki]] | The engine |\n",
        encoding="utf-8",
    )

    raw = vault / "raw"
    (raw / "notes").mkdir(parents=True)
    (raw / "notes" / "2026-01-02--a-note.md").write_text(
        "---\ntitle: A note\n---\n\nCaptured after the last compile.\n", encoding="utf-8"
    )
    (raw / "requests").mkdir()
    for n, (type_, status) in enumerate(
        (("folder-deep-scan", "pending"), ("email-deep-scan", "pending"), ("email-deep-scan", "done")),
        start=1,
    ):
        (raw / "requests" / f"request-{n:04d}.json").write_text(
            json.dumps({"type": type_, "status": status, "topic": "fixture"}), encoding="utf-8"
        )
    (raw / "suggestions").mkdir()

    (vault / "inbox").mkdir()
    (vault / "inbox" / "dropped.html").write_text("<html><body>dropped</body></html>", encoding="utf-8")
    (vault / "inbox" / "dropped.md").write_text("# dropped\n", encoding="utf-8")

    (vault / "daily" / "2026-01-02").mkdir(parents=True)
    (vault / "daily" / "2026-01-02.md").write_text("# 2026-01-02\n\nA digest.\n", encoding="utf-8")
    (vault / "daily" / "sessions").mkdir()  # today's file deliberately absent

    wiki = vault / ".wiki"
    for sub in ("state", "logs", "reports", "sessions"):
        (wiki / sub).mkdir(parents=True)
    (wiki / "state" / "state.json").write_text(
        json.dumps({"last_compile": LAST_COMPILE_ISO, "query_count": 3}, indent=2), encoding="utf-8"
    )
    (wiki / "config.yaml").write_text(
        "# fixture config — the engine's dataclass defaults apply\n", encoding="utf-8"
    )
    return vault


def patch_engine_paths(monkeypatch: pytest.MonkeyPatch, vault: Path, scratch: Path) -> Path:
    """Point every consumer module at ``vault`` and pin the environment the quick checks
    look at. Returns the scratch HOME so callers can normalise it away."""
    import doctor
    import menu_context
    import core.health as health

    # Import-before-patch: several collectors freeze `Path.home()`-derived constants at
    # first import (scan_screenshots.SCREENSHOTS_DIR, scan_browser.CHROME_PROFILE). If the
    # oracle were the first importer, those constants would be born under the scratch HOME
    # and OUTLIVE this test's monkeypatch — later tests would see a vanished tmp path.
    # Importing the package here, before HOME changes, keeps the module-level values real;
    # the explicit setattr below is what this test sees, and monkeypatch restores it.
    import collectors  # noqa: F401
    from collectors import scan_screenshots

    wiki = vault / ".wiki"
    knowledge = vault / "knowledge"
    constants: list[tuple[Any, dict[str, Path]]] = [
        (
            menu_context,
            {
                "INBOX_DIR": vault / "inbox",
                "RAW_DIR": vault / "raw",
                "RAW_REQUESTS_DIR": vault / "raw" / "requests",
                "RAW_SUGGESTIONS_DIR": vault / "raw" / "suggestions",
                "DAILY_DIR": vault / "daily",
                "KNOWLEDGE_DIR": knowledge,
                "PEOPLE_DIR": knowledge / "people",
                "PROJECTS_DIR": knowledge / "projects",
                "AREAS_DIR": knowledge / "areas",
                "REPORTS_DIR": wiki / "reports",
                "STATE_FILE": wiki / "state" / "state.json",
            },
        ),
        (
            health,
            {
                "ROOT_DIR": vault,
                "WIKI_DIR": wiki,
                "KNOWLEDGE_DIR": knowledge,
                "LOGS_DIR": wiki / "logs",
                "STATE_DIR": wiki / "state",
                "STATE_FILE": wiki / "state" / "state.json",
            },
        ),
        (doctor, {"ROOT_DIR": vault, "WIKI_DIR": wiki}),
    ]
    for module, names in constants:
        for name, value in names.items():
            monkeypatch.setattr(module, name, value)

    home = scratch / "home"
    bin_dir = scratch / "bin"
    env_dir = scratch / "env"
    for d in (home, bin_dir, env_dir):
        d.mkdir(parents=True)
    fake_wiki = bin_dir / "wiki"
    fake_wiki.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_wiki.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(bin_dir))
    for var in ("ANTHROPIC_API_KEY", "UV_PROJECT_ENVIRONMENT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(health, "_effective_env_dir", lambda: env_dir)
    monkeypatch.setattr(doctor, "_git_revision", lambda: "<REV>")
    # The piggyback check asks every registered collector `is_configured()`. The
    # screenshots collector answers from that frozen `Path.home() / "Screenshots"` — with
    # the real HOME it depends on the machine, and under pytest on which test imported the
    # module first (seen 2026-10-14: present in the full run, absent in isolation). Pin it
    # to the scratch home like everything else.
    monkeypatch.setattr(scan_screenshots, "SCREENSHOTS_DIR", home / "Screenshots")
    # a slow CI runner must not turn the 500 ms home-screen budget into a partial payload
    monkeypatch.setattr(menu_context, "WALL_CLOCK_BUDGET_S", 30.0)

    def _no_network(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("oracle: network disabled")

    monkeypatch.setattr(socket, "create_connection", _no_network)
    return home


# ── payload producers (the real entry points, in-process) ─────────────────────


def menu_payload(capsys: pytest.CaptureFixture[str]) -> dict:
    import menu_context

    assert menu_context.main() == 0
    return json.loads(capsys.readouterr().out)


def doctor_quick_payload(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> dict:
    import doctor

    monkeypatch.setattr(sys, "argv", ["doctor", "--quick", "--json"])
    doctor.main()  # exit code mirrors severity; the payload is what the oracle freezes
    return json.loads(capsys.readouterr().out)


def help_text() -> str:
    import cli

    return cli.render_help() + "\n"


# ── normalisation + golden comparison ─────────────────────────────────────────


def normalise(value: Any, *, placeholders: dict[str, str]) -> Any:
    """Replace machine- and clock-dependent fragments so two runs compare equal.
    ``placeholders`` maps a literal path to its token (longest first)."""
    ordered = sorted(placeholders.items(), key=lambda kv: -len(kv[0]))

    def text(s: str) -> str:
        for literal, token in ordered:
            s = s.replace(literal, token)
        return _DIGITS.sub("N", s)

    def walk(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: ("<AGO>" if k == "last_compile_ago" else walk(x)) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, str):
            return text(v)
        return v

    return walk(value)


def dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def diff_against_golden(name: str, text: str) -> str | None:
    """None when ``text`` equals the committed golden; otherwise a unified diff (or the
    reason there is nothing to compare against)."""
    path = GOLDEN_DIR / name
    if not path.exists():
        return f"golden {path.relative_to(REPO_ROOT)} is missing"
    expected = path.read_text(encoding="utf-8")
    if expected == text:
        return None
    return "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            text.splitlines(keepends=True),
            fromfile=f"golden/{name}",
            tofile="current",
        )
    )


def assert_matches_golden(request: pytest.FixtureRequest, name: str, text: str) -> None:
    path = GOLDEN_DIR / name
    if request.config.getoption(UPDATE_FLAG):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    problem = diff_against_golden(name, text)
    if problem is not None:
        pytest.fail(
            f"{name}: {problem}\n"
            f"If this change is intended, regenerate with `{UPDATE_HINT}` and commit the "
            "golden together with the change that caused it.",
            pytrace=False,
        )
