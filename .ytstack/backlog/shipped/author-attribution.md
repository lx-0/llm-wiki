# author-attribution — operator-as-implicit-author for single-tenant content

Today `compile.py` aggregates entity pages (`knowledge/people/alex.md` etc.) via **mention-based** inference — LLM reads substrate, identifies references by name/alias. **There is no `author:` frontmatter convention** (grep `^author:` across `knowledge/` returns nothing). Result: when operator-authored content says "we should pivot", the LLM has no signal that "we" = alex's perspective. Surfaced 2026-05-16 during Phase 2 design of `lx-vault-merge.md`.

## The gap

- Strategy docs / mission-vision-values / manifestos get distilled as *reference material* rather than as **alex's beliefs**
- Imported `imported/lx/**` content loses authorship at migration time
- `takes-substrate.md` (gbrain pattern) is adjacent but different: author-of-content ≠ holder-of-belief. takes covers "WHO believes WHAT, confidence + date". author covers "WHO wrote this".

## Proposal: hybrid `(c) + (a)`

**(c) Implicit-operator-author default** — single-tenant vault default:
- Config knob `personal.implicit_operator_author: str | None = null` — operator sets to `"alex"` (or whatever)
- Compile prompt instructed: "When `author:` is absent and `personal.implicit_operator_author` is set, treat the file as operator-authored content."
- Multi-tenant-ready: leave as null, files need explicit `author:` to attribute

**(a) Explicit `author:` stamp at Phase-2 migration** — belt-and-suspenders:
- Phase 2 migration of `imported/lx/**/*` writes `author: alex` to each frontmatter explicitly
- Eliminates ambiguity for that one-shot import batch
- Doesn't require ongoing operator discipline

## Touchpoints

- `scripts/core/config.py` + `config.example.yaml` + `migrations/migrate_config_keys.py` — add `personal.implicit_operator_author: str | None` (same-commit hard-rule)
- `scripts/core/frontmatter.py` or wherever schema-validation lives — recognize `author:` as an optional string
- `prompts/compile_main.md` — type-conditional rule: when distilling beliefs/decisions/opinions from a file, use `author:` (or fallback to `personal.implicit_operator_author`) to attribute
- `scripts/lint.py` — optional: warn on operator-likely paths missing `author:` when `personal.implicit_operator_author` is null (helps multi-tenant transition)
- `AGENTS.md` — document the convention

Phase 2 migration tooling (separate task in lx-vault-merge follow-up):
- Bulk-stamp `author: alex` into imported/lx/**/* during Phase-2 entity-page conversion

## Lift estimate

- Schema + config + migration entry: 0.5 day
- Compile prompt update: 0.25 day
- Lint optional warning: 0.25 day
- Migration bulk-stamp script (Phase 2): 0.5 day

**~1.5 days for the feature itself.** Phase-2-stamp adds half a day.

## Risks

1. **Compile prompt regression** — telling the LLM to attribute by `author:` might suppress legitimate mention-aggregation. Mitigation: explicit instruction that `author:` complements (not replaces) mention-based aggregation.
2. **Mis-attribution at migration** — if `imported/lx/Templates/` or similar non-operator-authored content gets stamped `author: alex`, becomes a noise source. Mitigation: migration script has explicit allowlist (Areas/, Projects/, Resources/, loose top-level) and skiplist (Templates/, _attachments/, Archives/).
3. **Multi-tenant future** — when 2nd operator joins (hypothetically), `implicit_operator_author` becomes ambiguous. Mitigation: keep it as single string config, escalate to lookup only when there's real multi-tenant demand. YAGNI.

## Ripens when

- Phase 2 of `lx-vault-merge.md` starts. Operator already validated demand 2026-05-16. Hot M008-or-M009 candidate (after M007 compile-role-axis ships).

## Status

**SHIPPED** via M009 (691d786, 2026-05-16, Agent B). See commit message + git log for implementation details. Backlog kept as decision-context.