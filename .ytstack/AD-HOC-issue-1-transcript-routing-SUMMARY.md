# AD-HOC — Issue #1: route `type: transcript` to compile_main (2026-05-24)

**Trigger:** GitHub issue #1 (@Sidwach). On a fresh vault, `wiki compile` over 139
jamie/gmeet transcripts produced 53 concepts, 2 projects, **0 person articles** —
every transcript carried named participants in frontmatter, yet `knowledge/people/`
stayed empty.

## Root cause (verified, not just read from report)

`scripts/compile_stages/route.py` `SUBSTRATE_PROMPTS` had no `transcript` key.
`_substrate_key()` returns the frontmatter `type:` (`"transcript"`), the dict
lookup missed, and `_DEFAULT_DISPATCH = ("compile_default", …)` won.
`compile_default.md` explicitly refuses person/project state work, so the two-layer
person-stub creation + State/Timeline + Action-Item routing documented in
`compile_main.md` (instruction 4) never ran.

**Not a regression** — `transcript` was never enumerated (`git log -S` shows only
M026 relocations). The 2026-05-16 "safe-by-default" dispatch change deliberately
deferred routing the dialog substrates (jamie/gmeet/voice/transcript) to
compile_main as "<5 files each, not yet profiled." This issue is that deferral
coming due. Same mechanism (`SUBSTRATE_PROMPTS.get(key, _DEFAULT_DISPATCH)`) that
guards against runaway *cost* also silently *under-processes* substrate that needs
the rich prompt — two failure directions, one root.

## Fix (commit `158fc6d`, on origin/main)

- `"transcript": ("compile_main", 60, "claude-haiku-4-5-20251001")` added to
  `SUBSTRATE_PROMPTS` — same tier as `longform` (rich prompt, 200K ctx for
  60–270 KB transcripts, 60-turn budget for multi-participant stub fan-out).
- `("raw/transcripts/", "transcript")` added to `_SUBSTRATE_PATH_FALLBACKS` for
  legacy pre-frontmatter files.
- Tests (`tests/test_decide_route.py`): `transcript → compile_main` dispatch +
  legacy path fallback. RED→GREEN; all route/dispatch suites green
  (1038 passed; 4 pre-existing `test_dream_sampling.py` failures are an
  unrelated parallel arc — `dream.py` does not import the routing tables).

## Scope notes

- **YouTube caught too (intended):** `scan_youtube.py` also emits
  `type: transcript`, so youtube transcripts now route to compile_main.
  compile_main self-gates person-stub creation on attributed dialog → single-
  speaker videos extract concepts without spawning spurious people pages.
- **voice-note stays on default (NOT a bug):** `voice.py` emits `type: voice-note`,
  which is already plain dictated text, not attributed multi-participant dialog —
  no participants to stub, no two-layer State. `compile_default` is correct. The
  2026-05-16 line lumping "voice" with the transcripts was imprecise.

## Follow-up

- **Force-recompile** the affected transcripts on the reporter's vault to backfill
  the person pages the aborted run skipped (noted in the issue comment).

## Closure

Issue #1 CLOSED/COMPLETED — auto-closed via `closes #1` when `158fc6d` landed on
origin/main (push by parallel session). Resolution comment posted
(issue #1, comment 4529027908). KNOWLEDGE.md updated (`4b11973`, `0d57abc`).
