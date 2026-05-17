# Voice punctuate — follow-ups post-2026-05-17 ship

Voice-punctuate shipped 2026-05-17 (commit `6038a6c`). `_punctuate()` live-probed in isolation against gemma4:e4b with 5 sample strings — clean output, eigennamen/substantive correctly cased, hallucination guard not tripped. Open work below.

## 1. End-to-end through collector — untested (REGEL #1)

`_punctuate()` was tested with `PYTHONPATH=scripts uv run python -c "from collectors.voice import _punctuate; ..."`. The actual `run()` path (read inbox file → punctuate → write `raw/voice/<file>.md` with cleaned body + `raw_transcript:` frontmatter → archive source) has not seen a fresh voice note since the feature shipped — all 25 inbox notes drained before `6038a6c` landed.

Verification: drop one fresh voice note via iOS Shortcut, run `wiki collect voice`, check:

- `raw/voice/voice-...md` body is punctuated
- Frontmatter contains `raw_transcript: |` followed by the original verbatim
- `daily/<date>/voice.md` rollup one-liner uses the cleaned form (filename slug too)
- Fallback path: temporarily set `models.classify_model` to a non-existent model OR break Ollama reachability, drop a note, confirm body == raw and no `raw_transcript:` key, no error raised

## 2. Backfill the 25 pre-2026-05-17 voice notes

The 25 notes in `raw/voice/` predating the feature carry raw stream-of-consciousness bodies (`Hallo hallo hallo`, `Doppeltippen`, …). They stay readable but lose grepability + compile-extraction quality.

Optional subcommand: `wiki backfill voice-punctuation [--dry-run]`. Logic:

1. Walk `raw/voice/*.md` where frontmatter has NO `raw_transcript:` key (= unprocessed).
2. For each: parse FM + body, send body through `_punctuate()`.
3. If cleaned ≠ raw: write back with cleaned body + `raw_transcript:` FM key. Filename + slug stay (renaming would break wikilinks).
4. Otherwise: skip silently.

Not urgent — the existing 25 notes are short test transcripts. Worth doing before any longer dictation becomes relevant.

## 3. Punctuation quality observation window

The 5-string probe was happy-path. Watch for:

- **Compound-word splits** (model writes "Doppel tippen" instead of "Doppeltippen" — observed 0/5 in probe but a real risk)
- **Domain-jargon casing** (operator names, project names): right-cased only if the model recognises them. Test with "lego", "obsidian", "claude code", "yesterday" before relying on it.
- **Code/syntax in dictation**: if operator dictates "schreib ein python script", the model might insert weird punctuation. Watch.
- **Hallucination guard tripping false positive**: 3× source length OR empty. If it trips on legitimately verbose punctuation (long German Nebensätze can balloon a 50-char source to 80-char with commas), relax the multiplier.

Trigger to revisit: 5+ voice notes where the operator preferred the raw form. Cheap test: keep `raw_transcript:` always populated so the comparison is one diff away.
