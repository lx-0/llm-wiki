# Gmail-API for consumer-Gmail accounts (gmail-personal gap)

**Status:** unresolved gap — engine architecture supports the use case in principle, but Google's OAuth model has no path that satisfies the operator's full constraint set.

**Date:** 2026-05-17

## Problem

`personal.accounts.gmail-personal` declares `filter.kind: gmail-api`. Suggestions
backend needs OAuth tokens to push label/move actions + create persistent
server-side filter rules via Gmail REST API. The OAuth flow requires the
account's Gmail address to be authorized against SOME Cloud project.

`gmail-personal` is a consumer Gmail account (`Wegener.Alexander@gmail.com`),
not in any Google Workspace.

## Operator's hard constraints (locked across this session)

1. **Don't reduce features.** Server-side persistent filter creation must
   stay possible (= must keep using Gmail REST API, not switch to IMAP-only).
2. **No coupling to `llm-wiki-496408`.** The shared Workspace project owned
   by yesterday-ai.de must not list gmail-personal as a Test user, must not
   share its OAuth client, must not have any cross-coupling with this
   consumer-Gmail account. Ever.
3. **No requirement that consumer Gmail users create their own Cloud
   project.** "Most private Gmail users don't have a Google Cloud project"
   — that setup is unrealistic for normal users.

## Google's OAuth model — what's structurally possible

For a consumer `@gmail.com` account to authorize a Cloud project's OAuth
client for restricted scopes (e.g. `mail.google.com`), exactly one of these
must hold:

| Path | What it requires | Why it doesn't fit |
|---|---|---|
| Internal user-type | App's project must be in a Workspace; user must be a Member of that Workspace | Consumer Gmail can't be in any Workspace |
| External-Testing + Test users | The consumer email must be on the project's Test users list | Violates constraint 2 |
| External-Production + Verification | Google must verify the app (brand verification + security assessment for restricted scopes) | Multi-month process; needs verifiable web domain + privacy policy + ~$15k security audit fee; not realistic for personal projects |
| Own Cloud project | User creates own GCP project, places own OAuth client at `.claude/oauth-client-<id>.json` (engine supports this since `d0e1023`) | Violates constraint 3 |

The intersection of operator's constraints with Google's allowed paths is
**empty**. No engineering trick around it — Google's OAuth design simply
doesn't have a path for "consumer Gmail authorizes app + zero per-user
setup + no own project + no app verification".

## Current engine state

- `0a12388` consolidated all Google integrations to fall back to
  `google-oauth-client.json` (PRIMARY) → `gmail-oauth-client.json` (FALLBACK).
- `d0e1023` added per-account override: `.claude/oauth-client-<account-id>.json`
  takes precedence over the global. Engine-side this is correct multi-tenant
  architecture, but it requires the operator to provide the per-account file
  — which means a per-account Cloud project.
- gmail-yesterday (Workspace account in yesterday-ai.de) works fully via the
  shared `google-oauth-client.json` + `llm-wiki-496408` in Internal mode.
- gmail-personal (consumer Gmail) is blocked. `wiki gmail-auth gmail-personal`
  returns Google error 403 `org_internal` when attempting the shared client
  flow.

## What would actually unblock gmail-personal

Exactly one of these would have to give:

1. **Engine ships a Google-verified OAuth app.** `lx-0/llm-wiki` goes through
   Google's app verification (brand-verification + restricted-scope security
   assessment). After verification, ANY Gmail user (including consumer
   accounts) can authorize the engine's shipped OAuth client without per-user
   setup or own Cloud project. This is the path Mailbird / Mimestream /
   Superhuman take. Multi-month operator investment; ~$15k security audit.

2. **Drop the restricted scope requirement.** Engine could request only
   `gmail.modify` + `gmail.settings.basic` (both Sensitive, not Restricted).
   Sensitive scopes have a lower verification bar (brand-verification only,
   no security assessment); in External-Production-Without-Verification mode
   they show users an "unverified app" warning that's click-throughable.
   Still requires the project's owner to publish + accept the warning UX.
   Operator still has to set consent screen up somewhere.

3. **Accept feature reduction for gmail-personal.** Drop
   `filter.kind: gmail-api` from this account's config. Suggestions backend
   silently skips `create-rule` actions for this account; `imap-move` actions
   still execute via the existing IMAP credentials (App-Password). Server-side
   filter creation: operator does it manually in Gmail UI on a one-time basis
   per filter. This is what most personal-Gmail integrations do in practice.

## What I won't propose again without operator green-lighting

The operator has explicitly rejected, repeatedly, with escalating frustration:

- Adding gmail-personal to `llm-wiki-496408` Test users (any variant)
- Setting up a separate Cloud project owned by the personal account
- Removing `filter.kind: gmail-api` from gmail-personal config (= feature reduction)
- Switching to XML-import or other engine-side workaround paths

Any future arc on this gap must come from operator deciding to relax one
constraint, OR a new path I haven't identified.

## Lessons baked into memory (next session)

- `feedback_dont_overpromise_shared_oauth_for_consumer_gmail.md` — the
  consolidation framing in `0a12388` was wrong because it didn't audit
  per-account identity types before assuming "one project covers all"
- `feedback_dont_repropose_rejected_options.md` — once the operator vetoes
  an option (feature reduction, per-account Cloud project, test-user-add),
  don't bring it back rephrased
- `project_per_account_oauth_resolver.md` — engine-side architecture
  (commit d0e1023) for future agents to know it exists
