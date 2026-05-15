# CLAUDE.md

Conventions for AI agents working on this repo live in [AGENTS.md](AGENTS.md) — tool-agnostic, read by Claude Code, Cursor, Aider, Codex, and others.

Hard-won engine learnings (Ollama gotchas, rate-limit debugging, anti-patterns to avoid) are in [.ytstack/KNOWLEDGE.md](.ytstack/KNOWLEDGE.md). Project-level decision log lives in [.ytstack/DECISIONS.md](.ytstack/DECISIONS.md). Read both before non-trivial changes.

## Hard rules

- **Config-knob changes are not done until the vault is migrated.** Adding/renaming/removing a key in `scripts/core/config.py` or `config.example.yaml` requires extending `scripts/migrations/migrate_config_keys.py` in the same commit so operator vaults at `<vault>/.wiki/config.yaml` get the new key written in (with the same default). Dataclass-default fall-through is not "the operator's config reflects the change" — it just hides it. Never `cp` into the vault; the migration is the only legal write path.
- **Operator-facing URLs are verified before they are sent.** Any URL handed to the operator to click — Google Cloud Console, OAuth API-enable, GCP project pages, vendor dashboards — must be assembled from authoritative local data, not from training memory or a guess. Project ID + project number + API short-name are all locally readable (e.g. `<vault>/.claude/*-oauth-client.json` → `installed.project_id`, `installed.client_id` prefix; engine config; error payload). Read the source, build the URL with the form the operator recognises (named project ID, not numeric), state it once, correctly. No "try this, if it 404s try that". No mixing project-name and project-number forms across messages. If the data isn't locally available, say so and ask — don't probe with the operator's browser as the test harness.
