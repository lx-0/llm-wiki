# Lifecycle fixtures

Introduced in M005-S04-T03 and -T04. Each pair (`<entity>-before.md` +
`<substrate>-after.md`) represents a state-evolution scenario the
compile prompt's lifecycle rules should handle correctly.

**Pair 1 — resolution-demotion** (T03):
- `jane-doe-before.md` — entity page in State BEFORE Jane sent the deck
- `jamie-followup-after.md` — substrate where Jane confirms she sent it

Expected outcome (encoded in the AFTER substrate's `## Expected lifecycle outcome` block): the next compile pass demotes the open `- [ ] Send the Q3 deck` from State to a Timeline entry marked `[resolved]`.

**Pair 2 — manual-[x] preservation** (T04):
- `bob-smith-before.md` — entity page with `- [x] Sign the contract` (operator-checked) in Action Items
- `email-touch-after.md` — substrate that touches Bob's page but does NOT mention the contract

Expected outcome: the next compile pass preserves the `- [x]` line in State (does NOT auto-demote on substrate touch alone).

LLM-emission validation is operator-canary work; these fixtures are
plumbing tests + canary truth-set.
