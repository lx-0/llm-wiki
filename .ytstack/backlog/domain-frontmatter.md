# Domain — optional life-domain axis as frontmatter tag

Optional frontmatter tag `domain: company | personal | ai | meta` on `knowledge/**/*.md`. Cross-cutting axis to the entity-type folder structure. Lifted from `lx/` audit (which used emoji-prefix folders 🌈 Company / 👤 Personal / 🤖 AI as a life-domain split) — but expressed as a tag, not as folders. See `lx-vault-merge.md` for the comparative analysis.

## The pattern

```yaml
---
title: "OAuth client credentials rotation"
type: concept
domain: company  # optional
---
```

Values (initial set, extend if needed):
- `company` — Yesterday-related, work, business strategy
- `personal` — health, family, apartment, side-interests
- `ai` — AI tooling, agent infra, prompt engineering (overlaps with company often)
- `meta` — wiki engine itself, ytstack, llm-wiki maintenance

Behavior:
- **Pure filter axis.** No folder change, no semantic engine treatment.
- **Dashboard variants**: `wiki query --domain personal` filters; dashboard can render per-domain Open Threads sections.
- **Graph view coloring**: secondary color channel (alongside entity-type) — see `project_graph_view_multichannel`.
- **Optional, never required.** Untagged articles default to "unscoped" and appear in all views.

## Why it matters now

- The `lx/` audit found a clean 3-way split (Company / Personal / AI) at the *top* of the manual organization. That signal — life-domain matters — is real, even though the folder-implementation is wrong for lxw.
- Today lxw has no way to ask "show me only Personal Action Items from this week" or "render a Company-only MOC". Domain frontmatter enables this with one line per page.
- Cost is genuinely tiny: optional field, no migration burden (un-tagged = "all"), no schema break.

## Open design questions

- **Single value or list?** Single is simpler. Some pages legitimately straddle (e.g. "llm-wiki" is both `ai` and `meta`). Recommend single + secondary `also_domains: []` if real need surfaces. Probably YAGNI v1.
- **Closed enum or freeform?** Closed enum (validated by lint) prevents drift. Add values via config knob.
- **Auto-domain via path heuristic?** Could infer from MOC membership (e.g. pages linked from `MOCs/yesterday.md` → `domain: company`). Cute, fragile. Skip.
- **Domain MOCs** — already exist per memory (`project_domain_mocs`): `MOCs/llm-wiki`, `MOCs/fleet`, `MOCs/openclaw`, `MOCs/claude-code`, `MOCs/yesterday`. These are *topic* MOCs, not *domain* MOCs. Coexist fine — domain is a coarser axis (5 values vs N topics).
- **Compile prompt awareness** — should compile know about domain? Probably no v1. Operator-driven tag.

## Touchpoints

- `scripts/core/frontmatter.py` — recognize `domain: str` with enum validation
- `scripts/core/config.py` + `config.example.yaml` — `domains: list[str] = ["company", "personal", "ai", "meta"]` (must extend `migrations/migrate_config_keys.py`)
- `scripts/cli.py` — `wiki query --domain <value>` filter
- `scripts/dashboard/*` — optional per-domain section rendering (defer until demand is clear)
- `scripts/lint.py` — validate `domain` is in configured enum
- `templates/.obsidian/graph.json` — domain as secondary color channel (border vs fill, or shape vs color — coordinate with type-axis to avoid clash)
- `AGENTS.md` — document the tag

## Lift estimate

- Schema + config + migration + lint: 0.5 day
- `wiki query --domain` filter: 0.25 day
- Graph view secondary channel (if attempted): 0.5 day
- Backfill ~50 obvious pages with domain tags: 0.5 day (mostly mechanical)

**~1.5 days for tag + query. Graph treatment optional follow-up.**

## Risks

1. **Adoption gap** — operator forgets to tag, most pages stay untagged, feature unused. Mitigation: backfill obvious cases at ship-time; if 3-month-later <20% adoption, declare unused and remove. Reversible.
2. **Overlap ambiguity** — "Is llm-wiki domain `ai` or `meta`?" — operator hesitation slows tagging. Mitigation: lint warns on missing, doesn't block; "when in doubt, leave blank" is fine.
3. **Folder-vs-tag confusion** — operator might want to re-create lx's folder structure inside lxw. Resist; tag-only enforces the architectural decision.

## Ripens when

- Anytime. Lowest-priority of the three lx-lessons cluster — ship after `archives-flag` and `areas-bucket` (which fix real gaps), this fixes a nice-to-have.

## Status

Backlog. Low-medium priority. Sibling to `archives-flag.md` and `areas-bucket.md` — the three "lessons from lx-audit" cluster. Cleanly independent; can defer indefinitely without blocking lx-merge or anything else.
