---
status: implemented
---

# Wiki Config — Single Source of Truth

All tunable parameters live in `<wiki>/.wiki/config.yaml`. Implemented.

## Why YAML, not plugin settings UI

The scripts run independently of any Obsidian process (hooks, piggybacks, CLI). Plugin settings are stored in `<vault>/.obsidian/plugins/.../data.json` — the scripts can't (and shouldn't) know that path. YAML at a known location is:

- Directly editable (Obsidian renders YAML readably).
- Versionable (git).
- Easy to validate (dataclass schema).
- Plugin-readable / -writable when needed.
- User-readable when no plugin is running.

## Architecture

- `.wiki/config.yaml` — user overrides only. Anything missing falls back to defaults.
- `.wiki/scripts/wiki_config.py` — dataclass-backed loader. `CONFIG` is a module-level singleton.
- `.wiki/wiki config get|set|keys|wizard` — bash CLI wrapping the Python loader.
- `.wiki/scripts/wiki_config.py get|set|keys|path|show` — Python CLI used by the bash wrapper.

## Sections

```yaml
scheduling:
  compile_after_hour: 18              # 0–23 local time, gates auto-compile + piggybacks
  dedup_window_seconds: 60

piggybacks:                           # all daily by default; weekly/disabled possible
  email_incremental: { enabled: true, cooldown_hours: 24 }
  lint_structural:   { enabled: true, cooldown_hours: 24 }
  review_wiki:       { enabled: true, cooldown_hours: 168 }
  optimize_claude_md:{ enabled: true, cooldown_hours: 24 }
  scan_screenshots:  { enabled: true, cooldown_hours: 24, max_per_run: 50 }
  follow_requests:   { enabled: true, cooldown_hours: 24 }
  sync_memories:     { enabled: true, cooldown_hours: 24 }
  retry_failed_flushes: { enabled: true, cooldown_hours: 24, max_per_run: 5 }

models:
  compile_model: claude-opus-4-7      # claude-opus-4-7 | claude-sonnet-4-6 | claude-haiku-4-5
  ollama_url: http://localhost:11434  # all local-LLM calls share this base
  vision_model: gemma4:e4b
  curiosity_model: gemma4:e4b
  classify_model: gemma4:e4b

limits:
  compile_max_files: 30               # rate-limit guard under the 5h Opus window
  compile_max_consecutive_failures: 3
  flush_max_retries: 3
  flush_retry_delay_seconds: 30
  screenshot_resize_width: 512
  screenshot_timeout_seconds: 60
  curiosity_max_gaps: 3
  curiosity_min_source_chars: 500
  sparse_threshold_words: 200

features:
  curiosity_loop: true                # gap detection + deep-scan requests
  vision_screenshots: true            # local OCR for screenshots
  procmail_execution: false           # opt-in; off by default

graph_view:
  mode: knowledge-only                # knowledge-only | full-vault | sources-only | custom
  custom_search: ""
```

## Adding a new tunable

1. Extend the matching dataclass in `wiki_config.py`.
2. Document the default in `config.example.yaml` with a comment.
3. Replace the hardcoded constant in the script with `CONFIG.<section>.<field>`.
4. Don't add ad-hoc constants back to scripts — extend the config layer.

## Caveat

PyYAML drops comments on programmatic write. `wiki config set` replays a header banner but custom inline comments are lost. For complex edits, edit `config.yaml` by hand and add comments back.

## Future: ruamel.yaml

Switching the loader to `ruamel.yaml` would preserve comments at the cost of a heavier dependency. Defer until comment loss becomes a real annoyance.
