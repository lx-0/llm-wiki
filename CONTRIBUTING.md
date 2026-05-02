# Contributing to llm-wiki

Thanks for your interest. llm-wiki is a small, opinionated engine; contributions are welcome but the project's scope is intentionally narrow.

## What's in scope

- Bug fixes in the engine (scripts, hooks, CLI).
- New ingestion collectors, scanners, or compilers that fit the existing pipeline shape (`raw/` → LLM compile → `knowledge/`).
- Improvements to the agent-facing documentation (`AGENTS.md`, `docs/concept.md`, `docs/PROCESS.md`, `.ytstack/KNOWLEDGE.md`).
- Performance / reliability fixes (rate-limit handling, hook timeouts, retry pipelines).

## What's out of scope

- New UI / theming / publish flows. This is a Markdown-on-Obsidian engine, not a wiki framework.
- Multi-tenant / SaaS-shaped features. The project is solo-by-default; depersonalized scale-out is a config concern, not a product concern.
- Replacing the LLM provider abstraction with a heavier dependency (we keep the surface in `scripts/ollama_client.py` + `wiki_config.py` deliberately small).

If you're not sure whether something is in scope, open a discussion first.

## Workflow

1. Open an issue describing what you want to change. For non-trivial work, wait for a thumbs-up before starting — saves wasted effort if scope is wrong.
2. Fork, branch off `main`. Branch names: `feat/<short>`, `fix/<short>`, `docs/<short>`.
3. Read [AGENTS.md](AGENTS.md) and [.ytstack/KNOWLEDGE.md](.ytstack/KNOWLEDGE.md) before non-trivial changes — they capture hard-won decisions you'll otherwise re-learn.
4. Make the change. Add tests where the project has them (it's currently script-heavy with limited test coverage; that's a known gap).
5. Update docs in the same PR:
   - `docs/PROCESS.md` if pipeline behavior changed.
   - `.ytstack/KNOWLEDGE.md` if you discovered a new gotcha or hard-won lesson.
   - `README.md` if the public CLI changed.
6. Open a PR. Conventional commit style (`feat:`, `fix:`, `docs:`, `chore:`) for the title.

## Local dev

```bash
# Install into a sandbox vault
./install.sh /tmp/sandbox-vault

# From inside .wiki/ (the engine dir):
cd /tmp/sandbox-vault/.wiki
uv run python scripts/<whatever>.py --help
```

`uv sync` is run by `install.sh`. The venv lives at `<vault>/.wiki/.venv/` — never at the vault root.

## Personal data

If you submit a PR, scan it for personal data first: hardcoded usernames, IPs, email addresses, folder structures from your own setup. Generic examples (`example.com`, `INBOX/Work`) are preferred over real ones.

The CI runs gitleaks on every push to catch obvious secrets, but it does not catch personal taxonomy or example data — that's on the contributor.

## License

By contributing you agree your contributions are licensed under the project's MIT License (see [LICENSE](LICENSE)).
