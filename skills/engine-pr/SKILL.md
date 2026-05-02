---
name: engine-pr
version: 1.0.0
description: |
  Open a Change Request as a GitHub Pull Request against the engine repo
  (lx-0/llm-wiki). Sibling workflow to the .ytstack/backlog/*.md scratchpad —
  use a PR when the proposal is concrete enough to expect a merge/close
  decision; use the backlog file when it's still formative.
  Handles branch creation, file write, gh-CLI invocation, and PR-body
  formatting consistent with the existing backlog convention.
  Use when: user says "open a PR upstream", "make an engine PR", "file CR
  as PR", "promote backlog item to PR", "open issue on engine repo".
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# Engine PR

Open a Pull Request against `lx-0/llm-wiki` (private, GitHub) for a proposed
engine change. Sibling workflow to the local `.ytstack/backlog/*.md`
scratchpad — both file CRs, but at different maturity levels.

## Overview

Now that the engine repo is on GitHub, the project has two CR-filing
workflows:

| | `.ytstack/backlog/*.md` | GitHub PR (this skill) |
|---|---|---|
| **State** | Scratch, formative, in-flight | Concrete, ready for sign-off |
| **Audience** | Self / future-self during plan-milestone | Engine owner (and any reviewer) |
| **Lifetime** | Lives until promoted, dropped, or scoped into a milestone | Lives until merged or closed |
| **Mechanism** | Markdown file committed to `main` | Branch + PR via `gh pr create` |
| **When** | Idea fresh out of conversation; touchpoints unclear; multiple open questions | Touchpoints clear; ready to merge if owner agrees |
| **Reviewable diff?** | No (just a doc) | Yes (when the PR contains the actual implementation) |

A backlog item can be **promoted** to a PR once it's matured — same content,
different shipping mechanism. Don't dual-track: when promoting, delete the
backlog file in the same PR or in a follow-up.

## When to use this skill (not the backlog)

Open a PR when **all** of these are true:

- The change is concrete — paths, files, behavioral shape are nailed down
- The change is small enough to review in one sitting (< ~500 LOC, ideally < 200)
- A decision is wanted from the engine owner: merge, close, or specific feedback
- Either: implementation is included in the PR (preferred), or the PR contains
  a tight design doc that the owner will respond to with merge / close /
  request-changes

If any of the above is shaky → file as `.ytstack/backlog/<slug>.md` instead.
The backlog is the right home for in-flight thinking; PRs are for asks.

## Workflow

### Step 1 — Branch from `main`

```sh
cd <engine-repo>          # path to your local engine clone (NOT the vault's .wiki/ subdir)
git fetch origin
git checkout -b cr/<slug> origin/main
```

Branch naming:

- `cr/<slug>` — change request, doc-only or design proposal
- `feat/<slug>` — new feature with implementation
- `fix/<slug>` — bug fix with implementation
- `refactor/<slug>` — pure code reorganization, no behavior change
- `docs/<slug>` — docs-only

`<slug>` is kebab-case, ≤ 5 words. Match the GitHub label vocabulary where
possible (`enhancement`, `bug`, `documentation`).

### Step 2 — Make the change

Either:

- **Doc-only PR (CR mode):** write a single markdown file, typically under
  `.ytstack/backlog/<slug>.md` or `docs/proposals/<slug>.md`. Same body
  structure as a backlog item (Problem / Proposed solution / Touchpoints /
  Edge cases / Open questions / Source).
- **Implementation PR:** the actual code change. Keep the PR scope tight —
  if you find yourself touching > 5 files outside the headline area, split.

### Step 3 — Commit

Follow the repo's commit-message convention (terse subject line, optional
body, `Co-Authored-By` trailer if AI-paired). Don't auto-amend — always new
commits per CLAUDE.md `Git Safety` rule.

### Step 4 — Push + open PR

```sh
git push -u origin cr/<slug>

gh pr create \
  --repo lx-0/llm-wiki \
  --base main \
  --head cr/<slug> \
  --title "<imperative subject, < 70 chars>" \
  --body "$(cat <<'EOF'
## Summary
<1–3 bullets>

## Why
<the load-bearing reason — incident, gap, request, …>

## Proposed change
<what concretely changes — paths, behavior, config>

## Touchpoints
- file:line — what changes
- file:line — what changes

## Edge cases
- <case> → <handling>

## Open questions
- <question> — <suggested default>

## Source
<conversation/incident reference if applicable>
EOF
)" \
  --label enhancement   # or bug / documentation / refactor
```

Available labels (existing in repo): `bug`, `documentation`, `enhancement`,
`question`, `help wanted`, `good first issue`, `duplicate`, `invalid`,
`wontfix`. Pick one or two; don't over-tag.

### Step 5 — Confirm + return URL

```sh
gh pr view --repo lx-0/llm-wiki --json url,number,state | jq
```

Always return the PR URL to the caller — they want to review it.

## Edge cases

- **Repo not cloned locally / wrong remote.** This skill assumes a local
  upstream working copy of `https://github.com/lx-0/llm-wiki` exists at
  `<engine-repo>` and has `origin` pointing at the GitHub repo. If you also
  have a vault-internal `.wiki/` clone, that's a separate copy (it may have a
  local `file://` remote pointing at your upstream working copy) — pushes from
  the `.wiki/` copy won't reach GitHub. Always run `git remote -v` first if
  you're unsure which clone you're in, and cd into the upstream working copy
  for any push to GitHub.
- **gh not authenticated.** Surface clearly; don't try to bypass.
  `gh auth status` first if uncertain. Multi-account: `gh auth switch` plus
  `gh auth setup-git` (macOS keychain quirk per CLAUDE.md Git Safety section).
- **Branch already exists.** Either continue work on the existing branch
  (then it's a PR update, no new PR needed) or pick a different slug.
  Never force-push to overwrite.
- **PR template missing.** If the repo grows a `.github/PULL_REQUEST_TEMPLATE.md`,
  let `gh` fill it instead of the body string above. Check
  `.github/pull_request_template.md` before constructing the body.
- **WIP / draft mode.** Use `gh pr create --draft` if the PR isn't ready for
  review yet — open question lists, missing tests, exploratory.
- **Promoting a backlog item to PR.** Read the backlog file, restructure into
  PR body, `git rm .ytstack/backlog/<slug>.md` in the same branch, push +
  open PR. The backlog removal goes with the PR so there's a single source
  of truth at any moment.
- **Cross-machine work.** The Sync.app working copy is canonical. Work there,
  not in the vault-internal clone. After merge, both copies update on next
  sync / pull.

## Rules

- **Never auto-merge.** Even on a 1-person repo, the explicit accept ritual
  matters — surface the PR, return the URL, stop.
- **Never push to `main` directly.** Even tiny fixes go via branch + PR,
  to keep the audit trail consistent. The repo is on `main` as default
  branch and that branch is sacred.
- **One concern per PR.** If during the change you notice a related-but-
  separable issue, stub a `.ytstack/backlog/<slug>.md` for it instead of
  bundling. Reviewability degrades fast with multiple concerns per PR.
- **Body fidelity.** The PR body should be readable cold by anyone with no
  conversation context — write the prompt the engine owner needs to make
  the merge decision, not "as we discussed earlier".
- **Don't `git stash`** (CLAUDE.md `Git Safety`). If you need to switch
  branches mid-work, commit first.
- **Always `git branch --show-current`** before any commit, per CLAUDE.md.

## Example

User: "open a PR for the clippings-sweep idea — it's concrete enough now"

Skill flow:

1. Read `.ytstack/backlog/clippings-sweep.md` (already exists from earlier
   conversation).
2. `cd <engine-repo> && git checkout -b feat/clippings-sweep origin/main`
3. Write `scripts/sweep-clippings.py`, hook it into `flush.py:PIGGYBACK_TASKS`,
   add config flag in `wiki_config.py`, document in `AGENTS.md`.
4. `git rm .ytstack/backlog/clippings-sweep.md` — promotion replaces backlog.
5. Commit; push.
6. `gh pr create --title "feat: pre-compile sweep of vault Clippings/ → raw/articles/" --body ... --label enhancement`
7. Return PR URL.
