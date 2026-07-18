"""Analyst-agent harness for the two-pass M019 analyst layer.

Pass-1 (per-study) and Pass-2 (cross-study) share this same harness
— they differ only in which prompt-file (persona) is loaded and what
the engine inlines as context. The agent invocation, scope-lock,
cost-tracking, and error-handling are identical.

Composition (verified empirically in M019-S01-T01 + carried through
S02-T02):

  allowed_tools = ['Read', 'Glob', 'Grep']
  disallowed_tools = ['Write', 'Edit', 'NotebookEdit']
  permission_mode = 'default'
  can_use_tool = make_path_scope_gate([])  # deny-all-writes
  setting_sources = ['project']

Since M021 S01 the composition is wired through ``run_sdk_query`` —
``SdkCallSpec(deny_all_writes=True)`` assembles the deny-all gate plus
the streaming prompt the callback contract requires; the tool sets stay
caller-owned policy in ``ANALYST_ALLOWED_TOOLS`` / ``ANALYST_DISALLOWED_TOOLS``.
"""

from __future__ import annotations

import hashlib
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from claude_agent_sdk import query  # noqa: E402

from scripts.core.config import CONFIG  # noqa: E402
from scripts.core.sdk_helpers import SdkCallSpec, run_sdk_query  # noqa: E402
from scripts.reports._engine.study import Study, utc_now_iso  # noqa: E402


# Persona prompt locations — `prompts/reports/analyst_*.md`. The SHA256[:16]
# of each file's bytes is the persona_version recorded in each output's
# frontmatter so a future audit can map output back to which persona-
# wording produced it.
_PROMPTS_ROOT = Path(__file__).resolve().parents[4] / "prompts" / "reports"
PERSONA_PER_STUDY = _PROMPTS_ROOT / "analyst_per_study.md"
PERSONA_CROSS_STUDY = _PROMPTS_ROOT / "analyst_cross_study.md"


# Same composition as inference. Locked together so a single config
# tweak applies to both classes of agent.
ANALYST_ALLOWED_TOOLS: tuple[str, ...] = ("Read", "Glob", "Grep")
ANALYST_DISALLOWED_TOOLS: tuple[str, ...] = ("Write", "Edit", "NotebookEdit")

# Default model — Haiku is fast + cheap. Personality post-wedge
# instruments might want Sonnet for richer interpretation; that's a
# per-call override via the `model` kwarg.
DEFAULT_ANALYST_MODEL = "claude-haiku-4-5"

# Max turns: analyst typically Reads a few substrate files (Pass-1)
# or none (Pass-2), then emits the markdown body. 8 turns leaves
# headroom for ad-hoc reads without bloat.
DEFAULT_MAX_TURNS = 8


class AnalystError(RuntimeError):
    """Raised when an analyst call fails in a way the caller must surface."""


@dataclass(frozen=True)
class AnalystResult:
    """Outcome of one analyst call (Pass-1 or Pass-2)."""

    markdown_body: str
    elapsed_ms: int
    model_id: str
    persona_version: str           # SHA256[:16] of persona prompt file
    prompt_version: str            # SHA256[:16] of full rendered prompt
    cost_usd: float
    pass_label: str                # "per-study" | "cross-study"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def run_analyst(
    *,
    system_prompt_path: Path,
    user_prompt: str,
    vault_cwd: Path,
    pass_label: str,
    model: str = DEFAULT_ANALYST_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> AnalystResult:
    """Run one analyst call (Pass-1 or Pass-2) end-to-end.

    Args:
        system_prompt_path: Path to `prompts/reports/analyst_per_study.md`
            or `analyst_cross_study.md`. The persona/instructions; loaded
            verbatim into the SDK call's `system_prompt`. Persona-version
            for provenance is the SHA256[:16] of this file's bytes.
        user_prompt: The "user message" the agent receives — typically
            the inlined study results, summary, and (for Pass-1) the
            prior-run summary.
        vault_cwd: Vault root the agent runs under (cwd). Read tool
            uses this as the resolution point for relative paths.
        pass_label: "per-study" or "cross-study" — recorded in the
            `AnalystResult` for provenance + logging.

    Returns:
        `AnalystResult` containing the markdown body + provenance.

    Raises:
        AnalystError: SDK failure / scope-lock violation / empty
            output. Caller surfaces to the operator + does not
            persist a half-formed `_analysis.md`.
    """
    import asyncio
    return asyncio.run(
        _run_analyst_async(
            system_prompt_path=system_prompt_path,
            user_prompt=user_prompt,
            vault_cwd=vault_cwd,
            pass_label=pass_label,
            model=model,
            max_turns=max_turns,
        )
    )


