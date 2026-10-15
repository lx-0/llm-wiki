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
import os
import re
import shutil
import socket
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "oracle"
BASH_GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "bash"
UPDATE_FLAG = "--snapshot-update"
UPDATE_HINT = f"uv run pytest tests/test_oracle_payloads.py tests/test_bash_oracle.py {UPDATE_FLAG}"

# A compile that happened long ago: every fixture source is newer, the compile state is
# stalled, and nothing depends on the day the test runs.
LAST_COMPILE_ISO = "2026-01-01T09:00:00"

_DIGITS = re.compile(r"\d+")


# ── fixture vault ─────────────────────────────────────────────────────────────


def _article(title: str, type_: str, body: str, **extra: str) -> str:
    lines = [
        f"title: {title}",
        f"type: {type_}",
        "summary: fixture article for the behaviour oracle",
    ]
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
        (
            ("folder-deep-scan", "pending"),
            ("email-deep-scan", "pending"),
            ("email-deep-scan", "done"),
        ),
        start=1,
    ):
        (raw / "requests" / f"request-{n:04d}.json").write_text(
            json.dumps({"type": type_, "status": status, "topic": "fixture"}), encoding="utf-8"
        )
    (raw / "suggestions").mkdir()

    (vault / "inbox").mkdir()
    (vault / "inbox" / "dropped.html").write_text(
        "<html><body>dropped</body></html>", encoding="utf-8"
    )
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
    # Import-before-patch: several collectors freeze `Path.home()`-derived constants at
    # first import (scan_screenshots.SCREENSHOTS_DIR, scan_browser.CHROME_PROFILE). If the
    # oracle were the first importer, those constants would be born under the scratch HOME
    # and OUTLIVE this test's monkeypatch — later tests would see a vanished tmp path.
    # Importing the package here, before HOME changes, keeps the module-level values real;
    # the explicit setattr below is what this test sees, and monkeypatch restores it.
    import collectors  # noqa: F401
    import doctor
    import menu_context
    from collectors import scan_screenshots
    from core import health

    from ._health_paths import patch_health_path

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
        (doctor, {"ROOT_DIR": vault, "WIKI_DIR": wiki}),
    ]
    for module, names in constants:
        for name, value in names.items():
            monkeypatch.setattr(module, name, value)
    # core.health is a package: each check reads the vault paths in its own submodule, so
    # they are patched where they are read (tests/_health_paths.py) — a patch on the
    # package would raise, the package binds none of them.
    for name, value in {
        "ROOT_DIR": vault,
        "WIKI_DIR": wiki,
        "KNOWLEDGE_DIR": knowledge,
        "LOGS_DIR": wiki / "logs",
        "STATE_DIR": wiki / "state",
        "STATE_FILE": wiki / "state" / "state.json",
    }.items():
        patch_health_path(monkeypatch, name, value)

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
    monkeypatch.setattr(health.engine, "_effective_env_dir", lambda: env_dir)
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


def doctor_quick_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> dict:
    import doctor

    monkeypatch.setattr(sys, "argv", ["doctor", "--quick", "--json"])
    doctor.main()  # exit code mirrors severity; the payload is what the oracle freezes
    return json.loads(capsys.readouterr().out)


def help_text() -> str:
    import cli

    return cli.render_help() + "\n"


# ── the bash layer (M034): the real `wiki` against an engine copy ─────────────
#
# M034 moves the bash-owned commands into Python. Each port is measured against what the
# bash did, recorded BEFORE the port: the real `wiki` runs out of a copy of the engine in
# the fixture vault, under a scratch HOME, through a `uv` shim. Subprocesses, not
# in-process calls, so the bash → Python hop is the one an operator gets.

# What a vault's `.wiki/` holds that the bash and the Python behind it read. Copies, not
# symlinks: `core/paths.py` resolves its own file, so a symlinked `scripts/` would make the
# repo's parent directory the vault.
ENGINE_PARTS = (
    "wiki",
    "lib",
    "scripts",
    "hooks",
    "prompts",
    "skills",
    "templates",
    "config.example.yaml",
    "pyproject.toml",
    "uv.lock",
    ".gitignore",
)
_FIXED_GIT_ENV = {
    "GIT_AUTHOR_NAME": "oracle",
    "GIT_AUTHOR_EMAIL": "oracle@example.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T09:00:00+00:00",
    "GIT_COMMITTER_NAME": "oracle",
    "GIT_COMMITTER_EMAIL": "oracle@example.invalid",
    "GIT_COMMITTER_DATE": "2026-01-01T09:00:00+00:00",
}
ORACLE_ORIGIN = "https://example.invalid/llm-wiki.git"


