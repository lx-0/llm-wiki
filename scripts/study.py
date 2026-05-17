"""CLI entry point for the `wiki study` subcommand family.

Sub-commands:

    wiki study list                                # show all studies + status
    wiki study run <study_id>                      # run all due instruments
    wiki study run <study_id> --instrument <slug>  # narrow to one ref
    wiki study new <id>                            # blank-stub a new study
    wiki study new <id> --fork-from <other>        # clone an existing one
    wiki study diff <run_a> <run_b>                # S04 stub (placeholder today)

A study is the parallelism unit. Two studies with overlapping
instruments run independently with their own state + run history.

State + scope:

    <vault>/<reports_dir>/studies/<id>/manifest.yaml   # immutable spec
                                       state.yaml     # last_run_at, run_count
                                       runs/<UTC-ts>/ # one dir per run
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Engine `scripts.*` imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.core.config import CONFIG  # noqa: E402
from scripts.core.paths import ROOT_DIR  # noqa: E402
from scripts.reports._engine.lib.render_summary import render_summary  # noqa: E402
from scripts.reports._engine.lib.timeline import (  # noqa: E402
    load_timeline,
    snapshot_from_dir,
)
from scripts.reports._engine.runner import run_inference  # noqa: E402
from scripts.reports._engine.study import (  # noqa: E402
    RunDirectory,
    Study,
    StudyManifest,
    acquire_study_lock,
    fork_study,
    list_studies,
    utc_now_iso,
)


log = logging.getLogger("study")


def _studies_root() -> Path:
    return ROOT_DIR / CONFIG.personal.reports_dir / "studies"


def cmd_list(args: argparse.Namespace) -> int:
    studies = list_studies(_studies_root())
    if not studies:
        print(
            f"(no studies found under {_studies_root()})\n"
            f"Hint: `wiki study new <id>` or seed via `wiki seed` (templates)."
        )
        return 0
    print(f"Studies under {_studies_root()}:\n")
    for s in studies:
        m = s.manifest
        last = s.state.last_run_at or "—"
        due = "DUE" if s.is_due() else "—"
        print(f"  {m.study_id:<32}  schedule={m.schedule:<10}  "
              f"runs={s.state.run_count:>3}  last={last:<26}  {due}")
        print(f"    title:       {m.title}")
        print(f"    instruments: {', '.join(r.alias or r.slug for r in m.instruments)}")
        print()
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    studies_root = _studies_root()
    study_dir = studies_root / args.study_id
    if not study_dir.is_dir():
        print(f"ERROR: study not found: {study_dir}", file=sys.stderr)
        print(
            f"Available studies: "
            f"{', '.join(s.manifest.study_id for s in list_studies(studies_root)) or '(none)'}",
            file=sys.stderr,
        )
        return 2

    try:
        study = Study.load(study_dir)
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: failed to load study {args.study_id!r}: {exc}", file=sys.stderr)
        return 2

    # Per-study flock prevents concurrent same-study runs (cross-study
    # runs proceed in parallel). Mirrors compile.py pattern.
    lock = acquire_study_lock(study.manifest.study_id)
    if lock is None:
        print(
            f"another `wiki study run {args.study_id}` is already in progress — "
            f"skipping. (Cross-study runs are not blocked.)",
            file=sys.stderr,
        )
        return 0

    try:
        # Optional: restrict to one instrument alias.
        instruments = list(study.manifest.instruments)
        if args.instrument:
            instruments = [
                r for r in instruments if (r.alias or r.slug) == args.instrument
            ]
            if not instruments:
                print(
                    f"ERROR: --instrument {args.instrument!r} not present in study "
                    f"{args.study_id!r}",
                    file=sys.stderr,
                )
                return 2

        timestamp = utc_now_iso()
        wall_start = time.perf_counter()
        print(
            f"\n=== wiki study run {args.study_id} @ {timestamp} "
            f"({len(instruments)} instrument(s)) ===\n"
        )

        with RunDirectory(study.runs_dir, timestamp) as run_dir:
            per_inst_results: list[tuple[str, Path]] = []
            for ref in instruments:
                if ref.source == "form":
                    # form-source instruments are operator-input only;
                    # S03 wedge ships only the inferred path. Skip with
                    # a visible message rather than silently dropping.
                    print(
                        f"  - {ref.alias or ref.slug} v{ref.version}: "
                        f"source=form — skipped (form-source path lands post-wedge)",
                        flush=True,
                    )
                    continue
                print(
                    f"  - {ref.alias or ref.slug} v{ref.version}: "
                    f"source={ref.source}; running …",
                    flush=True,
                )
                # run_inference writes the per-instrument report.
                # Override output_dir to point inside the run-dir's
                # instruments/ subdir.
                target_path = run_dir.instruments_dir / ref.report_filename
                # Use the slug for instrument lookup (the canonical
                # filesystem name); alias is just for output naming.
                report_path = run_inference(
                    ref.slug,
                    ref.version,
                    ROOT_DIR,
                    output_dir=run_dir.instruments_dir,
                )
                # run_inference names the file <slug>.md; rename if
                # alias differs.
                if report_path.name != ref.report_filename:
                    report_path.rename(target_path)
                    report_path = target_path
                per_inst_results.append((ref.alias or ref.slug, report_path))
                print(f"      → {report_path.relative_to(run_dir.tmp_dir)}", flush=True)

            # S04 — render the deterministic meta-report inside the
            # tmp dir before atomic commit. Builds the in-progress
            # snapshot from the tmp dir, appends to the cross-run
            # timeline (which already includes prior finalised runs),
            # writes _summary.md + chart SVGs.
            timeline = load_timeline(study.study_dir)
            new_snap = snapshot_from_dir(run_dir.tmp_dir, timestamp=timestamp)
            timeline.runs.append(new_snap)
            try:
                summary_path = render_summary(
                    study_id=study.manifest.study_id,
                    timeline=timeline,
                    summary_path=run_dir.tmp_dir / "_summary.md",
                    charts_dir=run_dir.charts_dir,
                )
                print(f"      → meta-report: {summary_path.relative_to(run_dir.tmp_dir)}",
                      flush=True)
            except Exception as exc:
                # Failure here MUST not poison the run — per-instrument
                # reports are the source of truth. Log + continue, the
                # operator can re-render meta later by re-running
                # render_summary against the finalised run.
                print(f"      ! meta-report render failed: {exc}", flush=True)

            # S05: Pass-1 analyst runs OUTSIDE the RunDirectory tmp envelope.
            # Reason: Pass-1 wants to read the per-instrument reports +
            # _summary.md from their FINALISED paths (so absolute paths
            # in the analyst's prompt resolve correctly when it uses
            # Read tool to chase citations). Atomic-rename happens at
            # RunDirectory.__exit__; we trigger Pass-1 right after.

        elapsed = time.perf_counter() - wall_start
        # Persist state — only after the RunDirectory atomically renamed.
        study.state.mark_run(datetime.now(timezone.utc))
        study.state.write(study.state_path)
        print(
            f"\n✓ Study run complete in {elapsed:.1f}s — "
            f"{len(per_inst_results)} instrument report(s) in "
            f"{study.runs_dir / timestamp}\n"
            f"  state updated: last_run_at={study.state.last_run_at} "
            f"run_count={study.state.run_count}"
        )

        # S05: trigger Pass-1 analyst on this freshly-finalised run.
        # Soft-fail policy: a Pass-1 error doesn't undo the run (per-
        # instrument reports + _summary.md are the source of truth).
        if not args.no_analyze:
            try:
                from scripts.reports._engine.lib.analyst import (
                    AnalystError, run_analyst,
                )
                from scripts.analyze import (
                    PERSONA_PER_STUDY,
                    _build_pass1_user_prompt,
                    _persist_pass1,
                )

                final_run_dir = study.runs_dir / timestamp
                user_prompt = _build_pass1_user_prompt(study, final_run_dir)
                print(
                    f"\n→ Pass-1 analyst on this run "
                    f"(prompt_chars={len(user_prompt):,}) …",
                    flush=True,
                )
                result = run_analyst(
                    system_prompt_path=PERSONA_PER_STUDY,
                    user_prompt=user_prompt,
                    vault_cwd=ROOT_DIR,
                    pass_label="per-study",
                )
                analysis_path = _persist_pass1(study, final_run_dir, result)
                print(
                    f"  → {analysis_path.relative_to(study.runs_dir.parent.parent)}  "
                    f"cost=${result.cost_usd:.4f}  "
                    f"elapsed={result.elapsed_ms / 1000:.1f}s"
                )
            except AnalystError as exc:
                print(
                    f"  ! Pass-1 analyst failed: {exc} "
                    f"(per-instrument reports unaffected; "
                    f"`wiki analyze --study {study.manifest.study_id}` "
                    f"to retry)",
                    file=sys.stderr,
                )
        return 0
    finally:
        lock.close()


def cmd_new(args: argparse.Namespace) -> int:
    studies_root = _studies_root()
    studies_root.mkdir(parents=True, exist_ok=True)
    if args.fork_from:
        source_dir = studies_root / args.fork_from
        if not source_dir.is_dir():
            print(
                f"ERROR: source study {args.fork_from!r} not found at {source_dir}",
                file=sys.stderr,
            )
            return 2
        try:
            source = Study.load(source_dir)
        except (ValueError, FileNotFoundError) as exc:
            print(f"ERROR: source study unreadable: {exc}", file=sys.stderr)
            return 2
        try:
            new_dir = fork_study(source, args.study_id, studies_root)
        except (ValueError, FileExistsError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(
            f"✓ Forked study {args.fork_from!r} → {args.study_id!r}\n"
            f"  manifest: {new_dir / 'manifest.yaml'}\n"
            f"  Edit the manifest to customise instruments / schedule / title, "
            f"then `wiki study run {args.study_id}`."
        )
        return 0

    # Blank-stub: write a minimal manifest the operator can edit.
    new_dir = studies_root / args.study_id
    if new_dir.exists():
        print(f"ERROR: study {args.study_id!r} already exists at {new_dir}", file=sys.stderr)
        return 2
    try:
        manifest = StudyManifest.from_dict({
            "study_id": args.study_id,
            "title": f"{args.study_id} (rename me)",
            "created": datetime.now(timezone.utc).isoformat(),
            "schedule": "manual",
            "instruments": [
                {"slug": "phq-9", "version": "1.0.0", "source": "inferred"},
            ],
            "notes": "Stub manifest — edit `instruments` and `schedule`, then `wiki study run`.",
        })
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    new_dir.mkdir(parents=True)
    import yaml
    (new_dir / "manifest.yaml").write_text(
        yaml.safe_dump(
            manifest.to_dict(),
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    print(
        f"✓ Stubbed study {args.study_id!r}\n"
        f"  manifest: {new_dir / 'manifest.yaml'}\n"
        f"  Edit the file, then `wiki study run {args.study_id}`."
    )
    return 0


def cmd_piggyback(args: argparse.Namespace) -> int:
    """Iterate all studies, run every one whose schedule is due.

    Called from flush.py piggyback machinery. Per-study flock means
    concurrent piggyback invocations + an operator-initiated
    `wiki study run` won't double-score the same study; cross-study
    runs proceed in parallel as designed.
    """
    studies_root = _studies_root()
    studies = list_studies(studies_root)
    due = [s for s in studies if s.is_due()]
    if not due:
        print(f"study_run_due: 0/{len(studies)} studies due — nothing to do.")
        return 0

    print(
        f"study_run_due: {len(due)}/{len(studies)} studies due "
        f"({', '.join(s.manifest.study_id for s in due)})"
    )
    failures = 0
    for s in due:
        # Re-use cmd_run by faking the args namespace.
        run_args = argparse.Namespace(
            study_id=s.manifest.study_id, instrument=None, no_analyze=False,
        )
        rc = cmd_run(run_args)
        if rc != 0:
            failures += 1
    if failures:
        print(f"study_run_due: {failures}/{len(due)} run(s) failed.")
        return 1
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    # S04 will implement: read two run-dirs, diff per-instrument scores,
    # render a markdown table of deltas. For S03 wedge, stubbed.
    print(
        f"`wiki study diff` is stubbed pending S04 (meta-report layer).\n"
        f"  Requested: {args.run_a} vs {args.run_b}\n"
        f"  Lands after S04-T04 (_summary.md + comparison renderer)."
    )
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Study lifecycle commands")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List studies with run status.")
    p_list.set_defaults(func=cmd_list)

    p_run = sub.add_parser("run", help="Run a study.")
    p_run.add_argument("study_id")
    p_run.add_argument(
        "--instrument",
        default=None,
        help="Limit to one instrument alias from the manifest.",
    )
    p_run.add_argument(
        "--no-analyze",
        action="store_true",
        help="Skip Pass-1 analyst after the run (deterministic study output only).",
    )
    p_run.set_defaults(func=cmd_run)

    p_new = sub.add_parser("new", help="Create a new study (stub or fork).")
    p_new.add_argument("study_id")
    p_new.add_argument("--fork-from", default=None)
    p_new.set_defaults(func=cmd_new)

    p_diff = sub.add_parser("diff", help="Compare two runs (stubbed pending S04).")
    p_diff.add_argument("run_a")
    p_diff.add_argument("run_b")
    p_diff.set_defaults(func=cmd_diff)

    p_pb = sub.add_parser(
        "piggyback",
        help="flush.py entry-point: run all studies whose schedule is due.",
    )
    p_pb.set_defaults(func=cmd_piggyback)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
