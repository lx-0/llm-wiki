"""Generic agent-task runner.

Reads `prompts/agents/<id>.md`, parses the task spec, spawns Claude Agent SDK
with declared model + tools + permissions, persists the result to a log,
and records the run timestamp in state/agent-runs.json on success.

Usage:
    uv run python agent_task.py <id>                         # run task
    uv run python agent_task.py <id> --dry-run               # show resolved spec
    uv run python agent_task.py <id> --var key=value         # body substitution
    uv run python agent_task.py --list                       # enumerate tasks
"""

import os
os.environ["CLAUDE_INVOKED_BY"] = "agent_task"

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path


from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    query,
)

import time

from core.agent_spec import AgentSpec, SpecError, list_specs, parse_spec
from core.paths import AGENT_SPECS_DIR, LOGS_DIR, STATE_DIR
from core.utils import now_iso, today_iso
from core.config import CONFIG  # noqa: E402
from core.sdk_helpers import StderrCapture, log_sdk_failure  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("agent-task")


def _resolve_model(spec: AgentSpec) -> str:
    return spec.model or CONFIG.models.compile_model


def _bake_vars(extra_vars: dict[str, str]) -> dict[str, str]:
    """Built-in vars all agent prompts get, plus operator overrides."""
    return {
        "today": today_iso(),
        "now": now_iso(),
        **extra_vars,
    }


AGENT_RUNS_FILE = STATE_DIR / "agent-runs.json"


def _load_agent_runs() -> dict[str, str]:
    try:
        return json.loads(AGENT_RUNS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _last_run_for(agent_id: str) -> str | None:
    return _load_agent_runs().get(agent_id)


def _record_last_run(agent_id: str) -> None:
    """Record an agent's successful-run timestamp in state/agent-runs.json.

    Runtime state lives in the gitignored state/ dir -- NEVER in the tracked
    prompts/agents/<id>.md frontmatter. Writing it into the prompt dirtied the
    vault .wiki/ checkout and broke `wiki update` (git pull) on every run that
    happened since the last update. See KNOWLEDGE.md.
    """
    runs = _load_agent_runs()
    runs[agent_id] = now_iso()
    AGENT_RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    AGENT_RUNS_FILE.write_text(
        json.dumps(runs, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


async def run(spec: AgentSpec, dry_run: bool, extra_vars: dict[str, str]) -> int:
    vars_resolved = _bake_vars(extra_vars)
    rendered = spec.render_body(**vars_resolved)
    model = _resolve_model(spec)

    if dry_run:
        log.info("Resolved agent spec for %r:", spec.id)
        log.info("  title:           %s", spec.title)
        log.info("  model:           %s", model)
        log.info("  allowed_tools:   %s", spec.allowed_tools)
        log.info("  permission_mode: %s", spec.permission_mode)
        log.info("  max_turns:       %d", spec.max_turns)
        log.info("  cwd:             %s -> %s", spec.cwd, spec.cwd_path())
        log.info("  last_run:        %s", _last_run_for(spec.id) or "—")
        if spec.button:
            log.info(
                "  button:          %s (style=%s, shell_id=%s)",
                spec.button.label, spec.button.style, spec.button.shell_command_id,
            )
        log.info("  vars:            %s", vars_resolved)
        log.info("  body (first 200): %s", rendered[:200].replace("\n", " "))
        return 0

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"agent-{spec.id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"

    log.info("Running agent task %r (model=%s, cwd=%s)", spec.id, model, spec.cwd_path())
    total_input_tokens = 0
    total_output_tokens = 0
    result_text = ""

    started = time.time()
    capture = StderrCapture()
    try:
        async for message in query(
            prompt=rendered,
            options=ClaudeAgentOptions(
                max_buffer_size=CONFIG.limits.sdk_max_buffer_size_mb * 1024 * 1024,
                cwd=str(spec.cwd_path()),
                model=model,
                allowed_tools=list(spec.allowed_tools),
                permission_mode=spec.permission_mode,
                max_turns=spec.max_turns,
                system_prompt={"type": "preset", "preset": "claude_code"},
                stderr=capture.callback,
            ),
        ):
            if isinstance(message, AssistantMessage) and message.usage:
                total_input_tokens += message.usage.get("input_tokens", 0)
                total_output_tokens += message.usage.get("output_tokens", 0)
            if isinstance(message, ResultMessage):
                result_text = message.result or ""
    except Exception as exc:
        log_sdk_failure(
            log,
            label=f"agent_task:{spec.id}",
            source=f"agent:{spec.id}",
            model=model,
            input_chars=len(rendered),
            started=started,
            capture=capture,
            exc=exc,
        )
        return 2

    log.info(
        "Agent %r done. Tokens — input: %d, output: %d",
        spec.id, total_input_tokens, total_output_tokens,
    )
    log_file.write_text(
        f"# agent: {spec.id}\n# title: {spec.title}\n# completed: {now_iso()}\n# tokens: input={total_input_tokens} output={total_output_tokens}\n\n{result_text}\n",
        encoding="utf-8",
    )
    log.info("Result logged to %s", log_file)

    _record_last_run(spec.id)
    return 0


def cmd_list() -> int:
    specs: list[AgentSpec] = []
    errors: list[tuple[Path, Exception]] = []
    for path in sorted(AGENT_SPECS_DIR.glob("*.md")):
        try:
            specs.append(parse_spec(path))
        except Exception as exc:
            errors.append((path, exc))

    if not specs and not errors:
        print("(no agent tasks defined yet — drop prompts/agents/<id>.md files to add them)")
        return 0

    width = max((len(s.id) for s in specs), default=20)
    for s in specs:
        btn = "✓" if s.button else " "
        last = _last_run_for(s.id) or "—"
        print(f"  {s.id:<{width}}  {btn} {s.title}  (last_run={last})")

    if errors:
        print()
        print("Specs that failed to parse:")
        for path, exc in errors:
            print(f"  ✗ {path.name}: {exc}")
        return 1
    return 0


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Run an agentic task.")
    parser.add_argument("id", nargs="?", help="task id (matches prompts/agents/<id>.md)")
    parser.add_argument("--list", action="store_true", help="list available tasks")
    parser.add_argument("--dry-run", action="store_true", help="resolve + print spec without spawning")
    parser.add_argument(
        "--var", action="append", default=[],
        help="prompt-body substitution (repeatable). Format: key=value",
    )
    args = parser.parse_args()

    if args.list:
        return cmd_list()

    if not args.id:
        parser.error("expected task id (or --list)")

    spec_path = AGENT_SPECS_DIR / f"{args.id}.md"
    try:
        spec = parse_spec(spec_path)
    except SpecError as exc:
        log.error("%s", exc)
        return 2

    extra_vars: dict[str, str] = {}
    for kv in args.var:
        if "=" not in kv:
            log.error("--var must be key=value, got %r", kv)
            return 2
        k, _, v = kv.partition("=")
        extra_vars[k.strip()] = v

    return await run(spec, args.dry_run, extra_vars)


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
