# Dream: stop re-spending on repeat INSUFFICIENT_CORPUS entities

**Status:** open · **Logged:** 2026-06-02 · **Size:** S–M

## Problem

The 2026-05-31 dream fixes (cache-aware tokens, no-op skip, char-budget trim,
INFO-downgrade of designed no-ops) made the warnings honest, but one *cost*
leak remains: an entity can burn a full SDK call (~$1) on a guaranteed no-op
every sweep, forever.

Observed (2026-06-02 lxw sweep): entity `kontakte` — a 2-line operator-imported
stub ("Sohn von Ranga Yongeshwar" + a URL, no substrate grounding). Corpus
`T1=8 (auth=0/recent=1/digests=7)`. The pre-flight no-op skip
(`features.dream_require_entity_substrate`) did NOT fire because `recent=1`.

Root cause of the spurious `recent=1`: `_mentions_entity` (dream.py) matches the
slug as a whole word, case-insensitive. The slug `kontakte` matches the generic
German noun "Kontakte" sitting in email-metadata regions of unrelated
substrate. The agent runs, finds zero synthesizable claims, prints
`INSUFFICIENT_CORPUS`, writes nothing — $1.04 burned. Every sweep. Same for any
generic-noun / common-word slug.

## Two candidate fixes (not mutually exclusive)

1. **Insufficient-corpus backoff (engine, general).** Record per-entity when a
   dream returns `INSUFFICIENT_CORPUS` (the agent already prints the sentinel;
   `DreamResult` could carry an `insufficient_corpus: bool`). On the next
   sweep, extend that entity's effective cooldown (exponential-ish, capped) or
   drop its selection weight until *new* substrate appears (reset the backoff
   when `recent`/`authored` actually grows). Generalises beyond generic-noun
   slugs — catches every junk/dormant entity. Bounded, deterministic, no new
   LLM calls. Knob: `dream_insufficient_corpus_backoff_days` (or a multiplier).

2. **Mention-scan precision (engine, narrow).** Generic-noun slugs are
   inherently collision-prone. Options: require the match to fall outside known
   metadata regions (email headers), or down-weight single-occurrence matches
   of dictionary words. Fragile — risks dropping legit matches. Lower priority
   than (1).

## Data-curation alternative (operator)

`kontakte` is a mis-named junk stub — it should arguably be renamed to the
actual contact, merged, or deleted. That removes *this* instance but not the
class of problem; (1) is the durable fix.

## Decision needed

Build (1) as a small milestone, or treat generic-noun stubs as data-curation
and defer? `wiki dedup` already exists for the merge path.
