---
name: README polish (deferred — needs engine stability or upstream signal)
description: README/doc improvements identified by the 2026-05-02 9-repo audit (basic-memory, mem0, ollama, simonw/llm, nanoGPT, OpenHands, fabric, claude-memory-compiler, karpathy/nanoGPT). Five high-ROI items shipped in that session; the remaining items wait on a precondition.
type: project
---

> Audit context: the 2026-05-02 wrapup compared this README against 9 popular adjacent-niche repos. Five improvements were shipped (CLI extraction, real-artifact excerpt, vault-tour PNG, "What this isn't", star history). What's below is what was identified but explicitly deferred.

## Deferred — needs precondition

- **Hero asciinema cast / GIF showing real `wiki setup → status → compile` flow.** basic-memory (closest cousin) leads with an embedded video and that turned out to be its strongest single differentiator. *Precondition:* engine stable enough to demo without staging — cleanup of one-shot warmup hiccups, plus a clean fresh-install path. Realistic earliest: post-M003 (Collector pattern rolled out so the demo isn't email-only).
- **"Trusted by" / adoption logos.** Standard top-tier pattern (mem0, OpenHands). *Precondition:* actual adopters beyond the author. Not a polish item — a project-stage item.
- **Discord / Slack / Twitter community link.** *Precondition:* willingness to staff support replies for a project labeled "heavy prototype development". Skip unless that flips.

## Considered and explicitly rejected

- **FAQ section.** 0 of 9 surveyed READMEs in the AI/dev-tool segment had one. Not idiomatic for this user-circle. The "What this isn't" 1-liner covers the main HN-style objections without the ceremony.
- **fabric-style "Recent Updates" / changelog inline in README.** Over-promising for a single-author scratch space. The `.ytstack/STATE.md` + commit history play that role internally.

## Audit framework (re-runnable)

When re-evaluating the README in the future, fetch the same 9 references (or their successors) and grade against this checklist — the consistent universal patterns are:

- Real artifact shown (8/9 popular READMEs in this niche)
- TOC + quickstart in first 50 lines
- Hero visual (logo / image / video — one of these)

Atypical patterns (don't add unless there's project-specific reason):

- FAQ (0/9)
- "Trusted by" logos (only mem0, OpenHands — both have actual production adopters)
- "Recent updates" inline (only fabric)
