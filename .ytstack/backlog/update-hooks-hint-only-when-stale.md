---
name: update's hooks hint prints after every update that moved the engine
description: "`wiki update` advises re-running `wiki hooks install` after every pull that brought a change, without looking at the installed hooks. The engine can compare them with what install would write and name only the agents whose hooks differ."
type: refinement
origin: M034-S05-T01 (recording the bash update)
created: 2026-10-16
---

# update's hooks hint prints after every update that moved the engine

## What the code does

After a pull that moved the engine, phase 2 prints this on every such update:

```
✓ Updated <old> → <new>
If hook payloads or config schema changed, you may want to re-run:
  wiki hooks install      # to refresh agent hook configs
```

The bash `_update_post_pull` does not look at the hooks; the records
`tests/golden/bash/update-fast-forward.txt` and its siblings show it. An operator reads it after
every update and cannot tell whether it applies to them.

## What it could do

The engine knows both sides:
- `core.agents.payload(name, wiki_dir=…, venv=…)` is what `wiki hooks install` would write;
- `core.agents.wiki_commands(core.agents.read_config(path))` is what is installed.

Print the hint only for the agents and scopes whose installed wiki hook commands differ from
the payload, and name them, as the cloud-vault check names `claude (user)` since 0.7.27. That
check could then fold into this one: a command without the environment is one kind of
difference.

"Or config schema changed" most likely means an agent's config schema (Cursor's flat
`version: 1` form), not `config.yaml`, which the update migrates itself. A payload comparison
covers that case either way.

## Why it is not in the port

S05-T02 ports update at oracle parity: defects are fixed in the bash first, then recorded.
This changes what the hint means, so it is a task of its own after the port, with its own
record.
