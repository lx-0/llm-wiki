---
title: "Yesterday Platform"
type: project
aliases: ["yesterday-platform", "yesterday-ai"]
tags: [project, yesterday, infra, llm-gateway]
compiled_from:
  - "raw/notes/yesterday-platform/2026-04-01--spec.md"
  - "daily/2026-04-08.md"
  - "raw/transcripts/jamie/2026-04-15--q1-review--abc.md"
created: 2026-04-01
updated: 2026-04-15
---

# Yesterday Platform

> The internal AI-services platform: agent hosting + LLM gateway + secrets + GitOps deployment via ArgoCD. Active, post-Q1 milestone in flight (M005 entity-pages layer on the wiki engine, dashboard pane being added). Owner is Jane Doe externally; the operator is technical lead.

## State
- **Status:** active
- **Stack:** Next.js 15 + tRPC v11 + Drizzle + Hono + LiteLLM Gateway
- **Owner:** [[knowledge/people/jane-doe]] (external sponsor); operator is tech lead
- **Deployment:** ArgoCD on Hetzner-K8s, Infisical for secrets
- **Current milestone:** M005 wiki entity-pages layer (this repo) + dashboard pane

## Action Items
- [ ] Ship M005 S03 dashboard pane 📅 2026-05-22 ⏫
- [ ] Decide on auth-provider migration (better-auth vs. NextAuth retention)
- [ ] Draft Q3 deck for Jane 📅 2026-05-20

## Open Threads
- Waiting on infra-capacity decision from Hetzner (mentioned 2026-04-05)
- Pending review: tRPC v11 vs. v10 retention in the legacy gateway endpoints

## What it is
The Yesterday platform is the umbrella for the agent-services + LLM-gateway stack used internally and by Paperclip. The wiki engine ([[knowledge/projects/llm-wiki]]) is one consumer; agent hosting is the other primary surface. Frontend on Next.js App Router; backend Hono + tRPC; deploys via ArgoCD with Infisical for secrets distribution. Smart routing through LiteLLM with per-virtual-key spend caps.

## Key Decisions
- **2026-04-15** — Q1 inference-cost framing locked: per-team budgets via virtual keys, not org-wide caps. Jane disagreed but accepted as a Q1 experiment.
- **2026-04-08** — tRPC v11 over v10 confirmed; ESM compatibility in Next.js 15 App Router was the deciding factor.
- **2026-04-01** — ArgoCD over Flux selected; team familiarity won over feature parity.

## See also
- [[knowledge/people/jane-doe]] — external sponsor, quarterly reviews
- [[knowledge/concepts/inference-cost-framing]] — the Q1 disagreement
- [[knowledge/projects/llm-wiki]] — consumer / sibling project
- [[knowledge/concepts/argocd-gitops]] — deployment pattern

---

## Timeline
- **2026-04-15** | `raw/transcripts/jamie/2026-04-15--q1-review--abc.md` — Q1 roadmap reviewed with Jane; inference-cost framing locked as Q1 experiment.
- **2026-04-08** | `daily/2026-04-08.md` — Architecture review with Jane; tRPC v11 over v10 confirmed.
- **2026-04-01** | `raw/notes/yesterday-platform/2026-04-01--spec.md` — Initial platform spec doc.
