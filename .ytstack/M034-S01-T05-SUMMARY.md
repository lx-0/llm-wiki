---
milestone: M034
slice: S01
task: T05
project: llm-wiki
closed: 2026-10-15T19:55:00+02:00
verification: passed
---

# M034-S01-T05 -- Summary

## Commits

- `25026f7` -- M034-S01-T05: menu, doctor, version, help and the bare entry move into the catalogue — the bash wrappers are gone, everything reaches Python through the one hop; release 0.7.6
- `2ad21f4` -- M034-S01-T05: the bash oracle records three more paths of the wrappers T05 ports, from today's bash — menu with an unknown argument (✗ unknown: wiki menu bogus, exit 1), help as -h, and version on an engine that is not a git checkout (! Not a git checkout…, exit 0). 50 cases
- `a3ef410` -- M034-S01-T05: planned — menu (home screen + --json route), doctor, version (engine_version.py), help and the bare entry move into the catalogue through the one hop; their five bash functions and case lines go; menu bogus takes the dispatcher's error style (decided); three cases recorded from today's bash first. S01 re-cut to 7 tasks (status → S03-T02)

## Outcome

`menu`, `doctor` and `version` are `py` commands in `cli_catalog`:
- **menu:** `menu.py`; a bannerless `--json` route to `menu_context.py`; `takes_args=False`.
- **doctor:** `doctor.py`.
- **version:** the new `scripts/engine_version.py`, with `revision` / `tag` / `origin`
  rows, the not-a-checkout warning, and no vault needed.

Their help texts moved verbatim from the bash heredocs (`H_MENU`, `H_DOCTOR`); `H_VERSION` is
new.

The catalogue gained two small pieces of machinery: `SubRoute.banner=None` (a
machine-readable route) and `CommandSpec.takes_args` (an unrouted argument is refused).

`cli.main([])` is the bare entry. It opens the menu when stdin and stdout are terminals and
prints help otherwise; this is `_interactive()`, which replaced the bash `-t` guard.

`wiki` lost `cmd_help`, `cmd_version`, `home_screen_python`, `cmd_menu`, `cmd_doctor`, their
case lines and the home-screen comment block. That is −130 lines, 759 left. Everything except
the not-yet-ported commands falls through to the one hop.

Live on the scratch vault (real uv, `25026f7`):
- the bare entry without a TTY prints help;
- in a pseudo-terminal the home screen renders, from `cli.py` → `python -m menu`;
- `version` prints the revision and the origin;
- `menu --json` gives the schema-2 payload with no banner;
- `doctor --quick --json` is valid JSON;
- `doctor` runs as dispatcher → `python -m doctor`, two processes where there were three;
- `menu bogus` exits 1 with the new message.

## Deviations from plan

- **The slice was re-cut before this task.** `status` moved to S03-T02, because it is a
  banner over `config status` and `hooks status`, both bash libraries ported there. The old
  T05 split into T05 (this task) and T06 (`dream` routing + auth aliases), and the consumer
  smoke became T07 (slice-plan notes).
- **One golden line moved without being a behaviour change.** In `doctor-quick-json`, the
  engine-environment check names the interpreter's `sys.prefix`. Through the hop, the
  fixture now runs from the vault's own `.wiki/.venv`, a link venv onto the test venv,
  instead of the test venv the shim exec'd directly. An operator's doctor always reported
  the vault venv. The oracle's `<VENV>` placeholder now covers both paths, so the golden is
  unchanged.
- **One behaviour change was decided in the CHANGELOG.** `wiki version --help` now prints
  help, where the bash ignored the flag and printed the version.

## Follow-ups

- **T06:** the `dream` / `dream-entity` routing (implicit sweep, `list-candidates` with its
  `--json` banner rule, `web-research`, the error for an unknown subcommand) and the three
  auth aliases. Records the dream error path from bash first.
- **S06 (surface diet):** `menu.py`'s non-TTY fallback still spawns `wiki help` (bash →
  python → python). It could print `render_help()` in-process. The output is the same.
- **S03-T02:** `wiki status`.

## Verification

Commands, all passed:
- `uv run --frozen pytest tests/test_cli.py tests/test_bash_oracle.py tests/test_bootstrap_hop.py -q`
  passes. The 10 new unit tests were watched failing first (missing `_interactive`, the
  old routing, a missing module).
- `uv run --frozen pytest -q`: 2340 passed, 1 skipped.
- ruff check and format are clean; the layout, module-size and function-length gates pass.

No call sites are left: a grep for the five deleted functions in `wiki` and `lib/` finds
nothing. CI is green on `25026f7` (ci + secrets-scan).
