# M005-S03 canary procedure — real-substrate LLM-emission validation

T05 of M005-S03. Engine-side work (prompt rules + lint + fixtures) is
done; this doc tells the operator how to validate that the LLM actually
obeys the rules on real substrates.

LLM emission cannot be CI-tested deterministically. This is a human-in-
the-loop step. Three canaries, increasing in real-world fidelity.

## Pass/fail philosophy

**Precision over recall.** False positives (hallucinated commitments)
are worse than false negatives (missed real ones). A canary that
under-extracts a real commitment is a PASS-with-caveats — turn the
recall knob (more aggressive prompt). A canary that fabricates one is
a FAIL — fix the prompt before shipping.

**Conservative routing.** Wrong entity page is worse than missed page.
A commitment routed to the right person but the wrong project is
PASS-with-caveats. A commitment routed to a hallucinated person is FAIL.

## Canary 1 — Synthetic fixture (cheapest)

Run compile against the M005-S03-T04 synthetic fixture. Truth-set is
explicit in the fixture's `## Expected extraction` block.

### Invocation

```bash
cd <vault>
# Copy the engine fixture into the live raw/ tree (one-shot, for canary only)
cp <engine-repo>/tests/fixtures/jamie/2026-04-15--canary-q1-review--abc.md \
   raw/transcripts/jamie/2026-04-15--canary-q1-review--abc.md

# Compile just this one file
wiki compile --only raw/transcripts/jamie/2026-04-15--canary-q1-review--abc.md
```

### Expected outputs

- A new `knowledge/people/jane-doe.md` (if not pre-existing) with two-layer shape.
- Jane's `## Action Items` contains: `- [ ] Send the Q3 deck 📅 2026-04-22` (with counter-proposal or similar wording).
- Jane's `## Open Threads` contains a "waiting on Hetzner infra capacity" line.
- Jane's `## Timeline` contains a 2026-04-15 entry citing `raw/transcripts/jamie/2026-04-15--canary-q1-review--abc.md`.
- The operator-side "Set up Bob intro" commitment lands on a project page (whichever is most contextually relevant — yesterday-platform or a fresh stub) OR on Bob's page if Bob is mentioned by name.
- A `knowledge/people/bob-*.md` stub may be created (if no Bob page exists). This is correct.

### Verification commands

```bash
# Jane's page exists with two-layer shape
test -f knowledge/people/jane-doe.md && grep -E "^## (State|Action Items|Open Threads|Timeline)" knowledge/people/jane-doe.md | wc -l
# expect: 4

# Q3 deck commitment with deadline
grep -F "Q3 deck" knowledge/people/jane-doe.md
grep -F "2026-04-22" knowledge/people/jane-doe.md

# Hetzner thread (in Open Threads — not Action Items)
grep -A1 "## Open Threads" knowledge/people/jane-doe.md | grep -F "Hetzner"

# Timeline entry citing the canary substrate
grep -F "2026-04-15--canary-q1-review--abc.md" knowledge/people/jane-doe.md

# Anti-hallucination check: no OVH-canary commitment (it was a hypothetical Jane rejected)
grep -F "OVH" knowledge/people/jane-doe.md && echo FAIL || echo PASS

# Lint stays green
wiki lint --structural-only 2>&1 | grep -E "two_layer_|action_item_"
# expect: no error/warning codes
```

### Decision

- All grep blocks return expected matches AND lint stays green → **PASS**
- Q3 deck found but no deadline → **PASS-with-caveat** (prompt-iteration: tighten deadline-extraction rule)
- Hetzner landed in Action Items instead of Open Threads → **PASS-with-caveat** (prompt-iteration: tighten blocked/waiting distinction)
- OVH commitment exists OR a non-mentioned person was stubbed → **FAIL**

## Canary 2 — Live jamie meeting

Pick a recent jamie meeting from `raw/transcripts/jamie/` with ≥2 named
attendees and at least one explicit commitment phrase. Run:

```bash
cd <vault>
wiki compile --only raw/transcripts/jamie/<chosen-file>.md
```

### Expected outputs

For each commitment in the transcript:
- An `- [ ]` line in the owner's `## Action Items` (or `## Open Threads` if blocked/waiting).
- A Timeline entry in the owner's page citing the transcript.
- If the owner had no prior page, a stub with the two-layer template.

For each rhetorical / hypothetical / rejected idea: NO emission.

### Verification

```bash
# Find people pages touched/created today
find knowledge/people -newer raw/transcripts/jamie/<chosen-file>.md -name "*.md"

# Spot-check 2-3 entries:
# - Does each commitment surface as `- [ ]` with `📅` if a date was given?
# - Does each Timeline entry cite the right substrate?
# - Are there any commitments YOU did NOT recall hearing? (potential hallucination)

# Lint must stay green
wiki lint --structural-only 2>&1 | tail -10
```

### Decision

- Every commitment YOU remember surfaces correctly, no hallucinated extras, lint green → **PASS**
- 1-2 commitments missed but precision intact → **PASS-with-caveat** (note in DECISIONS.md)
- Any hallucinated commitment ("we agreed to X" when no one said it) → **FAIL** (fix prompt before continuing M005)

## Canary 3 — Live gmeet meeting

Same procedure as canary 2 but with a gmeet substrate. gmeet has paired
`## Summary` + `## Transcript` sections; the LLM should extract from
the Transcript (where commitments live), citing the file once.

```bash
cd <vault>
wiki compile --only raw/transcripts/gmeet/<chosen-file>.md
```

Look for the same shape of outputs. gmeet speaker labels are typically
"first name only" or "first+last" — the slugification rule should still
land them on the right page.

### Decision

Same criteria as canary 2.

## When all three pass

S03 ships. Move to S04 (lifecycle). Add a 1-line entry to DECISIONS.md
noting which canaries passed clean vs. with-caveats so the dogfooding
arc is reviewable later.

## When one fails

Iterate on the prompt — likely candidates: the commitment-extraction
quality bar wording, the entity-resolution disambiguation rule, the
"do not stub for one-off mentions" guard. Re-run the failed canary.

Persistent failure across iterations is the signal to either:

- Roll back the M005-S03 commits (revert from `M005-S01-T01` head) and
  rescope as M005-S03-redux with different extraction approach
- Land what's there as PASS-with-permanent-caveat and note the open
  prompt-iteration ticket in DECISIONS.md

## Source-of-truth references

- Prompt rules: `prompts/compile_main.md` Instruction 3 (T01 + T02 sub-sections)
- Schema reference: `templates/AGENTS.example.md` People + Project Articles
- Spec-locking fixtures: `tests/fixtures/two_layer/`
- Synthetic substrate: `tests/fixtures/jamie/`
- Lint enforcement: `scripts/lint.py:check_two_layer_pages` + `check_action_item_syntax`