def build_engine_template(wiki: Path) -> Path:
    """Copy the engine's runtime parts into ``wiki`` as one git commit with a fixed origin
    (so `wiki version` reports a checkout). Build once, then `install_engine` it into each
    fixture vault — copying a finished checkout is cheaper than re-committing per case."""
    wiki.mkdir(parents=True, exist_ok=True)
    for part in ENGINE_PARTS:
        src = REPO_ROOT / part
        if src.is_dir():
            shutil.copytree(src, wiki / part, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(src, wiki / part)
    env = {**os.environ, **_FIXED_GIT_ENV}
    for argv in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        ["commit", "-q", "-m", "oracle engine copy"],
        ["remote", "add", "origin", ORACLE_ORIGIN],
    ):
        subprocess.run(["git", "-C", str(wiki), *argv], check=True, env=env)
    return wiki


def install_engine(vault: Path, template: Path) -> Path:
    """Put a built engine template into ``vault/.wiki/`` (next to the fixture's state and
    config) and give the vault the `.obsidian/` the bash vault guard demands."""
    wiki = vault / ".wiki"
    shutil.copytree(template, wiki, symlinks=True, dirs_exist_ok=True)
    (vault / ".obsidian").mkdir(exist_ok=True)
    return wiki


def build_engine_copy(vault: Path) -> Path:
    """Template + install in one step, for a single vault. Returns the engine dir."""
    template = build_engine_template(vault.parent / f"{vault.name}-engine-template")
    return install_engine(vault, template)


def write_uv_shim(bin_dir: Path) -> Path:
    """A `uv` first on PATH: `uv run [flags] python ARGS` execs this venv's python with
    ARGS. Nothing is synced or created, so no oracle run can mutate an environment, and
    the bash still makes its own hop into Python."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "uv"
    shim.write_text(
        "#!/bin/sh\n"
        'while [ "$#" -gt 0 ] && [ "$1" != python ]; do shift; done\n'
        '[ "$#" -gt 0 ] && shift\n'
        f'exec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return shim


def run_wiki(
    vault: Path, home: Path, bin_dir: Path, *args: str, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the engine copy's `wiki` the way a non-interactive caller does: no TTY, a
    scratch HOME, PATH = the uv shim + the system dirs (where `jq` and `git` live on macOS
    and on the CI runner). ``stdin`` scripts the answers to the bash's line-based prompts
    (`lib/ui.sh` reads with `read -r`, and EOF takes the default); without it stdin is
    /dev/null."""
    env = {
        "PATH": os.pathsep.join((str(bin_dir), "/usr/bin", "/bin")),
        "HOME": str(home),
        "PYTHONUTF8": "1",
    }
    return subprocess.run(
        [str(vault / ".wiki" / "wiki"), *args],
        cwd=vault,
        env=env,
        input=stdin,
        stdin=None if stdin is not None else subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


# What a mutating command's effect is measured over: everything under the vault and under
# HOME, minus the engine copy's runtime parts and git dir (the code, not its effect) and the
# logs (timestamps only).
NOT_AN_EFFECT = frozenset({*(f".wiki/{part}" for part in ENGINE_PARTS), ".wiki/.git", ".wiki/logs"})
_INLINE_LIMIT = 8192


def tree_manifest(root: Path, *, skip: frozenset[str] = frozenset()) -> dict[str, str]:
    """``{relative path: description}`` for every file and symlink under ``root``. A
    symlink is described by its target, a small UTF-8 file by its content, anything else by
    its size and sha256. Paths under a ``skip`` prefix are left out."""
    import hashlib

    manifest: dict[str, str] = {}
    if not root.exists():
        return manifest
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if any(rel == s or rel.startswith(s + "/") for s in skip):
            continue
        if path.is_symlink():
            manifest[rel] = f"-> {os.readlink(path)}"
        elif path.is_file():
            data = path.read_bytes()
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = None
            if text is not None and len(data) <= _INLINE_LIMIT:
                manifest[rel] = text
            else:
                manifest[rel] = (
                    f"<{len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()[:16]}>"
                )
    return manifest


def manifest_diff(
    before: dict[str, str],
    after: dict[str, str],
    label: str,
    normalise: Callable[[str], str] = lambda text: text,
) -> str:
    """The change between two manifests of one tree, as text: added entries in full,
    changed text as a unified diff, removed entries by name. ``label`` prefixes the paths
    (e.g. ``<VAULT>``). Entries are compared after ``normalise``, so a file whose only
    difference is a refreshed timestamp is no change."""
    before = {k: normalise(v) for k, v in before.items()}
    after = {k: normalise(v) for k, v in after.items()}
    out: list[str] = []
    for rel in sorted(after.keys() - before.keys()):
        out.append(f"+ {label}/{rel}\n{_indent(after[rel])}")
    for rel in sorted(k for k in after.keys() & before.keys() if after[k] != before[k]):
        diff = difflib.unified_diff(
            before[rel].splitlines(keepends=True),
            after[rel].splitlines(keepends=True),
            lineterm="",
            n=1,
        )
        body = "".join(line if line.endswith("\n") else line + "\n" for line in list(diff)[2:])
        out.append(f"~ {label}/{rel}\n{_indent(body)}")
    out.extend(f"- {label}/{rel}\n" for rel in sorted(before.keys() - after.keys()))
    return "".join(out)


def _indent(text: str) -> str:
    if not text.endswith("\n"):
        text += "\n"
    return "".join(f"    {line}" for line in text.splitlines(keepends=True))


# Hex revisions only when they carry a digit, so English words made of a–f survive.
_REVISION = re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b")
_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?"
)
_AGE = re.compile(r"\b\d+(\s*)(seconds?|minutes?|hours?|days?|weeks?|months?|years?) ago\b")
# Compact stamps in file names: `lib/common.sh:backup_file`'s `<file>.bak.YYYYmmdd-HHMMSS`
# and `core/config_backup`'s `state/config-backups/config-YYYYmmdd-HHMMSS-ffffff.yaml`.
# Before the revision rule, which would otherwise take the date half for a hash.
_COMPACT_STAMP = re.compile(r"\b\d{8}-\d{6}(?:-\d{6})?\b")