async def _run_analyst_async(
    *,
    system_prompt_path: Path,
    user_prompt: str,
    vault_cwd: Path,
    pass_label: str,
    model: str,
    max_turns: int,
) -> AnalystResult:
    log = logging.getLogger("reports.analyst")

    if not system_prompt_path.is_file():
        raise AnalystError(
            f"analyst persona prompt not found: {system_prompt_path}"
        )
    persona_text = system_prompt_path.read_text(encoding="utf-8")
    persona_version = _file_hash(system_prompt_path)
    prompt_version = _text_hash(user_prompt)

    start = time.perf_counter()

    # One harness call owns the mechanics (options assembly, stderr capture,
    # cache-aware usage extraction, LEDGER recording — cache-inclusive, on
    # every outcome — and failure diagnostics). The analyst scope-lock stays
    # caller-owned policy: deny_all_writes wires the empty-roots can_use_tool
    # gate + the streaming prompt the callback contract requires.
    result = await run_sdk_query(
        user_prompt,
        SdkCallSpec(
            label=f"reports.analyst pass={pass_label}",
            logger=log,
            model=model,
            cwd=vault_cwd,
            max_turns=max_turns,
            system_prompt=persona_text,
            allowed_tools=ANALYST_ALLOWED_TOOLS,
            disallowed_tools=ANALYST_DISALLOWED_TOOLS,
            setting_sources=("project",),
            deny_all_writes=True,
            input_chars=len(user_prompt) + len(persona_text),
            extra_log={"persona_version": persona_version,
                       "prompt_version": prompt_version},
        ),
        query_fn=query,
    )
    if result.failure is not None:
        raise AnalystError(
            f"analyst call failed (pass={pass_label}): {result.failure}"
        ) from result.exc

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    body = result.assistant_text.strip()
    if not body:
        raise AnalystError(
            f"analyst returned empty markdown body (pass={pass_label}) — "
            f"check captured stderr"
        )

    return AnalystResult(
        markdown_body=body,
        elapsed_ms=elapsed_ms,
        model_id=model,
        persona_version=persona_version,
        prompt_version=prompt_version,
        cost_usd=result.cost_usd,
        pass_label=pass_label,
    )


# ── Pass-1 / Pass-2 orchestration ───────────────────────────────────────
#
# Prompt-building + persistence live here (not in the CLIs) so `wiki study
# run` and `wiki analyze` consume one public interface. Every vault-relative
# path is derived from an EXPLICIT `vault_root` argument — no module-global.
# That kills the ROOT_DIR-vs-`--vault` mismatch class where the analyst's
# Read-tool cwd resolved citations against a different tree than the one the
# studies/analyses were discovered under.


def studies_root(vault_root: Path) -> Path:
    """`<vault>/<reports_dir>/studies` for a given vault root."""
    return vault_root / CONFIG.personal.reports_dir / "studies"


def analyses_root(vault_root: Path) -> Path:
    """`<vault>/<reports_dir>/analyses` for a given vault root."""
    return vault_root / CONFIG.personal.reports_dir / "analyses"


def latest_run_dir(study: Study) -> Path | None:
    """Return the latest finalised run directory for a study (skips
    `.<ts>.tmp` partial dirs). None if no runs exist yet."""
    if not study.runs_dir.is_dir():
        return None
    candidates = [
        p for p in study.runs_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.name)


def previous_run_dir(study: Study, latest: Path) -> Path | None:
    """Run directly preceding `latest` by lexical sort, or None."""
    if not study.runs_dir.is_dir():
        return None
    candidates = sorted(
        p for p in study.runs_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p != latest
    )
    return candidates[-1] if candidates else None


