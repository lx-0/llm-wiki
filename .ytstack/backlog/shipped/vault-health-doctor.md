# Vault-health: home-screen banner + `wiki doctor` + JSON surfaces

**Status:** IMPLEMENTED — banner live in `scripts/menu.py`; `wiki doctor` standalone subcommand; `wiki menu --json` + `wiki doctor --json` agent-facing; 29 new tests green; skill `use-llm-wiki` updated with three-surfaces explanation.
**Date:** 2026-05-17

## Problem

Configuration health is currently scattered across four commands that
don't compose:

- `wiki status` — config summary + hooks table + ollama probe
- `wiki hooks status` — per-agent install table
- `wiki skills status` — per-skill linked/missing table
- `wiki seed --check` — template drift audit

No single "is this wiki properly set up?" surface. The interactive home
screen says nothing when:

- Setup wizard was never run (config is all defaults)
- Hooks aren't installed in any project scope (session-capture broken)
- `models.ollama_url` is set but the host is unreachable (curiosity
  loop / inbox classification / voice punctuation / vision will fail)
- `ANTHROPIC_API_KEY` env / Claude CLI auth is missing (compile / query
  / dream will fail)
- compile-errors.log has been accumulating failures the operator
  hasn't seen

Plus the agent-surface gap from the prior session: agents reach into
`scripts/menu_context.py` directly to read suggestions because the
`wiki` CLI doesn't expose them as JSON.

## Goal

Three layers in one arc — each useful standalone, together they cover
"what's broken" (`doctor`) + "what's pending" (`menu --json`) +
"surface critical issues without asking" (banner).

1. **Health probe** — `core/health.py` returns a list of
   `CheckResult(id, severity, message, fix_command)`. Severity is one
   of `critical | warning | info | ok`. Pure Python, no LLM, ~200ms.

2. **Home-screen banner** — `menu.py` calls the probe; if there's at
   least one non-`ok` issue, renders a banner ABOVE the status line:

   ```
     ⚠ 1 critical, 2 warnings — wiki doctor for details
       ✗ run `wiki setup` — config has all-default values
   ```

   Critical issues are listed inline (usually 0-1). Warnings collapse
   into the count. Info-only never shows in the banner.

3. **`wiki doctor` subcommand** — standalone full audit, pretty-print
   default. `wiki doctor --json` for agents. Aggregates the new health
   probes plus structured re-exports of the existing
   `hooks-status` / `skills-status` / `seed --check` data.

4. **`wiki menu --json`** (bundled) — the agent-facing read of
   suggestions + status payload. Was discussed previous turn; lands in
   this arc because both `wiki doctor --json` and `wiki menu --json`
   are the same shape of feature (agent-facing read).

## Health checks v1

| ID                       | Severity   | Detection                                                                       | Fix                              |
|--------------------------|------------|---------------------------------------------------------------------------------|----------------------------------|
| `setup-not-run`          | critical   | `models.ollama_url == ""` AND `models.compile_model == "claude-opus-4-7"` (defaults from `Models()` dataclass) AND `state.json` missing       | `wiki setup`                     |
| `hooks-not-installed`    | warning    | hooks_status_summary returns 0 installed in project scope across all agents     | `wiki hooks install`             |
| `ollama-unreachable`     | warning    | `models.ollama_url` non-empty AND TCP connect fails (reuse `probe_ollama_reachable`) | check Ollama; or blank to disable |
| `claude-not-authed`      | warning    | `ANTHROPIC_API_KEY` env empty AND `~/.claude/credentials.json` missing AND `claude --version` either absent or returns auth-error | `claude /login` or set env       |
| `compile-errors-recent`  | warning    | `compile-errors.log` has lines from last 7 days                                 | review the log                   |
| `template-drift`         | info       | `wiki seed --check` finds ≥1 drifted file                                       | `wiki seed --check` for details  |
| `no-knowledge-articles`  | info       | `knowledge/**/*.md` count == 0                                                  | (fresh vault, expected)          |
| `no-compile-yet`         | info       | `state.json["last_compile"]` missing                                            | `wiki compile` after first source |
| `compile-stale`          | info       | `state.json["last_compile"]` > 30 days ago                                      | `wiki compile` (engagement)      |

Each check is its own function in `core/health.py`. `build_health()`
runs them all under the same 500ms hard cap as `menu_context.py`.

## Rendering

**Banner (home-screen, only when issues exist):**

```
  ⚠ 1 critical, 2 warnings — wiki doctor for details

     ✗ run `wiki setup` — config has all-default values
     ⚠ hooks not installed — wiki hooks install
     ⚠ ollama unreachable at http://kcma-d8:11434
```

Criticals always inline. Warnings inline when ≤2; collapse to count
when >2. Info never in banner. Spacing: 1 blank line between banner
and existing status line, no other layout shift.

**`wiki doctor` (pretty default):**

