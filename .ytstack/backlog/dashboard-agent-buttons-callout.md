---
name: The agent buttons sit outside their "🤖 Agents" callout
description: Seed's region rewrite writes the agent-buttons body and end marker without the callout's `> ` prefix, so the buttons render below the collapsed callout instead of inside it. The template inherited the rewritten form. Decide where the buttons belong before changing either.
type: defect
origin: M034-S04-T01 (recording the bash seed)
created: 2026-10-16
---

# The agent buttons sit outside their "🤖 Agents" callout

## What the code does

`dashboard.agent_buttons.update_dashboard` replaces the text from
`<!-- agent-buttons:begin -->` through `<!-- agent-buttons:end -->` with
`begin \n refs \n end`. The begin marker sits inside the collapsed callout
(`> <!-- agent-buttons:begin -->`), and the `> ` before it survives because it lies outside
the region. The refs line and the end marker get no prefix, though.

A blockquote does not carry on across an HTML block, so the refs most likely render as a
paragraph after the callout. That is visible on every dashboard, not hidden inside "🤖 Agents".

## How it got here

- `17f69ff` (2026-05-17) shipped the region inside the callout: both lines carry `> `.
- The first rewrite dropped the prefixes.
- `7cbb1b5` (2026-05-18) resynced the template from a rewritten vault, so the template now
  carries the unprefixed form too.
- lxw's dashboard has the same form (lines 296–298, read 2026-10-16).

## Why it is not fixed yet

The fix is cheap: carry the begin marker's line prefix onto each written line. But it moves
buttons that the operator has seen at the bottom of the dashboard for months into a
collapsed section.

That makes it a layout decision, not a clean defect. The rendering is also unverified here:
nothing in this repo renders Obsidian's callouts.

Decide first:
- **Inside the callout,** as designed in 17f69ff: fix the rewrite to keep the prefix, and
  resync the template.
- **Always visible:** move the markers out of the callout in the template, and keep the
  rewrite as it is.

The rewrite is Python already; S04-T03 only calls it in-process instead of through `uv run`.
The fix can land whenever the decision is made.
