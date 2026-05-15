# Curiosity deep-scan: use topic as IMAP/Gmail search-query, not blind folder dump

**Priority:** P2 — improves signal-to-noise of curiosity output. Not blocking; the
current architecture works, just produces a lot of irrelevant body content that
Claude has to filter at compile time.

**Origin:** 2026-05-15 first real curiosity consumer run after the model-fix arc
(`5dc6670`). Operator observation: "die requests haben keine wirkliche frage" —
correct, the request carries a topic string but the consumer never uses it as a
search predicate.

## Current behavior

`scripts/curiosity/backends/email.py:process_request()` calls
`reader.scan_deep(folder=folder, limit=50)` — pulls the **50 newest messages**
from the configured folder, **without any topic filtering**. The topic ends up
only in the rendered `deep-<slug>.md` frontmatter and prose intro, then the next
compile pass relies on Claude/Opus to filter relevant messages from the dump.

Effect: at folders with realistic mail volume, the curiosity-specific signal
(the topic) gets diluted across 50 mostly-unrelated bodies. Claude distills the
whole dump rather than the topic-relevant slice.

## Proposed change

Push the topic down to the reader as a query/keyword set so the IMAP/API does
the filtering server-side. Adapter capability is uneven:

| Reader kind | Search capability today | Lift cost |
|---|---|---|
| `gmail-api` | Full Gmail query syntax (`from:`, `subject:`, `after:`, free-text) | Add `query: str` arg to `scan_deep`; pass through to `users.messages.list q=...`. |
| `imap` | RFC 3501 `SEARCH`: `BODY`, `SUBJECT`, `FROM`, `SINCE` | Add `query` → translate to `SEARCH BODY "<term>"`. Multi-word topics need term-extraction (e.g. stopwords out, top-N keywords). |
| `thunderbird-mbox` | None — local file parsing only | Either skip topic-search (current behaviour) or post-filter in Python with substring match. |

## Adapter contract sketch

Extend the `MailboxReader` protocol in `scripts/adapters/mailbox/base.py`:

```python
def scan_deep(
    self,
    *,
    folder: str,
    limit: int,
    query: str | None = None,  # NEW: free-text topic; adapters apply best-effort
) -> Iterator[Message]:
    ...
```

Each reader handles `query` per its native capability; if unsupported, falls
back to current "newest N from folder" semantics. Document the per-adapter
behaviour clearly so the operator knows where topic-filtering actually fires.

## Topic → query translation

The topic strings llama3.1:8b produces are mid-sentence English noun phrases:
*"K8s + Cilium debugging quirks for agent-services"*. Needs cleanup before
hitting IMAP `SEARCH`. Two paths:

1. **Cheap:** strip stopwords + punctuation, take top 2-3 nouns. Risk: drops the
   technical context that makes the topic specific.
2. **Right:** ask the producer to also emit a `query_terms: list[str]` field in
   the request schema. Has the topic-generating LLM commit to the search terms
   alongside the prose topic. Same call, no extra cost.

Lean toward (2) — keep the LLM in the loop for term selection. Update the
schema in `curiosity/producer.py` + the prompt in `prompts/compile_curiosity.md`
to ask for both `topic` (prose) + `query_terms` (3-5 search keywords).

## Done when

- `MailboxReader.scan_deep` accepts an optional `query` parameter
- gmail-api + imap adapters honour it (thunderbird-mbox keeps current behaviour
  with a documented note)
- Producer emits `query_terms` and the consumer passes them through
- A `deep-<slug>.md` for a topic with mail-volume `> limit` in the folder shows
  topic-relevant bodies, not the newest-N generic dump

## Out of scope

- Vector-search / semantic embedding over mail corpus — that's an entirely
  different backend, not an extension of the IMAP-search path.
- Cross-folder search — keep the per-request `folder` scoping. If the topic
  spans folders the producer should emit multiple requests.

## Adjacent

- `curiosity-consumer-gap.md` — original consumer-gap ticket, now closed by the
  2026-05-15 model-fix arc. This ticket is the natural next iteration.
- `prompts/compile_curiosity.md` — extend rules + JSON example to cover
  `query_terms`.
