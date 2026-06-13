You are extracting recurring-meeting concepts and attendee-touch records from a Google Calendar day-rollup.

${owner_block}
## Hard facts (override anything in the source material)

${facts_md}

## Source material

**File:** `${source_path}`

```
${source_content}
```

## Your task — MINIMAL extraction only

This is METADATA, not dialog. Calendar files don't contain commitments, decisions, or first-person language. You will NOT trigger the full two-layer State rewrite shape used for transcripts (jamie/gmeet). You will NOT do carry-forward, resolution-detection, stale-flagging, or Action Item routing. Those belong to the dialog-rich substrate compile pass.

You have **Read, Grep, Glob, Edit, Write** restricted to `knowledge/**`. Stay under **8 turns**. Calendar metadata extraction must fit comfortably; if you find yourself nearing the cap, stop — the file is too dense, skip the remaining attendees rather than loop.

### 1. Recurring-concept pages

For each `[[concepts/<slug>|Title]]` wikilink in the source (typically marked as `**Recurring:**`), Glob `knowledge/concepts/<slug>.md`. If it exists: do nothing. If it doesn't: create a minimal stub at `knowledge/concepts/<slug>.md`:

```markdown
---
title: "<Title>"
type: concept
compiled_from: "${source_path}"
created: "${today}"
updated: "${today}"
tags: [meeting-concept, yesterday]
---

# <Title>

> Recurring meeting (calendar). First seen on ${today} via `${source_path}`.

(Operator can flesh this out manually if the meeting becomes substantive.)
```

The `yesterday` tag is the default domain anchor for meeting-concepts on this vault; if the meeting title clearly signals a different domain (e.g. "llm-wiki sync", "fleet planning"), substitute that one instead.

### 2. Attendee Timeline append (no State touch)

Collect every distinct attendee email from all events in the source (lines like `**Attendees:** a@x, b@y` and `**Organizer:** c@z`). Skip generic calendar-system addresses (`*@group.v.calendar.google.com`, holiday accounts, anything with `#` in the local part). For each real attendee email:

1. **Slugify** the local part of the email: `chris@yesterday-ai.de` → `chris`, `kontakt@simonschaffert.de` → `simon-schaffert` (use the domain's owner-name when local-part is `kontakt`/`info`/`hello`/etc.). Slug rules per AGENTS.md: lowercase, hyphen-separated, drop accents.
2. **Glob** `knowledge/people/<slug>.md`. If it does NOT exist: **SKIP this attendee.** Do not create stubs from calendar metadata — wait until a transcript/voice/email introduces the person properly.
3. If it EXISTS: append ONE Timeline line via `Edit`. Find the `## Timeline` section, and prepend (under the heading, above existing entries — Timeline is newest-first) a single line:
   `- **${today}** | \`${source_path}\` — Calendar: met for <comma-separated event titles, max 3>.`

   Do NOT touch the State block above `---`. Do NOT add Action Items. Do NOT change the executive blockquote. Do NOT remove any existing line. Append-only — one Timeline entry per attendee per source.

### 3. Index update (only if you created stubs)

If you created any new concept stub files in step 1, append one row per new file to `knowledge/index.md` in the standard format:
`| [[knowledge/concepts/<slug>]] | <one-line summary> | ${source_path} | ${today} |`

If you didn't create anything new (only appended Timeline entries to existing person pages): **skip this step entirely**. Existing rows don't need touching.

### 4. No operations log update

Calendar compiles run for every day's rollup — logging each one bloats `.wiki/logs/operations.md`. Skip the log append step.

## Anti-loop guard

If after 6 turns you haven't finished:
- STOP creating concept stubs (the remaining concepts can wait for the next pass).
- Finish your current attendee Timeline edit if mid-stream.
- Emit your final result; do not start new tool calls.

This is metadata extraction, not knowledge synthesis. The right output is small.

${output_language_instruction}
