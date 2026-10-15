---
milestone: M034
slice: S02
task: T04
project: llm-wiki
closed: 2026-10-15T21:30:00+02:00
verification: passed
---

# M034-S02-T04 -- Summary

## Commits

- `0e56967` -- M034-S02-T04: `wiki install-shortcut` in Python — shortcut_cli.py; a regular file in the way is refused, not rm -f'd; release 0.7.13
- `45fab6c` -- M034-S02-T04: the bash oracle records three more install-shortcut paths from the bash, before the port (65 cases)
- `1deeb46` -- M034-S02-T04: planned

## Outcome

`wiki install-shortcut` is `scripts/shortcut_cli.py`: the `~/.local/bin/wiki` symlink to this
vault's entry, `--print-only`, the PATH probe and the rc line. No vault is needed.
- A link that resolves to this entry is left alone; the compare uses resolved paths.
- A link to another vault is replaced.
- Anything that is not a symlink is refused (exit 1) and left untouched.
- The rc line keeps its quotes.

`core/console` gained `ok` / `warn` / `info` / `banner`, the stdout status lines the bash
printed. They are styled by stdout's terminal state at call time. `config_cli` and
`setup_cli` dropped their own copies for them.

`wiki` lost `cmd_install_shortcut` and is at 539 lines. The bash now owns only `hooks`,
`skills`, `seed`, `update` and `status`.

Live on the scratch vault, with a sandboxed HOME:
- the link is created (to `/private/tmp/…/.wiki/wiki`);
- the rc line is quoted;
- `wiki version` through the link from `/tmp` prints the revision.

## Deviations from plan

- **One shared helper set, not three copies.** The stdout helpers moved into `core/console`
  rather than being copied again into `shortcut_cli`. This anticipates S06-T02 (`print` →
  `core/console`) for the ported commands.
- **The refusal exits before the PATH section.** In the regular-file case the oracle's diff
  therefore also shows the PATH lines gone, a consequence of the decided refusal.

## Follow-ups

- **T05:** the slice's close.
  - The deletions it planned have already happened with each port: `cmd_config`,
    `cmd_setup`, `cmd_install_shortcut`, the wizard pieces, `ask` / `pause`.
  - Left: the docs pass (README / cli.md / AGENTS.md mentions of the bash pieces), and
    `wiki setup` end to end on a *fresh* scratch vault through the real install path.

## Verification

Commands, all passed:
- `uv run --frozen pytest tests/test_shortcut_cli.py tests/test_bash_oracle.py -q`. The 7
  shortcut tests were watched failing first. In the oracle (65 cases) only the decided lines
  moved: the rc-line quotes, the regular-file refusal, and one help line.
- `uv run --frozen --group typecheck ty check scripts/core`: clean.
- `uv run --frozen pytest -q`: 2428 passed, 1 skipped.

CI is green on `0e56967` (ci + secrets-scan).
