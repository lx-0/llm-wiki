"""`wiki config` — read and change `.wiki/config.yaml` (M034-S02-T02; was the bash `cmd_config`
with `lib/config.sh`'s editor and status, held to the bash oracle's `config-*` goldens).

- `get KEY` / `set KEY VALUE` / `keys` / `path` run `core.config`'s own CLI, with the bash's
  argument-count checks in front.
- `status` prints the summary rows and probes Ollama.
- bare `wiki config` is the interactive editor: a section, then a key, then a value — on
  `core/console`'s line-based prompts, so it works the same piped (the oracle drives it so).

`wiki config wizard` is still the bash wizard until S02-T03; the `wiki` entry routes it.
Plain output goes to stdout like the bash `ok` / `warn` / `info` lines; prompts go to stderr.
"""

from __future__ import annotations

import sys

import httpx

from cli_help import H_CONFIG
from core import config as core_config
from core.console import print_error, read_line, select_one

SECTIONS = [
    "models",
    "scheduling",
    "features",
    "piggybacks",
    "limits",
    "graph_view",
    "skills",
    "exit",
]
# The rows of `wiki config status` (and of `wiki status`, which calls it).
STATUS_KEYS = [
    ("compile_model", "models.compile_model"),
    ("ollama_url", "models.ollama_url"),
    ("compile_after_hour", "scheduling.compile_after_hour"),
    ("features.curiosity_loop", "features.curiosity_loop"),
    ("features.vision_screenshots", "features.vision_screenshots"),
    ("features.procmail_execution", "features.procmail_execution"),
    ("skills.global_install", "skills.global_install"),
]

# stdout lines are styled by stdout's terminal state (the bash's `[[ -t 1 ]]`)
_TTY = sys.stdout.isatty()
_BOLD, _DIM, _RESET = ("\033[1m", "\033[2m", "\033[0m") if _TTY else ("", "", "")
_GREEN, _YELLOW, _BLUE = ("\033[32m", "\033[33m", "\033[34m") if _TTY else ("", "", "")


def _banner(title: str, subtitle: str | None = None) -> None:
    print(f"{_BOLD}{title}{_RESET}")
    if subtitle:
        print(f"{_DIM}{subtitle}{_RESET}")
    print()


def _ok(message: str) -> None:
    print(f"{_GREEN}✓ {message}{_RESET}")


def _warn(message: str) -> None:
    print(f"{_YELLOW}! {message}{_RESET}")


def _info(message: str) -> None:
    print(f"{_BLUE}{message}{_RESET}")


def _prompt(text: str) -> None:
    sys.stderr.write(text)
    sys.stderr.flush()


# The store, as three seams the tests replace: reads go to config.yaml afresh each time (the
# editor writes between them, and core.config.CONFIG is read once per process); writes go
# through core.config's own `set`, backups and type coercion included.


def _keys() -> list[str]:
    return core_config.keys(core_config.load())


def _value(key: str) -> str:
    try:
        return str(core_config.value_of(key, core_config.load()))
    except KeyError:
        return "?"


def _set(key: str, value: str) -> bool:
    return core_config._cli(["set", key, value]) == 0


def _ollama_reachable(url: str) -> bool:
    """`GET {url}/api/tags` within 3 s and a 2xx answer — the bash `curl -sSf --max-time 3`."""
    try:
        httpx.get(f"{url.rstrip('/')}/api/tags", timeout=3).raise_for_status()
    except (httpx.HTTPError, httpx.InvalidURL):
        return False
    return True


def status() -> int:
    _banner("wiki config — status")
    print(f"{'config.yaml':<40} {core_config.CONFIG_FILE}")
    for label, key in STATUS_KEYS:
        print(f"{label:<40} {_value(key)}")
    print()
    url = _value("models.ollama_url")
    if _ollama_reachable(url):
        _ok("Ollama reachable")
    else:
        _warn(f"Ollama unreachable at {url}")
    return 0


def _edit_one(section: str, fd: int) -> None:
    """One pass through a section: list its keys with their values, pick one, set it."""
    section_keys = [k for k in _keys() if k.startswith(f"{section}.")]
    if not section_keys:
        _warn(f"No keys in {section}.")
        return
    print()
    print(f"{_DIM}Current values in {section}:{_RESET}")
    for i, key in enumerate(section_keys, 1):
        print(f"  {i}) {key:<50} = {_value(key)}")
    _prompt(f"Pick a key to edit {_DIM}(number, or 'b' to go back){_RESET}: ")
    pick = read_line(fd) or ""
    if pick in ("b", ""):
        return
    if not pick.isascii() or not pick.isdigit():
        _warn("Invalid pick.")
        return
    if not 1 <= int(pick) <= len(section_keys):
        _warn("Out of range.")
        return
    key = section_keys[int(pick) - 1]
    current = _value(key)
    print()
    _prompt(f"Set {key} {_DIM}[current: {current}]{_RESET}: ")
    new = read_line(fd) or ""
    if not new:
        _info("skipped")
        return
    if _set(key, new):
        _ok(f"{key} = {new}")


def edit(*, fd: int = 0) -> int:
    """Bare `wiki config`: pick a section, then a key, then its new value; Enter skips."""
    _banner("wiki config — edit", "Pick a section, then a key. Enter on a key skips it.")
    while True:
        print()
        sys.stdout.flush()
        section = select_one("Section", SECTIONS, default=len(SECTIONS), fd=fd)
        if section == "exit":
            break
        _edit_one(section, fd)
    print()
    _ok("Done.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        return edit()
    command, rest = args[0], args[1:]
    if command == "get":
        if len(rest) != 1:
            print_error("usage: wiki config get KEY")
            return 1
        return core_config._cli(["get", rest[0]])
    if command == "set":
        if len(rest) != 2:
            print_error("usage: wiki config set KEY VALUE")
            return 1
        return core_config._cli(["set", *rest])
    if command in ("keys", "path"):
        return core_config._cli([command])
    if command == "status":
        return status()
    print_error(f"unknown: wiki config {command}")
    print(H_CONFIG)
    return 1


if __name__ == "__main__":
    sys.exit(main())