def normalise_text(text: str, *, placeholders: dict[str, str]) -> str:
    """The volatile fragments of command output: the scratch paths (longest first), compact
    stamps → <STAMP>, git revisions → <REV>, wall-clock timestamps → <TS>, relative ages →
    "N <unit> ago"."""
    for literal, token in sorted(placeholders.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(literal, token)
    text = _COMPACT_STAMP.sub("<STAMP>", text)
    text = _TIMESTAMP.sub("<TS>", text)
    text = _REVISION.sub("<REV>", text)
    return _AGE.sub(lambda m: f"N{m.group(1)}{m.group(2)} ago", text)


def render_run(
    args: tuple[str, ...], run: subprocess.CompletedProcess[str], placeholders: dict[str, str]
) -> str:
    """One recorded invocation: the command, its exit code, stdout and stderr. A stream
    that does not end in a newline (a prompt waiting for input) gets one, so the next
    section marker starts its own line."""
    text = (
        f"$ wiki {' '.join(args)}".rstrip()
        + f"\nexit: {run.returncode}\n--- stdout ---\n{_line_end(run.stdout)}"
        + f"--- stderr ---\n{_line_end(run.stderr)}"
    )
    return normalise_text(text, placeholders=placeholders)


def _line_end(stream: str) -> str:
    return stream if not stream or stream.endswith("\n") else stream + "\n"


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


def diff_against_golden(name: str, text: str, golden_dir: Path = GOLDEN_DIR) -> str | None:
    """None when ``text`` equals the committed golden; otherwise a unified diff (or the
    reason there is nothing to compare against)."""
    path = golden_dir / name
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


def assert_matches_golden(
    request: pytest.FixtureRequest, name: str, text: str, golden_dir: Path = GOLDEN_DIR
) -> None:
    path = golden_dir / name
    if request.config.getoption(UPDATE_FLAG):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    problem = diff_against_golden(name, text, golden_dir)
    if problem is not None:
        pytest.fail(
            f"{name}: {problem}\n"
            f"If this change is intended, regenerate with `{UPDATE_HINT}` and commit the "
            "golden together with the change that caused it.",
            pytrace=False,
        )
