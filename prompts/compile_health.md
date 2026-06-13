You are processing a daily Oura health rollup against the personal-wiki health-policy article.

${owner_block}
## Hard facts (override anything in the source material)

${facts_md}

## Source material

**File:** `${source_path}`

```
${source_content}
```

## Your task — execute the established health-rollup policy

A `type: health-rollup` source is a structured metric-only YAML stub: frontmatter carries the day's biometrics; the body is either an empty `(Add observations below as needed.)` placeholder or operator-written prose. The policy lives in `knowledge/concepts/health-rollup-intake-format.md` and has been in force for weeks — your job is to execute it cheaply, not re-derive it.

You have **Read, Grep, Glob, Edit, Write** restricted to `knowledge/**`. Stay under **6 turns**. This is structured-substrate processing, not knowledge synthesis. The right output is small.

### 1. Classify the body

After the closing `---` of the frontmatter, the body is either:

- **Stub-body** — whitespace, the literal `(Add observations below as needed.)` placeholder, or both. Operator has not annotated this day. **This is the common case.** Go to §2-A.
- **Operator-prose** — anything else (sickness notes, training context, mood, travel, a sentence about why HRV crashed). Go to §2-B.

Do not parse the frontmatter metrics for "anomalies" — single-day biometric snapshots are point-in-time data, not knowledge, per the policy article. Trend aggregation is a separate, future concern outside this pass.

### 2-A. Stub-body branch

Stub-bodies are normally recorded **deterministically upstream** — a Python pre-pass in `compile.py` state-marks them with no agent and no `knowledge/` writes, so they never reach you. If one reaches you anyway: make **no edits at all**. A metric-only stub is point-in-time biometrics, not knowledge. In particular do **NOT** append it to any `compiled_from:` list — that list's unbounded growth previously broke the Read-tool token limit and stalled every health compile. Emit your final result directly with no tool calls.

### 2-B. Operator-prose branch

The operator wrote actual content in the body. Treat it as a thin substrate pass. Do **NOT** append to any `compiled_from:` list (see §2-A — it broke the Read limit). Two steps:

1. **Scan the prose for entity mentions** — people (first names, full names), projects (`fleet`, `openclaw`, `paperclip`, `llm-wiki`, etc.), and existing `[[knowledge/concepts/<slug>]]` wikilinks. For each:
   - Glob `knowledge/{people,projects,concepts}/<slug>.md`. If it does NOT exist: **SKIP** (do not stub from health-rollup mentions — wait for proper substrate introduction elsewhere).
   - If it EXISTS: append ONE Timeline line (newest-first under `## Timeline`):
     `- **${today}** | \`${source_path}\` — Mentioned in health rollup: <one-line context from the prose>.`
   - Do NOT touch the State block above `---`. Do NOT add Action Items. Do NOT carry-forward or stale-flag. Append-only.
2. **Append one log entry to `.wiki/logs/operations.md`** at the top (newest-first):

   ```markdown
   ## [${now}] compile | Health rollup <date> (with observations)
   - Source: `${source_path}`
   - Articles created: (none)
   - Articles updated: (none, or `[[<entity-page>]] (Timeline +1)` for each entity whose Timeline you edited)
   - Metrics snapshot: sleep <sleep_hours> h, score <sleep_score>, readiness <readiness_score>, HRV <hrv_overnight> ms, <steps> steps, RHR <resting_hr> bpm.
   - Observations: <one-sentence summary of the operator's prose>.
   ```

Do NOT create new entity stubs. Do NOT touch `knowledge/index.md`. Do NOT escalate to full two-layer carry-forward — that's the dialog-substrate pass's shape, not health's.

### 3. No new articles

Health-rollup files NEVER create new wiki articles, and NEVER edit the policy article (`concepts/health-rollup-intake-format`) — do not read it, do not append to its `compiled_from:`. Everything is append-only on existing entity pages (Timeline) or operations log.

### 4. Stop at the first complete result

This task is bounded: at most operations log + maybe one Timeline line per mentioned entity. If you find yourself reading the policy article or about to make a third kind of edit, you've drifted — stop and emit your final result.

## Anti-loop guard

If after 4 turns you haven't finished:
- STOP all entity-extraction. If you've written the log entry, you're done.
- Emit your final result; do not start new tool calls.

${output_language_instruction}
