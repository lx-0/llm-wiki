"""CLI entry point for the `wiki analyze` subcommand — M019 analyst layer.

Sub-commands / flags:

    wiki analyze                          # Pass-1 over all studies, then Pass-2
    wiki analyze --study <id>             # Pass-1 on one study's latest run
    wiki analyze --all-studies            # Pass-1 over every study's latest run
    wiki analyze --cross-study            # Pass-2 only
    wiki analyze --pass2-only             # alias for --cross-study
    wiki analyze --study <id> --no-pass2  # Pass-1 only on one study

Default flow when no flags: --all-studies + --cross-study (full analyst sweep).

Persistence:
    Pass-1 → <study>/runs/<latest-ts>/_analysis.md
    Pass-2 → <vault>/reports/analyses/<pass2-ts>.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from scripts.core.config import CONFIG  # noqa: E402
from scripts.core.paths import ROOT_DIR  # noqa: E402
from scripts.reports._engine.lib.analyst import AnalystError, run_analyst  # noqa: E402
from scripts.reports._engine.study import Study, list_studies, utc_now_iso  # noqa: E402


log = logging.getLogger("analyze")


# Persona prompt locations — `prompts/reports/analyst_*.md`. Hash of
# each file's bytes is the persona_version recorded in each output's
# frontmatter so a future audit can map output back to which persona-
# wording produced it.
PROMPTS_ROOT = Path(__file__).resolve().parent.parent / "prompts" / "reports"
PERSONA_PER_STUDY = PROMPTS_ROOT / "analyst_per_study.md"
PERSONA_CROSS_STUDY = PROMPTS_ROOT / "analyst_cross_study.md"


# Vault root — overridable via --vault for testing against synthetic
# study trees. Defaults to ROOT_DIR (engine's resolved vault).
_VAULT_ROOT: Path = ROOT_DIR


def _studies_root() -> Path:
    return _VAULT_ROOT / CONFIG.personal.reports_dir / "studies"


def _analyses_root() -> Path:
    return _VAULT_ROOT / CONFIG.personal.reports_dir / "analyses"


def _set_vault_root(path: Path) -> None:
    """Override the vault root (for tests + --vault flag)."""
    global _VAULT_ROOT
    _VAULT_ROOT = path.expanduser().resolve()


def _latest_run_dir(study: Study) -> Path | None:
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


def _previous_run_dir(study: Study, latest: Path) -> Path | None:
    """Run directly preceding `latest` by lexical sort, or None."""
    if not study.runs_dir.is_dir():
        return None
    candidates = sorted(
        p for p in study.runs_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p != latest
    )
    return candidates[-1] if candidates else None


def _build_pass1_user_prompt(study: Study, run_dir: Path) -> str:
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
    prev = _previous_run_dir(study, run_dir)
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


def _persist_pass1(study: Study, run_dir: Path, result) -> Path:
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


def cmd_pass1(args: argparse.Namespace) -> int:
    studies = list_studies(_studies_root())
    if args.study:
        studies = [s for s in studies if s.manifest.study_id == args.study]
        if not studies:
            print(f"ERROR: study {args.study!r} not found", file=sys.stderr)
            return 2

    if not studies:
        print(f"(no studies under {_studies_root()})")
        return 0

    failures = 0
    pass1_paths: list[Path] = []
    for study in studies:
        latest = _latest_run_dir(study)
        if latest is None:
            print(f"  {study.manifest.study_id}: no runs yet — skipping")
            continue
        analysis_path = latest / "_analysis.md"
        if analysis_path.is_file() and not args.rerun:
            print(
                f"  {study.manifest.study_id}: _analysis.md already exists "
                f"({analysis_path.relative_to(_studies_root().parent)}) — "
                f"--rerun to overwrite, skipping"
            )
            pass1_paths.append(analysis_path)
            continue
        print(
            f"  {study.manifest.study_id}: Pass-1 analyst on run {latest.name} …",
            flush=True,
        )
        user_prompt = _build_pass1_user_prompt(study, latest)
        print(f"    prompt_chars={len(user_prompt):,}", flush=True)
        try:
            result = run_analyst(
                system_prompt_path=PERSONA_PER_STUDY,
                user_prompt=user_prompt,
                vault_cwd=ROOT_DIR,
                pass_label="per-study",
            )
        except AnalystError as exc:
            print(f"    ! Pass-1 failed: {exc}", file=sys.stderr)
            failures += 1
            continue
        path = _persist_pass1(study, latest, result)
        pass1_paths.append(path)
        print(
            f"    → {path.relative_to(_studies_root().parent)}  "
            f"cost=${result.cost_usd:.4f}  elapsed={result.elapsed_ms / 1000:.1f}s",
            flush=True,
        )

    if failures:
        print(f"\nPass-1: {failures}/{len(studies)} failed.", file=sys.stderr)
        return 1
    print(f"\n✓ Pass-1 done: {len(pass1_paths)} _analysis.md file(s).")
    return 0


def _build_pass2_user_prompt(studies_with_analyses: list[tuple[Study, Path, Path]]) -> str:
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


def _persist_pass2(result, study_count: int) -> Path:
    """Write reports/analyses/<ts>.md."""
    out_dir = _analyses_root()
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


def cmd_pass2(args: argparse.Namespace) -> int:
    studies = list_studies(_studies_root())
    studies_with: list[tuple[Study, Path, Path]] = []
    for study in studies:
        latest = _latest_run_dir(study)
        if latest is None:
            continue
        summary = latest / "_summary.md"
        analysis = latest / "_analysis.md"
        if not summary.is_file() or not analysis.is_file():
            print(
                f"  {study.manifest.study_id}: skipping — "
                f"{'_summary' if not summary.is_file() else '_analysis'} missing "
                f"(run Pass-1 first)"
            )
            continue
        studies_with.append((study, summary, analysis))

    if not studies_with:
        print("(no studies with completed Pass-1 outputs — run "
              "`wiki analyze --all-studies` first)")
        return 0

    print(
        f"  Pass-2 cross-study synthesist over "
        f"{len(studies_with)} stud{'y' if len(studies_with) == 1 else 'ies'} …",
        flush=True,
    )
    user_prompt = _build_pass2_user_prompt(studies_with)
    print(f"    prompt_chars={len(user_prompt):,}", flush=True)
    try:
        result = run_analyst(
            system_prompt_path=PERSONA_CROSS_STUDY,
            user_prompt=user_prompt,
            vault_cwd=ROOT_DIR,
            pass_label="cross-study",
        )
    except AnalystError as exc:
        print(f"    ! Pass-2 failed: {exc}", file=sys.stderr)
        return 1

    path = _persist_pass2(result, len(studies_with))
    print(
        f"    → {path.relative_to(_analyses_root().parent)}  "
        f"cost=${result.cost_usd:.4f}  elapsed={result.elapsed_ms / 1000:.1f}s",
        flush=True,
    )
    return 0


def cmd_default(args: argparse.Namespace) -> int:
    """No-flag default: Pass-1 over all studies + Pass-2.

    Also the entry point used by `flush.py` piggyback when
    `study_run_due` fires — Pass-1 happens per-study automatically;
    Pass-2 fires here when invoked with `--cross-study-only` or
    on its own schedule.
    """
    if not args.cross_study_only:
        rc = cmd_pass1(args)
        if rc != 0:
            return rc
    if not args.no_pass2:
        return cmd_pass2(args)
    return 0


def main() -> int:
    from core.console import setup_console_logging
    setup_console_logging("analyze")
    parser = argparse.ArgumentParser(description="Operator-self-reports analyst layer")
    parser.add_argument("--vault", default=None, type=Path,
                        help="Override vault root (defaults to engine ROOT_DIR).")
    parser.add_argument("--study", default=None,
                        help="Pass-1: restrict to one study slug.")
    parser.add_argument("--cross-study-only", action="store_true",
                        help="Skip Pass-1, run Pass-2 only.")
    parser.add_argument("--no-pass2", action="store_true",
                        help="Run Pass-1, skip Pass-2.")
    parser.add_argument("--rerun", action="store_true",
                        help="Overwrite existing _analysis.md files.")
    args = parser.parse_args()
    if args.vault is not None:
        _set_vault_root(args.vault)
    return cmd_default(args)


if __name__ == "__main__":
    sys.exit(main())
