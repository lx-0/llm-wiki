# Quick-capture setup

The capture collector (`scripts/collectors/capture_collector.py`) ingests
**one-tap cryptic notes and article snippets** from an inbox directory. Each
`.txt` / `.md` / `.html` file dropped in becomes a frontmatter-stamped note
under `raw/captures/` with a *deterministic, content-derived capture-ID*
(`capture-<id>.md`). The same content always yields the same ID, so a re-drop
overwrites rather than duplicates.

Like voice intake, it's path-agnostic — any tool that writes a file into the
inbox works (an iOS Shortcut into an iCloud-Drive folder is the mobile-first
path).

## 1. Pick an inbox path

For **mobile-first capture** (recommended), put the inbox under iCloud Drive so
an iOS Shortcut can write to it:

```bash
mkdir -p ~/Library/Mobile\ Documents/com~apple~CloudDocs/CaptureIntake
```

For **Mac-only** capture, any local path works (`mkdir -p ~/CaptureIntake`).

## 2. Wire it in `config.yaml`

In `<vault>/.wiki/config.yaml`:

```yaml
personal:
  capture_inbox: "~/Library/Mobile Documents/com~apple~CloudDocs/CaptureIntake"
```

The piggyback is on by default with a 1 h cooldown. To keep it
operator-invoked only:

```yaml
piggybacks:
  capture:
    enabled: false
```

## 3. See how the brain read each capture

After captures are compiled into knowledge, the **daily digest** grows a
`## Captures` section listing each capture of the day keyed by its short-id
with the article it became — the brain's interpretation:

```markdown
## Captures

- `a1b2c3d4` · crack the nuts at the bakery → [[knowledge/projects/bakery-run.md]]
- `e5f6a7b8` · idea about tiered pricing → _not yet compiled_
```

This is the observable forward link: you can see, per capture, exactly which
article it fed.

## 4. Correct a wrong reading by ID

If the brain mis-read a capture, drop a **new** capture whose first line
references the wrong one's short-id (the one shown in the digest), led by
`corrects:` or `re:`:

```
corrects:a1b2c3d4 it was a metaphor about focus, not an actual bakery errand
```

The collector recognises the reference to a known capture and tags the new
note `kind: correction` + `corrects: <full-id>` (a plain `Re: <subject>` email
snippet won't false-match — the reference must be a hex capture-id). An unknown
id falls back to an ordinary fresh capture.

> **Status:** capture intake, the digest forward-link, and correction
> *recognition* (this tagging) are live. The automatic step that marks the old
> interpretation superseded and regenerates the affected article on the next
> compile cycle lands in M025-S03 — until then the correction is recorded and
> visible, but the article is not yet auto-rewritten.
