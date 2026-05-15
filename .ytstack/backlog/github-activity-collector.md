# GitHub activity collector — own commits / PRs / comments across orgs

**Priority:** P2 — operator is a top-producer on GitHub (yesterday-ai, lx-0,
Yesterday-AI, personal). Already-structured output substrate, well-rate-limited
API, multi-org coverage. Currently zero wiki coverage of this output stream.

**Origin:** 2026-05-15 substrate-landscape conversation. Identified as
already-structured-and-cheap (REST + GraphQL, 5000/hr) — no schema reverse
engineering, no TCC, no manual export.

## The gap it fills

The operator's commit messages, PR bodies, issue comments, and code reviews
are some of the most thought-through prose they write all week, yet none of it
reaches the wiki. compile.py can distill daily/ entries but the actual technical
content lives in GitHub. A wiki article about a feature gains depth when it
knows which PRs landed it, what the review discussion was, and which issues
it closed.

## Substrate boundary

Two axes:

1. **Own output** (high-signal, primary substrate)
   - commits authored by operator
   - PRs opened by operator (title, body, conversation)
   - issue comments by operator
   - code review comments by operator
2. **Inbound attention** (lower-signal, optional)
   - reviews requested of operator
   - issues assigned to operator
   - @mentions of operator

Phase 1 = own-output only. Phase 2 = inbound. Different substrate classes;
inbound is "attention" similar to gmail-inbox, output is "creation".

Lands in `raw/notes/github/`.

## Source landscape

Already-mapped via `gh` CLI (operator is logged in):

| Endpoint | Use |
|---|---|
| `gh api user/events` | Operator's recent events across all orgs. 90-day rolling window — needs to be persistently archived to outlive the window. |
| `gh search commits --author @me --sort author-date` | Commit-level enumeration. Cross-org. |
| `gh pr list --author @me --state all` | Own PRs per repo. Loop over repos. |
| `gh search issues --commenter @me --sort updated` | Cross-org issue/PR comments. |
| `gh api graphql ...` | One query for everything via `contributionsCollection`. |

GraphQL `contributionsCollection` is likely the single-query shape that beats
the REST patchwork. Verify on impl.

## Phasing

**Phase 1 — own commits + own PRs.** One md file per PR (frontmatter: repo,
number, title, opened_at, merged_at, state, labels; body: PR body + commits
included + final state). Daily rollup file for commits not associated with a
merged PR. Watermark on `events`-cursor or per-repo last-seen-commit-sha.

**Phase 2 — own issue + review comments.** Append to the PR md file for
PR-comments; new daily rollup for issue-comments. Linkable from
people/<reviewer>.md entity pages.

**Phase 3 — inbound (reviews requested, mentions).** Daily rollup. Different
substrate class — treat as attention signal, low-distill weight.

## Anti-slop heuristics

- `gh pr list --state merged` only for stable Phase 1 ingest (open PRs churn).
- Skip `chore(deps):` / dependabot author commits.
- Skip commits with empty bodies and ≤5-word titles unless they're isolated
  (squash-merge PRs get the PR body, not the commit message).
- Org allowlist: yesterday-ai, lx-0, Yesterday-AI, alex0fo (personal),
  alex-claude (work). Skip random forks the operator hasn't actually authored
  in.
- Min lines-changed threshold? Probably no — small fixes can be high-signal.

## Watermark design

`events` API gives `id` (snowflake) per event — newest first. Stash latest
seen `id` per `(actor, scope)`. On next run, paginate until that `id` reappears.
For repos that don't show in `events` (deep history > 90 days), supplemental
sweep via `commits --since` per repo, gated by `last_commit_per_repo` state.

## Open questions

- **GraphQL vs REST patchwork.** `contributionsCollection` GraphQL returns
  commits + PRs + issues + reviews in one shot, scoped to a year. Probably the
  right primary API; REST as fallback for older data.
- **Multi-account.** Operator has multiple GitHub identities (`alex0fo`,
  `alex-claude`, possibly others). Multi-tenant from day one per policy:
  `personal.accounts.<id>.github` with `kind: github-api`.
- **Squash merges.** Commit on main is one squash; PR is the real story.
  Default: ingest PR-level, attach squash-SHA as reference, drop per-commit
  history for squash-merged repos.
- **Private repos.** Some of operator's output is in private orgs (Yesterday-AI
  internal). Default ingest = yes (operator owns the substrate); operator can
  per-org denylist if needed.
- **Code-content vs prose-content.** PR diffs are huge and code-shaped — bad
  fit for distillation. Default: ingest titles + bodies + comments only, drop
  diffs (or summary-only via a pre-distill pass like llm-transcripts).

## Touchpoints

- `scripts/collectors/github.py` — new collector. `supports_account_loop=True`.
- `scripts/adapters/github.py` — `gh` CLI wrapper (already on system) or
  direct PyGithub. Probably `gh api` via subprocess for auth simplicity.
- `state/github-state.json` — per-account `last_event_id`,
  `last_commit_sha_per_repo`.
- New config: `personal.accounts.<id>.github` with `kind: github-api`,
  `username`, `org_allowlist`, `skip_dependabot`, `include_private`.

## Lift estimate

- Phase 1 (PRs + commits via GraphQL contributionsCollection): 1.5 days
- Phase 1 multi-org loop + state file: 0.5 day
- Phase 2 (comments): 1 day
- Phase 3 (inbound): 1 day

**~3-4 days end-to-end.** Phase 1 alone is ~2 days and would cover ~80% of
the value.

## Risks

1. **GraphQL contributionsCollection year-scoped.** History older than 1 year
   needs separate REST sweeps. Mitigation: one-shot backfill via REST,
   incremental via GraphQL.
2. **Squash-merge data loss.** Pre-squash commits exist only on (deleted)
   feature branches. Mitigation: ingest at PR-merge time, not after — but
   that means watermark on PR-merge events, not commits.
3. **Volume.** Operator merges 5-20 PRs/week across orgs. Manageable, but
   per-PR markdown adds up. Mitigation: archive policy after N months
   (`raw/notes/github/<year>/`).
4. **`gh` auth drift.** Memory notes that macOS `gh auth switch` doesn't always
   propagate. Mitigation: collector should `gh auth status` at start, error
   loud if unauthenticated.
5. **Private repo leakage.** A future curiosity-loop or share-vault step could
   expose private commit content. Mitigation: per-source `visibility:
   private|public` frontmatter field, downstream consumers filter.

## Ripens when

- Operator asks "what shipped in Yesterday-AI in March?" and the wiki has no
  answer because it never knew.
- OR entity-pages-state-timeline lands and wants a "recent activity" pane per
  project — GitHub is the natural source.
- OR takes-substrate lands and wants to attribute opinions to specific PR
  review comments.

## Status

Backlog. Probably the cleanest concept in the substrate-extension cluster
because the API surface is fully known and well-documented. Could ship in
parallel with llm-transcripts (no overlap). Strong candidate for Phase 1 of
an M006 substrate-extension milestone.
