"""`wiki config` — read and change `.wiki/config.yaml` (M034-S02-T02; was the bash `cmd_config`
with `lib/config.sh`'s editor and status, held to the bash oracle's `config-*` goldens).

- `get KEY` / `set KEY VALUE` / `keys` / `path` run `core.config`'s own CLI, with the bash's
  argument-count checks in front.
- `status` prints the summary rows and probes Ollama.
- bare `wiki config` is the interactive editor: a section, then a key, then a value — on
  `core/console`'s line-based prompts, so it works the same piped (the oracle drives it so).
- `wizard` is the six-question first-run wizard (S02-T03; `wiki setup` runs it too, then the
  hooks step — `setup_cli.py`).

Plain output goes to stdout like the bash `ok` / `warn` / `info` lines; prompts and the
validators' complaints go to stderr.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable

import httpx

from cli_help import H_CONFIG
from core import config as core_config
from core.console import ask, confirm, print_error, read_line, select_one
from core.console import banner as _banner
from core.console import info as _info
from core.console import ok as _ok
from core.console import warn as _warn

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

# The dim and yellow pieces inside prompts follow stdout's terminal state, as the bash's did
# (`[[ -t 1 ]]`); the status lines are core/console's ok / warn / info / banner.
_TTY = sys.stdout.isatty()
_DIM, _YELLOW, _RESET = ("\033[2m", "\033[33m", "\033[0m") if _TTY else ("", "", "")


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


# ── The setup wizard (`wiki config wizard`; `wiki setup` runs it before the hooks step) ──

MODELS = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5"]
_HOUR = re.compile(r"[0-9]|1[0-9]|2[0-3]")


def _complain(message: str) -> None:
    """A validator's complaint, on stderr beside the prompt it answers. In the bash it went
    to stdout inside `$(ask …)`, which captured it into the answer (fixed in 0.7.10)."""
    print(f"{_YELLOW}! {message}{_RESET}", file=sys.stderr)


def _valid_url(value: str) -> bool:
    if re.match(r"https?://", value):
        return True
    _complain("Must start with http:// or https://")
    return False


def _valid_hour(value: str) -> bool:
    if _HOUR.fullmatch(value):
        return True
    _complain("Hour must be 0–23")
    return False


def _ask(prompt: str, current: str, validate: Callable[[str], bool], fd: int) -> str:
    sys.stdout.flush()
    return ask(prompt, default=current, validate=validate, fd=fd)


def _yes(prompt: str, default: bool, fd: int) -> bool:
    sys.stdout.flush()
    return confirm(prompt, default=default, fd=fd)


def _switch(key: str, on: bool) -> None:
    """The three switches are written on every run, as the bash wrote them."""
    _set(key, "true" if on else "false")


def _ask_ollama(fd: int) -> bool:
    """Question 1: the Ollama URL, probed. Returns whether it answered."""
    current = _value("models.ollama_url")
    url = _ask("Ollama base URL", current, _valid_url, fd)
    if url != current:
        _set("models.ollama_url", url)
    if _ollama_reachable(url):
        _ok(f"Ollama reachable at {url}")
        return True
    _warn(f"Ollama NOT reachable at {url} — local-LLM features will fail.")
    return False


def _ask_model_and_hour(fd: int) -> None:
    """Questions 2 and 3: the compile model and the auto-compile hour."""
    current_model = _value("models.compile_model")
    _info("Compile model — Claude tier for compile.py and retry_failed_flushes.py")
    default = MODELS.index(current_model) + 1 if current_model in MODELS else 1
    sys.stdout.flush()
    model = select_one("Pick", MODELS, default=default, fd=fd)
    if model != current_model:
        _set("models.compile_model", model)
    print()
    current_hour = _value("scheduling.compile_after_hour")
    hour = _ask("Auto-compile starts at hour (0-23, local time)", current_hour, _valid_hour, fd)
    if hour != current_hour:
        _set("scheduling.compile_after_hour", hour)


def wizard(*, fd: int = 0) -> int:
    """The six questions worth asking at first run; Enter keeps the current value."""
    _banner("wiki config — setup wizard", "6 questions. Skip with Enter to keep the current value.")
    print()
    ollama_ok = _ask_ollama(fd)
    print()
    _ask_model_and_hour(fd)
    print()
    _info(
        "Procmail execution lets suggestions/cli.py call a webmail-procmail provider API to "
        "apply mail rules server-side."
    )
    _warn(
        "Only enable if you have a procmail-capable webmail account configured "
        "(e.g. All-Inkl kasserver)."
    )
    procmail_on = _value("features.procmail_execution") == "True"
    _switch("features.procmail_execution", _yes("Enable procmail execution?", procmail_on, fd))
    print()
    local = _yes("Enable local-LLM features (curiosity loop + screenshot OCR)?", ollama_ok, fd)
    _switch("features.curiosity_loop", local)
    _switch("features.vision_screenshots", local)
    print()
    _info("Global skill install links the 'use-llm-wiki' skill into ~/.claude/skills/")
    _info("so an agent working in *any* project can discover and query this wiki.")
    global_on = _value("skills.global_install") == "True"
    question = "Make this wiki's use-llm-wiki skill globally available?"
    _switch("skills.global_install", _yes(question, global_on, fd))
    print()
    _ok(f"Wizard complete. Config written to {core_config.CONFIG_FILE}.")
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
    if command == "wizard":
        return wizard()
    print_error(f"unknown: wiki config {command}")
    print(H_CONFIG)
    return 1


if __name__ == "__main__":
    sys.exit(main())
