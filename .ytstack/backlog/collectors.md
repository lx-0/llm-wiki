# Collectors — Standalone Ingest Programs

## Idea

The wiki engine is a **compiler** — it turns raw sources into wiki articles. Gathering raw material from external sources is a separate concern. **Collectors** are independent programs that prepare raw data and drop it into `raw/`.

## Three separate concerns

```text
1. COLLECTORS              2. WIKI ENGINE          3. PERSONAL VAULT
   (gather)                   (compile)               (live work)

   Email digest               raw/  ← collectors      Tasks, meetings, briefs
   Calendar summary           daily/ ← session hooks  Reading list
   Browser data               knowledge/ ← compile    Customer notes
   Screenshot OCR
   NAS scanner
   RSS / articles
   …
```

## Possible collectors

| Collector | Source | Output | Trigger | Priority |
|---|---|---|---|---|
| **Email digest** | local mbox / IMAP / Gmail API | thread metadata + LLM-filtered bodies → `raw/notes/email/` | daily | high |
| **Calendar summary** | local CalDAV / Google Calendar API | day/week digest → `raw/notes/calendar/` | daily | high |
| **Browser** | Firefox / Chrome profile dirs | tabs, bookmarks, visits, search → `raw/notes/browser/` | weekly | medium |
| **Screenshots** | OS screenshot folder | per-image vision OCR sidecars → next to PNG | daily | medium |
| **NAS scanner** | SMB-mounted NAS | metadata index → `raw/notes/nas/` | weekly | medium |
| **Downloads watcher** | OS downloads dir | PDFs/articles → `raw/articles/` | fswatch / periodic | medium |
| **Bookmark sync** | browser bookmarks | URLs → `raw/articles/` | weekly | medium |
| **LinkedIn ingest** | LinkedIn API / MCP | contacts, posts, messages → `raw/notes/linkedin/` | weekly | low |
| **Messages digest** | iMessage / Signal / Slack | relevant convos → `raw/notes/messages/` | tbd | low |
| **Articles / RSS** | RSS feeds | new articles → `raw/articles/` | daily | low |

## Email ingest pattern (template for others)

Three-stage flow that minimises cost and maximises signal:

1. **Stage 1 — metadata scan** (free): list folders, count messages, sender frequencies, subject patterns, date ranges. Output one summary file per account.
2. **Stage 2 — LLM relevance filter on metadata** (cheap, local model): which folders / threads / senders are likely to contain actionable knowledge?
3. **Stage 3 — deep scan on filtered subset** (medium cost): read full bodies, reconstruct threads, summarise.

Only stage 3 reads message bodies; the cost is bounded by the stage-2 filter.

## Curiosity loop — cross-collector pattern

When the wiki compiler processes a collector's output, it also generates **ingest requests** for the next run:

```text
shallow scan → compile → wiki articles + ingest requests
                              ↓
next run reads requests → deeper scan → compile → richer articles + new requests
                              ↓
… loop until knowledge saturates or budget hits the cap
```

Requests land in `raw/requests/<collector>-*.json`. Types: `deep-scan`, `metadata-scan`, `thread-focus`, `skip`. Each request carries a priority and a budget estimate. The loop stops at max rounds or budget cap.

The system decides where to dig deeper; the human only sets the budget.

## Open questions

- Separate repo for collectors, or part of the wiki repo? Argument for separate: collectors are mostly OS-/account-specific, can have their own dependency graph. Argument against: tight coupling with `raw/` schema.
- Local vs. remote — some collectors need APIs (Gmail, Google Calendar, LinkedIn).
- Privacy — email and messages are sensitive; never push raw bodies to git, only metadata digests.
- Budget defaults per collector — how aggressive should the curiosity loop be?

## Next step

Stabilise the wiki engine first, then build collectors one at a time. Don't bundle them — each is a separate review surface.
