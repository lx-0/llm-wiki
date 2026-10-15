# `wiki config set` keeps the operator's comments in config.yaml

**Found:** M034-S02-T02, while recording the bash oracle's `config-edit-set` case (2026-10-15).

## The problem

`core/config.py:_set_in_yaml` parses config.yaml, sets one key, and dumps the whole file
again with `yaml.safe_dump` under a fixed five-line header. Every comment the operator wrote
is gone after one `wiki config set`, and so is their key order. In the golden, the fixture's
own first line, `# bash-oracle fixture config — …`, is replaced by the writer's header. A
round-robin backup keeps the old text under `.wiki/state/config-backups/`, so nothing is
unrecoverable; but it is silent.

It is documented, and has been since the bash:
- `wiki config --help` ends with "comments in config.yaml are dropped on programmatic writes";
- the header itself says "comments not present here are dropped".

So this is a known trade-off, not a regression. Two sites write config.yaml this way: the
setup wizard, through `config set`, and the `migrate_config_keys` migration.

## Why it matters

config.yaml is operator-managed. The engine's own guidance for operator YAML (the memory
"yaml.safe_dump only for file creation") is a line-level replacement of the one key, so the
rest stays byte for byte. `_set_in_yaml` is the exception. Each `wiki config set`, wizard run
or editor change also turns into a whole-file diff in a vault that tracks `.wiki/` in git.

## Fix sketch

- **The key already exists as a scalar line:** replace that line's value in place, with
  indentation, quoting style and trailing comment kept.
- **The key is new:** insert it under its section, or append the section.
- **Fall back to the dump only for structure changes** (a list or mapping value, which `set`
  refuses anyway) or when the file does not parse.
- **Test on the real data shape:** a copy of the live vault's config.yaml, with its comments,
  must survive one `set` with a one-line diff.
- **Same commit:** the migration's writer, and the help line plus the header text.

## Size / priority

Small (one function, tests, two docs lines). Low urgency: documented, backed up,
operator-visible only as lost comments. Natural home: S02-T03 or later, wherever
`core/config` is touched next.
