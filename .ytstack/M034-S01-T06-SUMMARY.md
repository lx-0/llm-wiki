---
milestone: M034
slice: S01
task: T06
project: llm-wiki
closed: 2026-10-15T20:12:00+02:00
verification: passed
---

# M034-S01-T06 -- Summary

## Commits

- `2bf80f3` -- M034-S01-T06: the dream / dream-entity routing and the OAuth aliases move into the catalogue — the last argv routing leaves bash; release 0.7.7
- `2ea37a0` -- M034-S01-T06: the bash oracle records four more routing paths from today's bash — dream with an unknown subcommand, bare dream-entity, dream web-research --help and gmeet-auth --help (53 cases)
- `572b1df` -- M034-S01-T06: planned — the dream / dream-entity routing (default route, argument prefixes, the list-candidates --json banner rule, the unknown-subcommand refusal) and the auth aliases (kind alias) move into the catalogue

## Outcome

The catalogue expresses the routing the bash `case` statements encoded.

New machinery:
- `SubRoute.args`: arguments a route puts first.
- `CommandSpec.handler_args`: the same, for the default handler.
- `CommandSpec.default_route`: the route taken for no arguments or a leading `--flag`.
- Kind `alias`, with `alias_of`.

The commands:
- **`dream`** has six routes over `dream.py`: `sweep` / `--all-entities`, `list-candidates`
  / `--list-candidates` and `web-research` / `--web-research-only`. Its default route is
  `sweep`, and it refuses unrouted words.
- **`dream-entity`** is `dream.py entity …`, and shows its help when bare.
- **The three OAuth names** are aliases of `auth <service>`.

`cli._route` resolves a named route first, then the default one, and `cli.main` dispatches an
alias as its argv.

`wiki` lost `cmd_dream`, `cmd_dream_entity`, `_run_script` and five case lines; it is down to
684 lines. `lib/common.sh` lost `wants_json`, whose last caller was `cmd_dream`.

Live on the scratch vault:
- `dream --dry-run` runs under the `wiki dream sweep` banner, and `dream-entity <slug>
  --dry-run` under `wiki dream-entity`;
- `dream list-candidates --json` parses as JSON (2 candidates);
- `gmail-auth` prints the auth help, and bare `dream-entity` prints its own help;
- `dream bogus` exits 1 with the dispatcher's message.

## Deviations from plan

- **`tests/test_bash_json_banner.py` was rewritten, not deleted.** It used to drive the
  bash `wants_json` rule through a stub `uv`, and both the rule and its caller are gone. It
  now holds the `--json` seam end to end, through the real `wiki` and the one hop into
  `dream.py`, in the oracle's fixture:
  - with `--json`, `json.loads` must succeed on stdout;
  - without it, the human banner leads.

  It was seen to fail: with the dispatcher's `--json` rule removed it raised
  `JSONDecodeError`, and the rule was then restored.
- **`wants_json` was deleted with its last caller.** That follows the locked decision "no
  soft deprecation".
- **Two outputs stay out of the goldens on purpose.** The sweep and `list-candidates`
  outputs depend on the clock, and the sweep's weights are probabilistic. The routing unit
  tests (17) and the end-to-end banner test cover those routes.

## Follow-ups

- **T07:** the consumer smoke on the scratch vault, at S01's head:
  - the desktop app's `wikiBin` spawns (`menu --json`, `doctor --json`);
  - the Obsidian shell-command buttons;
  - the `~/.local/bin/wiki` symlink;
  - the use-llm-wiki skill's commands.
- **S02 onward:** the remaining bash commands are `setup`, `config`, `hooks`, `skills`,
  `seed`, `update`, `status` and `install-shortcut`.

## Verification

Commands, all passed:
- `uv run --frozen pytest tests/test_cli.py tests/test_bash_oracle.py -q`. The 17 routing
  tests were watched failing first, and the oracle is unchanged except for the decided
  `dream-unknown` prefix.
- `uv run --frozen pytest -q`: 2361 passed, 1 skipped.
- ruff check and format are clean; `bash -n` passes on `wiki` and `lib/common.sh`.

A grep for `cmd_dream|_run_script|gmail-auth)|wants_json` in `wiki` and `lib/` finds nothing.
CI is green on `2bf80f3` (ci + secrets-scan).
