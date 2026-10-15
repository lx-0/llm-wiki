"""Vault-health checks for the home-screen banner + `wiki doctor` surface.

Each check is a pure function returning a `CheckResult`. `build_health()`
runs them all and returns the list, ordered by severity (critical first).
Per-check try/except so a single broken probe never kills the rest;
falls back to a `severity="warning"` result describing the probe failure.

Severities (ordered):
    critical    — wiki is broken / unusable in this state
    warning     — wiki works but a capability is degraded
    info        — informational; often expected (e.g. fresh vault)
    ok          — check passed

`--quick` mode skips network probes + subprocess calls (TCP connect,
`claude --version`, `wiki seed --check`), trading completeness for
sub-50ms latency. Used by hooks where 250ms is too slow.

The checks live by subsystem: `environment` (setup, hooks, the `wiki` shortcut,
Ollama, Claude auth, account tokens, voice), `engine` (template drift, updates,
dependency integrity, cloud eviction), `pipeline` (compile, corpus, index, flush,
piggybacks); `_base` holds `CheckResult` and the shared helpers. This package binds
none of the vault paths or private helpers the tests patch — a patch belongs on the
submodule that reads the name (`tests/_health_paths.py`, `tests/test_health_package.py`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict

from core import actions
from core.health._base import SEVERITY_ORDER, CheckResult, _probe_failed
from core.health.engine import (
    check_dependencies_importable,
    check_engine_cloud_eviction,
    check_engine_update_available,
    check_template_drift,
)
from core.health.environment import (
    check_account_auths,
    check_claude_authed,
    check_hooks_installed,
    check_ollama_reachable,
    check_setup_run,
    check_voice_audio_setup,
    check_wiki_on_path,
)
from core.health.pipeline import (
    check_compile_errors_recent,
    check_compile_state,
    check_flush_pipeline,
    check_index_drift,
    check_no_knowledge_articles,
    check_piggyback_health,
)

__all__ = [
    "SEVERITY_ORDER",
    "CheckResult",
    "build_health",
    "check_account_auths",
    "check_claude_authed",
    "check_compile_errors_recent",
    "check_compile_state",
    "check_dependencies_importable",
    "check_engine_cloud_eviction",
    "check_engine_update_available",
    "check_flush_pipeline",
    "check_hooks_installed",
    "check_index_drift",
    "check_no_knowledge_articles",
    "check_ollama_reachable",
    "check_piggyback_health",
    "check_setup_run",
    "check_template_drift",
    "check_voice_audio_setup",
    "check_wiki_on_path",
    "health_summary",
    "to_json",
]


# ── Orchestration ───────────────────────────────────────────────────

# Checks return either a single CheckResult or a list[CheckResult]
# (for multi-result probes like per-account auth — one CheckResult per
# account-integration pair, count knowable only at probe time).
# `build_health` flattens both cases into a single list.
_ALL_CHECKS: list[Callable[..., CheckResult | list[CheckResult]]] = [
    check_setup_run,
    check_hooks_installed,
    check_wiki_on_path,
    check_ollama_reachable,
    check_claude_authed,
    check_account_auths,
    check_compile_errors_recent,
    check_flush_pipeline,
    check_template_drift,
    check_engine_update_available,
    check_no_knowledge_articles,
    check_compile_state,
    check_voice_audio_setup,
    check_piggyback_health,
    check_index_drift,
    check_dependencies_importable,
    check_engine_cloud_eviction,
]


def build_health(*, quick: bool = False) -> list[CheckResult]:
    """Run every check, return results sorted by severity (criticals first).

    Per-check return type is `CheckResult | list[CheckResult]`. Single
    results are appended; lists are extended. Multi-result probes
    (e.g. per-account auth: N accounts × M integrations) handle their
    own iteration internally.
    """
    results: list[CheckResult] = []
    for fn in _ALL_CHECKS:
        try:
            # Pass quick=True only to checks that accept it (introspect signature).
            from inspect import signature

            produced = fn(quick=quick) if "quick" in signature(fn).parameters else fn()
            if isinstance(produced, list):
                results.extend(produced)
            else:
                results.append(produced)
        except Exception as exc:
            results.append(_probe_failed(fn.__name__, "unknown", exc))
    results.sort(key=lambda r: (SEVERITY_ORDER.get(r.severity, 99), r.id))
    return results


def health_summary(results: list[CheckResult]) -> dict[str, int]:
    """Reduce a check list to severity counts for the banner / JSON payload."""
    out = {"critical": 0, "warning": 0, "info": 0, "ok": 0}
    for r in results:
        out[r.severity] = out.get(r.severity, 0) + 1
    return out


def to_json(results: list[CheckResult]) -> list[dict]:
    """Serialize to plain-dict form for JSON output (schema 2: `title` always present,
    `verb` from the action catalogue when the check is dispatchable)."""
    out: list[dict] = []
    for r in results:
        d = asdict(r)
        d["title"] = r.title or r.message
        d["verb"] = actions.verb_for(r.dispatch_args) if r.dispatch_args else None
        out.append(d)
    return out
