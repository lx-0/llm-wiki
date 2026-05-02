# Compiler Optimization Suggestions

## Goal

The compiler can spot patterns in collector data (recurring senders, redundant labels, manual sorting that could be a rule, …) but it can't act on the source system itself. **Optimization Suggestions** is the bridge: the compiler proposes concrete actions, the human approves per-action, a separate script executes.

## Suggestion vs. curiosity request

These two outputs of the compiler look similar but have different lifecycles:

| | Curiosity requests (`raw/requests/`) | Optimization suggestions (`raw/suggestions/`) |
|---|---|---|
| **Direction** | Compiler wants **more data** | Compiler proposes **changes to the source** |
| **Executor** | Scanner, automatic (`--follow-requests`) | Human approves → script executes |
| **Risk** | Low (read-only) | Medium (mutates external data) |
| **Lifecycle** | `pending → processing → done` | `pending → approved/rejected → executed` |

## Inputs to the optimizer

1. **Collector data** in `raw/notes/<source>/` — metadata, deltas, deep scans
2. **Existing rules / config** of the target system, parsed into a normalised form
3. **Wiki knowledge** (`knowledge/`) — e.g. "project X is archived" → suggest archiving its messages

## Suggestion file format (YAML)

```yaml
# raw/suggestions/<slug>-<date>.yaml
type: optimization-suggestion
category: email-filter        # arbitrary; UI groups by this
source: compile
priority: high                # high | medium | low
risk: low                     # low | medium | high
target: "Short headline"
rationale: "Why this is being suggested, in plain text"
actions:
  - type: create-rule
    account: <account-id>
    status: pending           # pending | approved | rejected | executed | failed
    rule:
      name: "..."
      condition: '...'
      action: "Move to folder"
      folder: "..."
  - type: imap-move
    account: <account-id>
    status: pending
    search: ['FROM', 'sender@example.com']
    source_folder: "INBOX"
    target_folder: "INBOX/Archive"
    estimated_count: 317
dry_run: |
  Free-form preview of what executing all actions would do.
created: 2026-04-13
```

Key design points:

- **Per-action status**, not per-suggestion. A suggestion may bundle several actions; the human can approve some and reject others.
- **dry_run** is mandatory — the executor renders it for the human before any action runs.
- **estimated_count** for IMAP-move-style actions so the human sees blast radius.

## Two execution paths

The optimizer's most natural target is **email**, because:

- Most users have many accounts and folders.
- Email systems expose programmatic access (IMAP, server-side filter files).
- Patterns are easy for the compiler to spot (recurring senders, frequent manual moves).

For email specifically, two execution paths are useful:

### A. Server-side filter rules (future mail)

Each provider has its own format:

- **Thunderbird** writes `msgFilterRules.dat` per account. Plain-text, line-based. Thunderbird must be closed when the file is rewritten — it overwrites on shutdown.
- **All-Inkl / kasserver** has a Webmail API that exposes Procmail-style rules; rules apply server-side and take effect immediately.
- **Gmail** has filter rules via the Gmail API (OAuth2).

### B. IMAP actions (existing mail)

For mutating already-delivered messages:

```python
from imapclient import IMAPClient

with IMAPClient(host, ssl=True) as client:
    client.login(user, password)
    client.select_folder('INBOX')
    uids = client.search(['FROM', 'sender@example.com'])
    client.move(uids, 'INBOX/Archive')      # move
    client.add_flags(uids, ['$label2'])      # tag
    client.add_flags(uids, [b'\\Seen'])      # mark read
```

IMAP is server-side; the mail client can stay open and will sync automatically.

**Tag mapping** (Thunderbird ↔ IMAP keywords): `$label1=Important`, `$label2=Work`, `$label3=Personal`, `$label4=Todo`, `$label5=Later`.

## Suggestion prompt (compiler-side)

When an email-scanner source is being compiled, the compiler runs a second LLM pass with a prompt like:

> Given this email-scanner data and the existing filter rules, propose 0–N optimisations. Strict rules: no duplicates (check both rule sets), use exact email addresses, minimum 5+ messages per pattern, prefer extending existing rule groups over creating new ones, be conservative.

Output: zero or more YAML files in `raw/suggestions/`.

Anti-pattern to avoid: don't propose rules for one-off senders. The threshold (5+ messages) and the "extend existing groups" preference are critical to keep noise low.

## Executor

A separate script (`execute-suggestions.py`) reads the YAML, prompts the human per-action (or accepts `--approve FILE N` for non-interactive use), and dispatches to the right backend:

- **Filter file mutation** — parse → patch → write (with `.bak`)
- **IMAP action** — login → search → mutate
- **Audit log** — every executed action gets a line in `raw/suggestions/_audit.log`

## Failure modes

- **Mail client open during file rewrite** → it overwrites the patched file on close. Solution: detect open clients and refuse, or use server-side APIs where available.
- **Stale credentials** → IMAP login fails. Surface clearly in the executor's output.
- **Folder doesn't exist** → IMAP move fails. Pre-flight check.
- **Race with the user manually moving mail** → `estimated_count` may be off. Re-run the search before moving and warn if delta > 20%.

## Generalisation

The pattern isn't email-specific. Any source where the compiler spots a repeatable manual action — calendar event categorisation, browser bookmark tags, file-system organisation — can use the same suggestion / approve / execute split. Email is just the proof-of-concept because it has the richest API surface.
