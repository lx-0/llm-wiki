# Report a problem to the engine

When the wiki itself misbehaves — CLI crash, stale state, schema mismatch,
missing feature, prompt regression — file an issue against the engine repo
`lx-0/llm-wiki`. Operators **report**; they do not PR. PRs against the engine
are the engine maintainer's job.

## Prerequisites

- `gh` CLI installed and authenticated (`gh auth status`).
- Operator wants the bug/feature on record. If unsure, just log it in their
  vault's `.ytstack/backlog/<slug>.md` first — that's local and cheap.

## When to file

Open an issue when **all** are true:

- The problem reproduces (or you have a clear failing log).
- It's not already filed (`gh issue list --repo lx-0/llm-wiki --search "<keyword>"`).
- The operator gave the go-ahead — never file as a side effect.

Skip the issue, keep it local in the vault's backlog when:

- The bug is operator-specific (their config, their data, their machine).
- It's still formative — multiple open questions, no clear ask.
- It would just say "I wonder if…" — not enough signal yet.

## The flow

### Step 1 — search first

```sh
gh issue list --repo lx-0/llm-wiki --state all --search "<keyword>"
```

If a matching issue exists: add a comment with new evidence instead of opening
a duplicate.

### Step 2 — gather evidence

Surface concrete:

- **Command** that triggered it (full args).
- **Output** — exit code, stderr, the actual error line. Not paraphrased.
- **Environment** — engine version (`wiki status` or git SHA of `.wiki/`), OS,
  Python version if relevant.
- **State** — only if relevant (e.g. `state.json` excerpt, log tail).
  Never paste secrets, full transcripts, or PII.

### Step 3 — open the issue

```sh
gh issue create \
  --repo lx-0/llm-wiki \
  --title "<imperative subject, < 70 chars>" \
  --label bug \
  --body "$(cat <<'EOF'
## What happened
<one paragraph — the surface symptom>

## Reproduce
1. <step>
2. <step>

## Expected
<what should happen>

## Actual
<what happened, with command output>

```
<paste relevant log excerpt — trimmed>
```

## Environment
- engine: <git SHA or version>
- OS: <macOS / Linux + version>
- Python: <version>
- vault layout: <stock / has piggyback X / has collector Y>

## Notes
<anything optional — what you tried, suspected cause>
EOF
)"
```

Label choices (existing in repo): `bug`, `enhancement`, `documentation`,
`question`, `help wanted`, `good first issue`. Pick one, maybe two. Don't
over-tag.

### Step 4 — confirm

```sh
gh issue view --repo lx-0/llm-wiki --json url,number,state
```

Return the URL to the operator.

## Rules

- **Operators report, don't PR.** Never `git push` to the engine repo, never
  `gh pr create` against `lx-0/llm-wiki`. Issues only.
- **Search before opening.** Duplicates are noise.
- **No secrets in the body.** Paths, tokens, raw substrate — strip before posting.
- **One concern per issue.** If you find a second bug while writing the first,
  file it separately.
- **Body fidelity.** Anyone reading cold should be able to triage — no "as we
  discussed", no conversation references.
- **Don't auto-file.** Operator green-light per issue, every time.

## Example

```text
Operator: "compile crashed with exit-1 and empty stderr on the YouTube notes — file that"

1. gh issue list --repo lx-0/llm-wiki --search "compile exit-1 empty stderr"
   → 0 matches.

2. Evidence:
   - command: wiki compile
   - exit code: 1, stderr: (empty)
   - source: raw/notes/youtube/<file>.md (148 KB)
   - engine SHA: 2ff499b

3. gh issue create --repo lx-0/llm-wiki --label bug \
     --title "compile: silent exit-1 on long YouTube notes (~150 KB)" \
     --body "..."

4. Return https://github.com/lx-0/llm-wiki/issues/<n>
```
