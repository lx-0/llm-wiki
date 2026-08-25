# Backlog: bash `[[ … ]]` parsed as wikilinks — false positives + publish corruption

Found by the 2026-08-25 full-state audit. `WIKILINK_RE` matches bash
double-bracket test syntax in live lines (outside code fences): `[[ -f
"$logfile" ]]`, `[[ "$status" == "complete" ]]`, `[[ $size -gt 104857600 ]]` —
seen in `concepts/bash-script-api-conventions.md`,
`concepts/container-log-rotation-truncate-strategy.md`, and as index junk rows.

Three consumers are affected:
1. lint/links: false-positive "broken link" ERRORS (inflates the 321 count).
2. publish render: normalize_links DEGRADES these spans to plain text — content
   corruption class in the mirror (inline code with `[[ … ]]` loses brackets).
3. index: junk rows like `[[! -o monitor]]`.

## Fix shape

Grammar-level guard in `core/links.py` (single source of truth): a target that
starts/ends with whitespace, or starts with `!`/`-`/`$` shell-test shapes, is
NOT a wikilink (Obsidian itself does not resolve `[[ x ]]` with leading space —
verify against Obsidian behavior first, live-probe rule). Add fixtures for all
observed shapes; re-run links/lint counts before/after to measure the class.
Also audit already-published articles for degraded spans once fixed (publish
will re-send them via content-hash change automatically).
