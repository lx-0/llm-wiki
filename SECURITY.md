# Security Policy

## Supported versions

llm-wiki is at version 0.x. Only the `main` branch is currently supported. There is no LTS line and no backporting.

## Reporting a vulnerability

**Do not open a public issue for security reports.**

Instead, report privately via one of:

- GitHub's [private vulnerability reporting](https://github.com/lx-0/llm-wiki/security/advisories/new) feature on this repo.
- Email the maintainer (see commit author metadata for current address).

When reporting, include:

- A description of the vulnerability and the impact.
- Steps to reproduce or a proof-of-concept.
- The commit SHA / version where you found it.
- Any suggested mitigation if you have one.

You'll get an acknowledgement within 7 days and a fix or status update within 30 days for valid reports. Trivial issues may be fixed publicly without an advisory; high-severity issues will get a coordinated disclosure with a fixed-version advisory.

## What counts as a vulnerability

In scope:

- Code injection via untrusted ingest sources (HTML clippings, audio transcripts, email bodies) reaching the compile prompt or shell.
- Path traversal in any of the file-handling scripts (`process-inbox.py`, `compile.py`, `flush.py`, `seed.py`, hooks).
- Credential leaks through logs, error messages, or staged transcripts (e.g. `flush-context-*.md`).
- Webmail/IMAP integrations leaking session state across accounts.

Out of scope:

- Issues that require an attacker to already have local filesystem access to the vault directory (the threat model assumes a trusted local user).
- Configuration mistakes that expose `config.yaml` (which holds credentials) — `config.yaml` is gitignored; if you committed it, that's a setup issue, not a vulnerability in the engine.
- Vulnerabilities in upstream dependencies that don't have an exploitable reach in llm-wiki's code paths. (For those, file with the upstream project; we'll bump the dep when a fix lands.)

## Hardening notes

- `config.yaml` and `.env*` are in `.gitignore` — keep credentials out of git.
- The webmail-procmail save endpoint (currently used for All-Inkl integrations) is destructive on empty body — see the gotcha in `.ytstack/KNOWLEDGE.md` "Procmail Webmail API". Don't call save endpoints during exploration.
- The flush pipeline never deletes transcripts that haven't been confirmed-persisted — see the "no gap between capture and persist" invariant in the same file.
