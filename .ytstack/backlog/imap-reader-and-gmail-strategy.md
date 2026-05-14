# IMAP Reader + Gmail-access strategy

**Status:** IMAP reader — implementing (2026-05-14). Internal-OAuth-app strategy — documented, org-side, not engine work.

## Problem

The mailbox-collector architecture has two reader kinds: `thunderbird-mbox`
(reads what a local mail client already synced) and `gmail-api` (Gmail API
+ OAuth). Neither serves a colleague who:

- runs **no local mail client** → `thunderbird-mbox` has nothing to read, and
- is on a **personal `@gmail.com`** and won't create a Google Cloud project
  → `gmail-api` dead-ends at "Diese App ist blockiert" (a borrowed/sample
  `client_secret.json`, or per-user GCP projects, which is unacceptable UX).

Research (2026-05) on the constraint landscape:

- Basic-auth over IMAP is dead (Google killed it Mar–May 2025).
- **App passwords still work for consumer `@gmail.com`** (not Workspace) with
  2FA enabled — the standard "no GCP project, no local client" path. On
  Google's slow deprecation watch (May-2026 tightening announced) but live.
- Email clients "just work" because they ship a **pre-registered, Google-approved
  OAuth client**. A small tool can't replicate that without Google's security
  assessment for the restricted `https://mail.google.com/` scope.
- An OAuth app with **User Type "Internal"** skips Google verification entirely,
  even for restricted Gmail scopes — but only for members of the owning
  Workspace.

## Two audiences, two answers

| Audience | Answer |
|---|---|
| Has a local mail client (Thunderbird/Apple Mail) | `thunderbird-mbox` — unchanged. The client owns auth+sync. |
| On the org Google Workspace, no local client | `gmail-api` against **one shared "Internal" OAuth app** owned by the org. No per-user GCP project, no verification, refresh tokens don't expire. Org-side setup — see below. |
| On a personal `@gmail.com`, no local client | **`imap` reader** + app password. This document's engine change. |

## Engine change: the `imap` reader

**What.** New `scripts/adapters/mailbox/imap.py` — `ImapReader`, a generic
IMAP `MailboxReader`. New `kind: imap` dispatch in
`scripts/adapters/mailbox/__init__.py:resolve_reader`.

**Auth.** IMAP login: username + app password. `config.yaml` carries only
env-var *names*, never the secret — same discipline as the `all-inkl-procmail`
filter (`imap_pass_env`). Config shape:

```yaml
reader:
  kind: imap
  imap_host: imap.gmail.com
  imap_pass_env: GMAIL_PERSONAL_IMAP_PASS   # app password
  imap_user_env: ""                          # optional; falls back to account.email
  folders: []                                # optional allowlist; empty/absent = all folders
```

**How it integrates.** `ImapReader` implements the existing `MailboxReader`
Protocol (`list_folders` / `scan_metadata` / `scan_deep`) — `EmailCollector`,
`collectors/cli.py`, the curiosity deep-scan backend all consume it unchanged.
`since` is pushed to the server via IMAP `SEARCH SINCE <date>` (date-granular),
then re-filtered in Python against the precise watermark. Stateless: one
connect → search → batched fetch → logout per call. `imapclient>=3.0.0` is
already a dependency.

**Edge cases / failure modes.**

- Missing `imap_host` or unset credential env vars → warning logged, scan
  yields nothing. Collector never crashes (graceful-agnostic, like `gmail-api`).
- Connect/login failure (network, bad app password, bad host) → caught,
  warning, yields nothing.
- A folder that vanished mid-run → skip that folder, continue.
- IMAP `SEARCH SINCE` is **date**-granular, the watermark is a timestamp →
  Python re-filters `date < since` after fetch. Same as the Gmail-API reader's
  `after:` query.
- Undated messages (unparseable Date header) → in delta mode (`since` set)
  they are **skipped**, same rule as `ThunderbirdMboxReader` (otherwise they
  re-report every run — see KNOWLEDGE.md).
- Gmail IMAP exposes `[Gmail]/All Mail` *plus* per-label folders → the same
  message is counted in multiple folders. Pre-existing behaviour of the
  Thunderbird reader too; the optional `folders:` allowlist lets the operator
  scope it (e.g. `folders: ["INBOX"]`).

**Files.** New `adapters/mailbox/imap.py`; edit `adapters/mailbox/__init__.py`
(dispatch + kind-table docstring); `config.example.yaml` (add an `imap`
example); new `tests/test_imap_reader.py`; lxw `config.yaml` reconfigures
`gmail-personal` from `gmail-api` → `imap`.

## Org-side: the shared "Internal" OAuth app (Group 2 — not engine work)

For colleagues on the org Google Workspace, the clean path is **one** OAuth
client, owned by the org, consent screen User Type **Internal**:

1. A Workspace admin creates an OAuth client (Desktop-app type) in an
   org-owned GCP project; scopes `https://mail.google.com/` +
   `gmail.settings.basic`. User Type **Internal** → no Google verification.
2. The Workspace admin allowlists the app once (Workspace API controls).
3. The resulting `client_secret.json` is an installed-app client — it ships
   to every internal install (committed to a private seed location, or
   distributed out-of-band), exactly as Thunderbird ships its client ID.
4. Each colleague runs `wiki gmail-auth <account-id>` once → consent → done.
   Refresh tokens don't expire (unlike External "Testing"-mode test users,
   whose tokens die after 7 days — unusable for an unattended piggyback).

No engine change needed — the existing `gmail-api` reader already supports
this; what was wrong before was a borrowed/sample `client_secret.json` and
the assumption of per-user GCP projects. This is an org-process item, tracked
here so it isn't lost.

## Deferred

- **`docs/architecture.excalidraw`** — the `scanner_email_t` adapter node
  enumerates `thunderbird / gmail / allinkl`; should gain an `imap` line.
  Adding it grows the node's box into the `scanner_calendar` box below it,
  so it needs a reflow (cascade-shift of everything below), not a one-line
  edit. The node already says "multi-backend" so the diagram isn't *wrong*,
  just incomplete. Fold this into the next architecture-diagram sync pass —
  which also owes the four 2026-05-14 collector ports (scan-calendar /
  -browser / -screenshots / -youtube → Registry collectors).