def build_pass1_user_prompt(study: Study, run_dir: Path) -> str:
    """Inline the manifest + per-instrument reports + summary for one study run."""
    sections: list[str] = []
    sections.append(f"# Study: {study.manifest.study_id}\n")
    sections.append(f"## Manifest\n\n```yaml\n"
                    f"{(study.study_dir / 'manifest.yaml').read_text(encoding='utf-8').strip()}\n"
                    f"```\n")

    summary_path = run_dir / "_summary.md"
    if summary_path.is_file():
        sections.append(f"## Deterministic summary (`_summary.md`)\n\n"
                        f"{summary_path.read_text(encoding='utf-8').strip()}\n")

    instruments_dir = run_dir / "instruments"
    if instruments_dir.is_dir():
        for report in sorted(instruments_dir.glob("*.md")):
            sections.append(
                f"## Per-instrument report: `instruments/{report.name}`\n\n"
                f"{report.read_text(encoding='utf-8').strip()}\n"
            )

    # Optional: previous run's summary for change framing
    prev = previous_run_dir(study, run_dir)
    if prev is not None:
        prev_summary = prev / "_summary.md"
        if prev_summary.is_file():
            sections.append(
                f"## Previous run's summary (for change framing): "
                f"`runs/{prev.name}/_summary.md`\n\n"
                f"{prev_summary.read_text(encoding='utf-8').strip()}\n"
            )

    sections.append(
        f"\n---\n\nProduce the Pass-1 analyst markdown body for this run "
        f"per the system prompt. Heading: `# Analysis — "
        f"{study.manifest.study_id} @ {run_dir.name}`. Body 400-700 words.\n"
    )
    return "\n".join(sections)


def persist_pass1(study: Study, run_dir: Path, result: AnalystResult) -> Path:
    """Write _analysis.md with frontmatter into the run dir."""
    fm = {
        "kind": "analysis",
        "pass": 1,
        "study_id": study.manifest.study_id,
        "run_timestamp": run_dir.name,
        "informant_report": True,
        "persona_version": result.persona_version,
        "prompt_version": result.prompt_version,
        "model_id": result.model_id,
        "cost_usd": round(result.cost_usd, 4),
        "elapsed_ms": result.elapsed_ms,
        "engine_version": "M019-S05",
    }
    body = (
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
        + "\n---\n\n"
        + result.markdown_body.strip()
        + "\n"
    )
    out_path = run_dir / "_analysis.md"
    out_path.write_text(body, encoding="utf-8")
    return out_path


def build_pass2_user_prompt(
    studies_with_analyses: list[tuple[Study, Path, Path]],
) -> str:
    """Inline manifest + summary + analysis for each study's latest run.

    `studies_with_analyses` is `[(Study, latest_summary_path, latest_analysis_path), ...]`.
    """
    sections: list[str] = []
    sections.append(f"# Cross-study scope: {len(studies_with_analyses)} study/studies\n")
    for study, summary_path, analysis_path in studies_with_analyses:
        sections.append(
            f"\n---\n\n## Study: `{study.manifest.study_id}`\n"
        )
        sections.append(
            f"### Manifest\n\n```yaml\n"
            f"{(study.study_dir / 'manifest.yaml').read_text(encoding='utf-8').strip()}\n```\n"
        )
        sections.append(
            f"### Latest `_summary.md` ({summary_path.parent.name})\n\n"
            f"{summary_path.read_text(encoding='utf-8').strip()}\n"
        )
        sections.append(
            f"### Latest `_analysis.md` (Pass-1)\n\n"
            f"{analysis_path.read_text(encoding='utf-8').strip()}\n"
        )

    sections.append(
        f"\n---\n\nProduce the Pass-2 cross-study synthesis markdown body. "
        f"Heading: `# Cross-study analysis — {utc_now_iso()}`. "
        f"Body 250-450 words at N≥2; 80-150 words at N=1 (honestly "
        f"acknowledge the single-study state).\n"
    )
    return "\n".join(sections)


def persist_pass2(
    result: AnalystResult, study_count: int, *, vault_root: Path
) -> Path:
    """Write `<vault>/<reports_dir>/analyses/<ts>.md`."""
    out_dir = analyses_root(vault_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now_iso()
    out_path = out_dir / f"{timestamp}.md"
    fm = {
        "kind": "cross-study-analysis",
        "pass": 2,
        "pass2_timestamp": timestamp,
        "study_count": study_count,
        "informant_report": True,
        "persona_version": result.persona_version,
        "prompt_version": result.prompt_version,
        "model_id": result.model_id,
        "cost_usd": round(result.cost_usd, 4),
        "elapsed_ms": result.elapsed_ms,
        "engine_version": "M019-S05",
    }
    body = (
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
        + "\n---\n\n"
        + result.markdown_body.strip()
        + "\n"
    )
    out_path.write_text(body, encoding="utf-8")
    return out_path
