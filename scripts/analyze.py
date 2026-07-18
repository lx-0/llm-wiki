"""CLI entry point for the `wiki analyze` subcommand — M019 analyst layer.

Sub-commands / flags:

    wiki analyze                          # Pass-1 over all studies, then Pass-2
    wiki analyze --study <id>             # Pass-1 on one study's latest run
    wiki analyze --all-studies            # Pass-1 over every study's latest run
    wiki analyze --cross-study            # Pass-2 only
    wiki analyze --pass2-only             # alias for --cross-study
    wiki analyze --study <id> --no-pass2  # Pass-1 only on one study

Default flow when no flags: --all-studies + --cross-study (full analyst sweep).

Prompt-building + persistence live in the analyst library
(`scripts.reports._engine.lib.analyst`); this CLI is a thin driver that
resolves a vault root (`--vault`, else engine ROOT_DIR) and passes it
explicitly to every path-resolving call — so the analyst agent's Read-tool
cwd always matches the tree the studies were discovered under.

Persistence:
    Pass-1 → <vault>/<reports_dir>/studies/<id>/runs/<latest-ts>/_analysis.md
    Pass-2 → <vault>/<reports_dir>/analyses/<pass2-ts>.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.core.paths import ROOT_DIR  # noqa: E402
from scripts.reports._engine.lib.analyst import (  # noqa: E402
    PERSONA_CROSS_STUDY,
    PERSONA_PER_STUDY,
    AnalystError,
    analyses_root,
    build_pass1_user_prompt,
    build_pass2_user_prompt,
    latest_run_dir,
    persist_pass1,
    persist_pass2,
    run_analyst,
    studies_root,
)
from scripts.reports._engine.study import Study, list_studies  # noqa: E402


log = logging.getLogger("analyze")


def cmd_pass1(args: argparse.Namespace, vault_root: Path) -> int:
    studies = list_studies(studies_root(vault_root))
    if args.study:
        studies = [s for s in studies if s.manifest.study_id == args.study]
        if not studies:
            print(f"ERROR: study {args.study!r} not found", file=sys.stderr)
            return 2

    if not studies:
        print(f"(no studies under {studies_root(vault_root)})")
        return 0

    failures = 0
    pass1_paths: list[Path] = []
    for study in studies:
        latest = latest_run_dir(study)
        if latest is None:
            print(f"  {study.manifest.study_id}: no runs yet — skipping")
            continue
        analysis_path = latest / "_analysis.md"
        if analysis_path.is_file() and not args.rerun:
            print(
                f"  {study.manifest.study_id}: _analysis.md already exists "
                f"({analysis_path.relative_to(studies_root(vault_root).parent)}) — "
                f"--rerun to overwrite, skipping"
            )
            pass1_paths.append(analysis_path)
            continue
        print(
            f"  {study.manifest.study_id}: Pass-1 analyst on run {latest.name} …",
            flush=True,
        )
        user_prompt = build_pass1_user_prompt(study, latest)
        print(f"    prompt_chars={len(user_prompt):,}", flush=True)
        try:
            result = run_analyst(
                system_prompt_path=PERSONA_PER_STUDY,
                user_prompt=user_prompt,
                vault_cwd=vault_root,
                pass_label="per-study",
            )
        except AnalystError as exc:
            print(f"    ! Pass-1 failed: {exc}", file=sys.stderr)
            failures += 1
            continue
        path = persist_pass1(study, latest, result)
        pass1_paths.append(path)
        print(
            f"    → {path.relative_to(studies_root(vault_root).parent)}  "
            f"cost=${result.cost_usd:.4f}  elapsed={result.elapsed_ms / 1000:.1f}s",
            flush=True,
        )

    if failures:
        print(f"\nPass-1: {failures}/{len(studies)} failed.", file=sys.stderr)
        return 1
    print(f"\n✓ Pass-1 done: {len(pass1_paths)} _analysis.md file(s).")
    return 0


def cmd_pass2(args: argparse.Namespace, vault_root: Path) -> int:
    studies = list_studies(studies_root(vault_root))
    studies_with: list[tuple[Study, Path, Path]] = []
    for study in studies:
        latest = latest_run_dir(study)
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
    user_prompt = build_pass2_user_prompt(studies_with)
    print(f"    prompt_chars={len(user_prompt):,}", flush=True)
    try:
        result = run_analyst(
            system_prompt_path=PERSONA_CROSS_STUDY,
            user_prompt=user_prompt,
            vault_cwd=vault_root,
            pass_label="cross-study",
        )
    except AnalystError as exc:
        print(f"    ! Pass-2 failed: {exc}", file=sys.stderr)
        return 1

    path = persist_pass2(result, len(studies_with), vault_root=vault_root)
    print(
        f"    → {path.relative_to(analyses_root(vault_root).parent)}  "
        f"cost=${result.cost_usd:.4f}  elapsed={result.elapsed_ms / 1000:.1f}s",
        flush=True,
    )
    return 0


def cmd_default(args: argparse.Namespace, vault_root: Path) -> int:
    """No-flag default: Pass-1 over all studies + Pass-2.

    Also the entry point used by `flush.py` piggyback when
    `study_run_due` fires — Pass-1 happens per-study automatically;
    Pass-2 fires here when invoked with `--cross-study-only` or
    on its own schedule.
    """
    if not args.cross_study_only:
        rc = cmd_pass1(args, vault_root)
        if rc != 0:
            return rc
    if not args.no_pass2:
        return cmd_pass2(args, vault_root)
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
    vault_root = (
        args.vault.expanduser().resolve() if args.vault is not None else ROOT_DIR
    )
    return cmd_default(args, vault_root)


if __name__ == "__main__":
    sys.exit(main())
