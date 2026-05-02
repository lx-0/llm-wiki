# Decisions

Append-only architectural and product decisions for llm-wiki. Never rewrite past entries. If a decision is reversed, add a new entry that supersedes.

Format for each entry:

## YYYY-MM-DD: <Short title>

**Context:** <what forced the decision>
**Options considered:** <A, B, C>
**Chose:** <selected option>
**Reason:** <why>
**Supersedes:** <link to earlier entry if this reverses a prior decision>

---

## 2026-05-02: Adopt ytstack as project memory; migrate existing docs

**Context:** llm-wiki has been iterating for several weeks with ad-hoc project memory split between `docs/` (engine documentation, design decisions, plans) and Claude project-memory files (project_*.md, feedback_*.md). The follow-up backlog and roadmap were unstructured. Long-term iterative development needs a durable STATE / slice-task structure.
**Options considered:** (A) keep ad-hoc, defer ytstack until a `docs/plans/*` milestone; (B) adopt ytstack now, scaffold `.ytstack/` alongside existing docs with pointer-based duplication; (C) adopt ytstack now and consolidate — migrate `docs/design-decisions.md`, `docs/plans/`, and Claude project-memory artifacts into `.ytstack/` shape.
**Chose:** C.
**Reason:** Pointer-duplication accumulates drift; a single source of truth per artifact type is cleaner. The project is long-horizon (months of iteration ahead) and ytstack's STATE / slice-task discipline is exactly what an unstructured follow-up backlog lacks.
**Supersedes:** —
**Linked artifacts:** `OFFICE-HOURS-self-cartography-engine.md`; upstream ytstack PR #15 (M010 brownfield-detect-analyze-migrate).

## 2026-05-02: Skip plan-ceo-review (concept mode) for initial scaffolding

**Context:** ytstack greenfield flow recommends `office-hours` → `plan-ceo-review` (concept) → `init-project`. For llm-wiki the project is brownfield-retro: validated by months of artifacts, solo-funded by curiosity, no external customer waiting for a wedge.
**Options considered:** (A) run plan-ceo-review concept-mode anyway for discipline; (B) skip and let reality be the critic.
**Chose:** B.
**Reason:** The `Risks` section of the pitch already names the wedge-discipline question explicitly (single-wedge focus rejected); a CEO-style review would land on the same point. Marginal value of formal stress-test is low when the operator is also the user. Reality (M001 outcomes) is the better critic.
**Supersedes:** —

## 2026-05-02: Project-level .ytstack/ (committed), not user-level

**Context:** init-project asks where `.ytstack/` lives. llm-wiki's pitch positions it as potentially public; the engine repo already commits `docs/` engine documentation.
**Options considered:** (A) project-level (.ytstack/ in repo, committed); (B) user-level (~/.ytstack/projects/llm-wiki/, machine-local, private); (C) both.
**Chose:** A.
**Reason:** Engine repo already commits engine-tier documentation. Survives repo clone, visible to other agents and contributors, no machine-loss risk. User-level only correct for secret side-projects, which this is not.
**Supersedes:** —