```
  Vault health — lxw vault (commit 5a5694e)

  Config + setup
    ✓ setup wizard completed
    ✗ hooks not installed in any project scope
        → wiki hooks install
    ✓ skills linked (use-llm-wiki globally registered)

  Connectivity
    ✓ ollama reachable (http://kcma-d8:11434, ~45ms)
    ✓ ANTHROPIC_API_KEY present

  Pipeline
    ⚠ compile-errors.log has 3 entries from 2026-05-17
        → tail .wiki/logs/compile-errors.log
    ✓ last compile 4h ago
    ✓ 384 articles
    ℹ 1 template drifted (AGENTS.md — operator customization)

  Summary: 1 warning, 1 info, 0 critical
  Run `wiki doctor --json` for machine-readable output.
```

Severity glyphs: ✓ ok, ✗ critical, ⚠ warning, ℹ info. Colored.

**`wiki doctor --json`:**

```json
{
  "vault": "lxw",
  "engine_revision": "5a5694e",
  "summary": {"critical": 0, "warning": 1, "info": 1, "ok": 6},
  "checks": [
    {
      "id": "setup-not-run",
      "category": "config",
      "severity": "ok",
      "message": "setup wizard completed",
      "fix": null
    },
    {
      "id": "compile-errors-recent",
      "category": "pipeline",
      "severity": "warning",
      "message": "3 entries from 2026-05-17",
      "fix": "tail .wiki/logs/compile-errors.log",
      "details": {"count": 3, "since": "2026-05-17"}
    }
  ]
}
```

Stable field names; `details` is per-check optional structured info.

**`wiki menu --json`:**

Same shape as the probe currently emits, just wired through the
`wiki` CLI surface so agents don't reach into `scripts/menu_context.py`.

```json
{
  "status": {"articles": 384, "last_compile_ago": "4h", "ollama_reachable": true},
  "suggestions": [
    {"key": "1", "count": 3, "label": "3 files in inbox/",
     "cmd": "process-inbox", "priority": 1}
  ]
}
```

## Integration

**New files:**
- `scripts/core/health.py` (~200 LOC) — `build_health()` + per-check
  functions. Returns `list[dict]` with stable field names.
- `scripts/doctor.py` (~200 LOC) — CLI surface. `--json` flag.
- `tests/test_health.py` (~150 LOC) — per-check unit tests against
  monkeypatched paths + env, JSON shape stability.

**Modified files:**
- `wiki` — `cmd_doctor()` + dispatch case for `doctor`. New flag for
  `menu --json`. ~30 LOC.
- `scripts/menu.py` — call `build_health()`, render banner at top of
  `_build_screen_html()` if non-`ok` issues exist. ~30 LOC.
- `scripts/menu_context.py` — optionally include health summary in
  the JSON payload (so `wiki menu --json` reflects health at the
  outer level). Decision: include a `health_summary` field at top
  level: `{"critical": N, "warning": N}` — agents can fast-check
  without parsing every check. Full per-check detail stays in
  `wiki doctor --json`.

**Skill update:**
- `skills/use-llm-wiki/SKILL.md` — document `wiki menu --json` and
  `wiki doctor --json` in the "Detecting wiki state" reference
  section. Agents currently have no documented way to check health.

## Cold-start cost

- Banner adds ~50ms to home-screen first paint (one extra probe). Hard
  cap inherited from menu_context.py's 500ms SIGALRM.
- `wiki doctor` cold: ~250ms (probe + render). Acceptable for
  on-demand audit.

## Failure modes

- **Probe times out** → banner shows nothing, agent gets empty checks
  list. Operator can still run `wiki doctor` directly which has its
  own probe execution.
- **Single check throws** → that check is skipped, others run. Same
  pattern as `menu_context.py` per-probe try/except.
- **`claude --version` not in PATH** → claude-not-authed check
  returns severity `warning` with fix "ensure claude CLI is installed".

## What stays out

- **Auto-fix actions** — banner only suggests `wiki setup` etc; never
  runs them automatically. Operator decision per check.
- **Per-account auth status** (gmail / gmeet / calendar tokens) —
  deferred. Currently checked at collector-run time; surfacing in
  doctor is additive but bigger scope.
- **Pipeline trend metrics** (compile cost over time, article growth)
  — that's analytics, not health. Different feature.
- **Persistent health history** — each `wiki doctor` run is a fresh
  snapshot. No log of prior runs.

## Open questions

1. **Banner verbosity** — list all criticals inline (1-2 typical), or
   always collapse to count? Recommendation: list criticals inline,
   collapse warnings to count when >2.
2. **`wiki menu --json` placement** — `wiki menu --json` (flag on
   existing menu command) or `wiki suggest` (new subcommand)?
   Recommendation: flag on menu — discoverable from same surface, no
   new naming.
3. **Doctor `--quick`?** — skip expensive checks (TCP probe, claude
   --version subprocess) for use in PreToolUse hooks where 250ms is
   too slow. Defer — wait for a hook use case.
