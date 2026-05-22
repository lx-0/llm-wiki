# Consumption / curiosity intake axis — entertainment & media-consumption as persona-coverage

**Status:** thematic cluster, not a single wedge. Groups the existing consumption-side collector pitches under one persona-axis and records the priority reframe from the 2026-05-22 substrate-landscape conversation.

**Origin:** 2026-05-22. Operator asked whether playlists/histories from YouTube, Spotify, SunoFlow, browser, etc. are sensible intake or just clutter the self-cartography with junk. Outcome: the *blindspot/persona-coverage* frame wins over the *signal-density* frame. Canonical decision: `.ytstack/DECISIONS.md` 2026-05-22 ("Intake is valued by persona/blindspot coverage, not per-source signal-density"). Policy restated in CLAUDE.md "Hard rules" + AGENTS.md "Evaluating a new intake channel".

## The axis this covers

Work-substrate (mail / calendar / gmeet / jamie / docs) has a systematic bias: it captures the **intentional, professional** operator. The non-work persona — curiosity, leisure, cultural consumption, mood, what occupies attention outside of deliverables — falls through that net. An honest self-cartography that omits it has a built-in blindspot. This cluster is the consumption/curiosity axis that closes it.

## The two reframes that make it non-junk

1. **Coverage, not yield.** A single Spotify track or YouTube view is near-zero signal per row — but the *aggregate* ("3 weeks of Japanese-learning podcasts", "sudden Roman-history deep-dive") is exactly the persona signal nothing else captures. Clutter is already solved engine-side (`compile-role: source-only` + `daily/`-aggregation keep these out of per-item `knowledge/`), so low-signal-per-row is not a disqualifier.
2. **Content granularity is the actual gap.** Browser-history already crudely covers leisure *attention* at domain level (it knows you hit `youtube.com` 200×). What's dark is the *content* layer — what those 200 visits were *about*. That's the value these collectors add, and the reason "we already have browser-history" doesn't close the axis.

## Guardrails (so it doesn't become firehose-maximalism)

- **Axes, not channels.** Spotify + YouTube-watch-history + podcasts + Netflix mostly measure the *same* cultural/curiosity-consumption axis. Strong case for the first channel on the axis; steep diminishing returns stacking the rest. Pick for axis-coverage, not source-count.
- **Synthesis is the gate.** None of these pays off as raw `raw/` growth. They only earn their place if the dream-cycle / a persona entity-page consumes them into a "what occupies the operator" portrait. If the consumer doesn't exist yet, the consumer is the prerequisite, not the collector.

## Candidate channels (existing per-collector backlog files)

| Channel | File | Axis fit | Notes |
| --- | --- | --- | --- |
| Spotify / Apple Music listening | `music-listening-collector.md` | consumption/curiosity (primary) | **Re-valued by this decision.** The file currently frames it "never primary, weight low, correlation-ribbon only" — that's the superseded signal-density stance. Under the new policy it's a primary blindspot-coverage candidate. Update the file's framing if/when picked up. |
| YouTube watch-history | `youtube-intake.md` | consumption/curiosity | Distinct from the *shipped* youtube content-ingest (which ingests videos the operator deliberately drops in). Watch-history = passive feed; needs an engagement filter (saved/replayed/searched/completed) to beat pure noise. |
| Browser content | `browser-history-collector.md` | attention (domain) → content gap | Already domain-aggregated; the content layer is where the curiosity signal lives. |
| Reading highlights | `reading-highlights-collector.md` | curiosity/learning | Readwise/Kindle/Pocket — *intentional* consumption, higher signal than passive feeds. |
| Suno generations | `sunoflow-collector.md` | **production, NOT this axis** | Operator *output/creation*. Belongs to the portrait but on the production axis. Listed here only to mark the boundary — it is not the better candidate just because the operator authors it (criterion-switch error during the conversation). |

## Recommended sequencing (when capacity allows)

1. **First mover on the axis** = the channel with the best content-granularity-per-effort. Reading-highlights (`reading-highlights-collector.md`) is intentional consumption (highest signal, lowest noise) and a clean candidate for first.
2. **Build / confirm the synthesis consumer** (persona entity-page or dream-cycle pane that surfaces "what occupies the operator") in the same arc — otherwise (1) is dead raw weight.
3. Only then weigh a *second* axis-mate (music or watch-history), expecting diminishing returns and gating on an engagement filter for the passive feeds.

## Open questions

- Engagement filter for passive feeds (Spotify plays, YouTube autoplay): what counts as attention-bearing vs. background? (saved / replayed / searched / completed / dwell-time?)
- Does the persona entity-page exist yet as a synthesis target, or is that the real prerequisite milestone for this whole cluster?
- Privacy/sensitivity posture for consumption data (`sensitivity:` frontmatter as with health?).

## Related

- `.ytstack/DECISIONS.md` 2026-05-22 — canonical policy.
- `gbrain-comparison.md` / `karpathy-comparison.md` — firehose-maximalist intake philosophy reference.
- `curiosity-dashboard.md` / `curiosity-topic-as-search-query.md` — adjacent curiosity-loop consumers.
