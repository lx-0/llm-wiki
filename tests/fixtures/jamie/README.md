# Synthetic jamie substrate fixtures

Introduced in M005-S03-T04. Each `*.md` here imitates the shape of a real
jamie meeting transcript (frontmatter + `## Summary` + `## Transcript`
with speaker-labelled dialogue) so the compile pipeline can be smoke-tested
without touching the live lxw vault.

Filename convention mirrors the live collector output: `<date>--<slug>--<short-id>.md`.

Each fixture's body is *annotated* — the expected commitments are obvious
to a human reader so a real-substrate canary (S03-T05) can spot-check
whether the LLM caught them. The `## Expected extraction` block at the
bottom of each fixture lists what the LLM should find (the LLM ignores
that block during compile because it's a doc, not transcript content,
but the test pytest can grep it for canary truth-set).
