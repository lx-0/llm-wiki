---
title: "Q1 Review with Jane Doe"
type: transcript
collector: jamie
meeting_date: 2026-04-15
attendees:
  - Alex Wegener
  - Jane Doe
short_id: abc
---

## Summary

Quarterly review with Jane Doe (VP Eng, Acme). Covered Q1 retrospective on the Yesterday platform, the inference-cost-framing disagreement, and pending intros. Jane committed to share the Q3 deck by next Friday; the operator committed to set up an intro to Bob from Acme's product team. Infra capacity is the open blocker.

## Transcript

**Alex:** Thanks for making time, Jane. Want to go over the Q1 numbers and where we landed on the inference-cost framing?

**Jane:** Yeah, of course. So I still think the per-team budget model is going to bite you, but I get why you're trying it as a Q1 experiment. I'll send the Q3 deck by next Friday with my counter-proposal — we have something workable internally.

**Alex:** Appreciated. Friday the 22nd?

**Jane:** Yeah, by EOD April 22nd.

**Alex:** Perfect. While we're on intros — I'll set up the Bob intro this week. He's been asking about the platform architecture and I think you two should connect.

**Jane:** Sounds good. Just CC me whenever you're ready.

**Alex:** One thing that's still blocking us — we're waiting on the infra-capacity decision from Hetzner. Their team said by end of April but nothing concrete yet. Anything you'd do differently if you were us?

**Jane:** Honestly, if Hetzner doesn't come through, OVH has spare capacity right now. But I wouldn't switch yet. Wait it out.

**Alex:** What if we did a small canary on OVH just to validate? Hypothetically.

**Jane:** Hypothetically, sure, but I wouldn't actually do it. Too much complexity for too little learning.

**Alex:** Fair. Anything else on your end?

**Jane:** That's it from me. Talk soon.

## Expected extraction

(This block is documentation for the test harness, not part of the transcript content the LLM compiles. The LLM rule says to extract commitments from the Transcript section; this block tells the test harness what counts as "correct".)

- **Jane → Action Item**: Send the Q3 deck 📅 2026-04-22 (with counter-proposal on inference-cost framing)
- **Operator → Action Item on project page**: Set up Bob intro (this week, no hard date)
- **Jane → Open Threads** (operator-side concerns, blocked): Waiting on Hetzner infra-capacity decision (mentioned 2026-04-15)
- **NOT extracted** (hypothetical / rejected): "small canary on OVH" — that was discussed as a hypothetical and Jane explicitly rejected it. The LLM should skip.
- **NOT extracted** (closing pleasantry): "Talk soon" — not a commitment.
