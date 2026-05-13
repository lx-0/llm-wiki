# Dashboard — Open Action Items section

**Status:** backlog. Independent of `dashboard-upcoming-events.md`; can ship alone.

**Origin:** 2026-05-10. User wants `dashboard.md` to surface open todos / action items at the top so they don't drown in `## ✅ Open tasks` (which only matches Obsidian Tasks `- [ ]` syntax and misses everything in `daily/`).

## Problem

Every `daily/YYYY-MM-DD.md` session block ends with a `## Action Items` heading followed by bullet items (`- **Foo** — bla bla`). 95+ items across the last 10 days alone. The flush prompt produces this format consistently.

But the existing dashboard `## ✅ Open tasks` block uses the **Tasks plugin** (`- [ ]` checkbox syntax), which doesn't see plain bullet items. So the entire daily-action-items stream is invisible on the dashboard.

## What "open" means here

Action items in dailies have no completion state — there's no `- [x]` mechanic. Three possible definitions of "open":

1. **Recency-windowed**: items from the last N days (default 7) are "still open by recency". Cheap, no state to maintain, accepts that some shown items are already done.
2. **Manual checkbox conversion**: change the flush prompt so action items render as `- [ ]` and Tasks plugin handles open/done state. Requires user to tick checkboxes; otherwise everything stays "open" forever.
3. **Per-item state file**: track item-id → status in `state/action-items.json` updated by user via dashboard buttons. Most effort.

Default recommendation: **option 1** for v1 — simplest, surfaces signal immediately, no behavioural changes elsewhere. Re-evaluate after operator reports whether stale items are noisy enough to warrant option 2.

## How (sketch)

New section in `templates/dashboard.md` placed near the top (above `## ⚡ Engine status` or in a fresh `## 📅 Up next` umbrella section):

```dataviewjs
// Aggregate '## Action Items' bullets from daily/ files modified in the last 7 days.
const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
const dailies = dv.pages('"daily"').where(p => p.file.mtime.toMillis() > cutoff)
  .sort(p => p.file.mtime, 'desc');

const items = [];
for (const p of dailies) {
  const text = await dv.io.load(p.file.path);
  const sections = text.split(/^##\s+Action Items\s*$/mi).slice(1);
  for (const sec of sections) {
    const block = sec.split(/^---/m)[0];
    const bullets = block.match(/^[-*]\s+.+$/gm) || [];
    for (const b of bullets) {
      items.push({ day: p.file.name, line: b.replace(/^[-*]\s+/, '') });
    }
  }
}

dv.table(['Day', 'Action item'],
  items.slice(0, 30).map(x => [`[[${x.day}]]`, x.line]));
```

Tunables:
- Cutoff window (default 7 days) → could be a config field.
- Max items shown (default 30).
- Heading + emoji for the dashboard section.

## Edge cases / risks

- **Same item appears in multiple sessions on the same day** (multiple flushes). Dedup heuristic: collapse byte-identical bullets within the same day.
- **Bullets that span multiple lines** (e.g. nested structure). Regex above is one-line-only — multi-line items get clipped. Acceptable for v1; flag in commit message.
- **"None identified"** placeholder text from the flush prompt. Filter out: skip bullets matching `^None identified` or `^- None`.

## Non-goals

- Marking items done from the dashboard (option 3 above).
- Modifying the flush prompt to emit checkboxes (option 2 above).
- Cross-substrate aggregation (knowledge/, raw/notes/, etc.). Daily/ only — that's where action items live.

## Hard preconditions

None. Dataview JS is already enabled in the vault (existing dashboard sections use it).

## Doc updates required

- `docs/PROCESS.md` — add the new dashboard section to the dashboard surface description.
- `templates/dashboard.md` — the actual block.
- Probably `KNOWLEDGE.md` if any non-obvious pattern surfaces during implementation.
