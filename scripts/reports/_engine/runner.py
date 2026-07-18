"""M019-S02-T04 — end-to-end inference runner for one instrument.

Glues together everything from S01 + S02-T01..T03:

  1. Load instrument (id, items.yaml, cutoffs.yaml, instrument.yaml).
  2. Resolve substrate scope (files within instrument's lookback,
     filtered to CLINICAL_DEFAULT_SUBSTRATE_GLOBS for the wedge).
  3. Render the inference prompt (`prompts/reports/infer_instrument.md`)
     with items inline and substrate listed as paths (agent reads on
     demand — keeps prompt small + matches the audit's headroom story).
  4. SHA256-hash the rendered prompt → prompt_version (immutable
     identifier of which prompt version produced this run).
  5. Run each `InferenceBatch` through `infer_batch()` (single batch
     for PHQ-9 since no subscales).
  6. Compose into `InferenceRun`, hand answers to `score_instrument()`
     for deterministic banding.
  7. Persist the report markdown under
     `<vault>/reports/_adhoc/<ts>/<slug>.md` with embedded methodology.

Wedge target: PHQ-9. T05 will add 4 more instruments without touching
this file (instrument-yaml only).

Usage:
    uv run python scripts/reports/_engine/runner.py \\
        --vault ~/Library/Mobile\\ Documents/.../lxw \\
        --instrument phq-9 \\
        --version 1.0.0
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import textwrap
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import yaml  # noqa: E402

from scripts.core.prompts import render  # noqa: E402
from scripts.reports._engine.instrument import Instrument, load_instrument  # noqa: E402
from scripts.reports._engine.lib.inference import (  # noqa: E402
    InferenceRun,
    default_batches,
    infer_batch,
)
from scripts.reports._engine.substrate_scope import (  # noqa: E402
    CLINICAL_DEFAULT_SUBSTRATE_GLOBS,
    resolve_substrate_files,
)
from scripts.reports._engine.lib.verify_report import verify_report  # noqa: E402
from scripts.reports._engine.score import score_instrument  # noqa: E402


def _load_operator_answers(
    study_dir: Path | None,
    instrument_slug: str,
) -> dict[str, int]:
    """Load operator-supplied answers for one instrument from a study's
    `operator_answers.yaml`. Returns {item_id: int} or empty dict.

    The yaml file shape:

      <instrument-slug>:
        "<item_id>":
          value: <int in instrument scale>
          answered_at: <iso timestamp>
          note: <optional free-form>

    Operator-supplied answers take precedence over inferred answers
    in scoring. Items present here are also excluded from the
    inference prompt's items_block so the SDK call doesn't waste
    tokens guessing items the operator has already answered.
    """
    if study_dir is None:
        return {}
    fp = study_dir / "operator_answers.yaml"
    if not fp.is_file():
        return {}
    raw = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return {}
    instr_section = raw.get(instrument_slug) or {}
    if not isinstance(instr_section, dict):
        return {}
    out: dict[str, int] = {}
    for item_id, entry in instr_section.items():
        if isinstance(entry, dict) and "value" in entry:
            try:
                out[str(item_id)] = int(entry["value"])
            except (TypeError, ValueError):
                continue
    return out


def _render_items_block(
    instrument_dir: Path,
    *,
    only_ids: set[str] | None = None,
    exclude_ids: set[str] | None = None,
) -> str:
    """Render the items block for the prompt, including substrate_inferable
    flag so the agent honours the curation. Reads items.yaml directly
    rather than going through the loader because we want the raw
    `text` and `substrate_inferable` keys verbatim.

    Args:
        only_ids: when set, render only items whose id is in this set —
            scopes the prompt to one batch's items for multi-subscale
            instruments (ASRS Part-A / Part-B). If None, render all
            items (single-batch case).
    """
    raw = yaml.safe_load((instrument_dir / "items.yaml").read_text(encoding="utf-8"))
    lines: list[str] = []
    for item in raw:
        if only_ids is not None and str(item["id"]) not in only_ids:
            continue
        if exclude_ids is not None and str(item["id"]) in exclude_ids:
            continue
        flag = item.get("substrate_inferable", True)
        flag_str = "true" if flag else "false"
        sub = item.get("subscale")
        sub_suffix = f"  [subscale: {sub}]" if sub else ""
        rev = " [REVERSE-CODED]" if item.get("reverse_coded") else ""
        lines.append(
            f"- **{item['id']}** (substrate_inferable: {flag_str}){sub_suffix}{rev}\n"
            f"    \"{item['text']}\""
        )
    return "\n".join(lines)


def _render_substrate_block(paths: list[Path], vault_root: Path) -> str:
    """Render substrate paths as a bulleted list the agent can read
    on demand. Paths are relative to vault root so the agent's Read
    calls don't leak absolute paths into evidence citations.
    """
    if not paths:
        return "  (no substrate files matched the lookback window — answers will be `null` across the board)"
    rels = sorted(
        str(p.relative_to(vault_root)) for p in paths if p.is_relative_to(vault_root)
    )
    return "\n".join(f"- `{r}`" for r in rels)


def _persist_report(
    *,
    output_dir: Path,
    timestamp: str,
    instrument: Instrument,
    scored,
    run: InferenceRun,
    rendered_batches: list[tuple[str, str, str]],
    prompt_version: str,
    lookback_days: int,
    substrate_paths: list[Path],
    vault_root: Path,
) -> Path:
    """Write the run's report markdown with embedded methodology.

    `rendered_batches` is `[(batch_label, prompt_version, rendered_prompt), ...]`
    — the ACTUAL prompts sent to the SDK this run (operator-answered items
    excluded, scoped per batch), so the embedded prompt block matches the
    hashed `prompt_version` instead of a divergent second render.
    """
    meta = instrument.meta
    instrument_dir = instrument.instrument_path
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{meta.slug}.md"

    score = scored.score
    inference_cfg = meta.inference

    # Frontmatter — embedded provenance fields per the Q6 durability
    # posture: a future AI reader must be able to interpret this
    # report without the engine.
    fm = {
        "instrument": meta.slug,
        "version": meta.version,
        "title": meta.title,
        "domain": meta.domain,
        "run_timestamp": timestamp,
        "run_kind": "ad-hoc",
        "informant_report": True,
        "total_score": score.total,
        # Loader-surfaced scoring geometry so downstream (timeline +
        # meta-report) never re-derives it: likert scale, the highest
        # achievable total, and which bands are clinically elevated.
        "likert": {"lo": meta.likert.lo, "hi": meta.likert.hi},
        "max_total": instrument.max_total,
        "concern_bands": list(instrument.concern_bands),
        "band": scored.band,
        "bandable": scored.bandable,
        "coverage": {
            "answered_at_high_confidence": score.answered,
            "total_items": score.total_items,
            "coverage_pct": score.coverage_pct,
            "bandable_threshold": scored.bandable_threshold,
        },
        "scope": {
            "lookback_days": lookback_days,
            "file_count": len(substrate_paths),
            "globs": list(CLINICAL_DEFAULT_SUBSTRATE_GLOBS),
        },
        # Per-item normalised values for downstream per-instrument
        # radar rendering. Reverse-coded items already flipped so
        # higher = more burden uniformly. Items not in this dict were
        # null (substrate_inferable:false OR confidence below threshold).
        "per_item": dict(score.per_item_normalised),
        "model_id": run.batches[0].model_id if run.batches else "",
        "prompt_version": prompt_version,
        "cost_usd": round(run.total_cost_usd, 4),
        "elapsed_ms": run.total_elapsed_ms,
        "engine_version": "M019-S02-T04",
    }

    lines: list[str] = []
    lines.append("---")
    lines.append(yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip())
    lines.append("---\n")

    lines.append(f"# {meta.title} — {timestamp}\n")
    lines.append(
        "> **Informant Report.** This score was inferred by an LLM "
        "observer reading the operator's substrate (daily logs, voice "
        "notes, health data, transcripts) over the lookback window — "
        "NOT self-reported. Methodology is embedded below; the report "
        "is durable independent of the engine.\n"
    )

    # Score block
    band_str = scored.band if scored.band else "*partial, not bandable*"
    lines.append("## Score\n")
    lines.append(
        f"- **Total:** {score.total} / {instrument.max_total}"
    )
    lines.append(f"- **Band:** {band_str}")
    lines.append(
        f"- **Coverage:** {score.answered} / {score.total_items} items "
        f"({score.coverage_pct}%) at confidence ≥ "
        f"{inference_cfg.min_confidence}"
    )
    lines.append(f"- **Bandable threshold:** {scored.bandable_threshold}%\n")

    # Per-item table
    lines.append("## Items\n")
    lines.append("| ID | Answer | Confidence | Evidence count | Reasoning |")
    lines.append("|---|---|---|---|---|")
    for item_id, inf in sorted(run.per_item.items(), key=lambda kv: kv[0]):
        ans = "—" if inf.answer is None else str(inf.answer)
        conf = f"{inf.confidence:.2f}"
        ev_count = len(inf.evidence)
        # Truncate reasoning to one line in the table; full text below.
        reasoning_short = inf.reasoning.replace("\n", " ").strip()
        if len(reasoning_short) > 100:
            reasoning_short = reasoning_short[:97] + "..."
        lines.append(f"| {item_id} | {ans} | {conf} | {ev_count} | {reasoning_short} |")
    lines.append("")

    # Per-item details (expandable)
    lines.append("## Per-item detail\n")
    for item_id, inf in sorted(run.per_item.items(), key=lambda kv: kv[0]):
        lines.append(f"### Item {item_id}\n")
        lines.append(f"- Answer: `{inf.answer}`")
        lines.append(f"- Confidence: `{inf.confidence:.2f}`")
        if inf.reasoning:
            lines.append(f"- Reasoning: {inf.reasoning}")
        if inf.evidence:
            lines.append("- Evidence:")
            for ev in inf.evidence:
                line_str = f":{ev.line}" if ev.line else ""
                lines.append(f"  - `{ev.file}{line_str}`")
                if ev.quote:
                    quote = ev.quote.replace("\n", " ").strip()
                    if len(quote) > 240:
                        quote = quote[:237] + "..."
                    lines.append(f"    > {quote}")
        lines.append("")

    # Embedded methodology — durable record
    lines.append("## Embedded methodology\n")
    lines.append(
        "<details><summary>Items (verbatim from items.yaml)</summary>\n"
    )
    lines.append("```yaml")
    lines.append(
        (instrument_dir / "items.yaml").read_text(encoding="utf-8").strip()
    )
    lines.append("```\n</details>\n")

    lines.append(
        "<details><summary>Cutoffs (verbatim from cutoffs.yaml)</summary>\n"
    )
    lines.append("```yaml")
    lines.append(
        (instrument_dir / "cutoffs.yaml").read_text(encoding="utf-8").strip()
    )
    lines.append("```\n</details>\n")

    lines.append(
        "<details><summary>Instrument meta (verbatim from instrument.yaml)</summary>\n"
    )
    lines.append("```yaml")
    lines.append(
        (instrument_dir / "instrument.yaml").read_text(encoding="utf-8").strip()
    )
    lines.append("```\n</details>\n")

    lines.append(
        "<details><summary>Prompt rendered for this run</summary>\n"
    )
    if not rendered_batches:
        lines.append(
            "_(no SDK call this run — every item was operator-answered, "
            "so no inference prompt was rendered.)_\n"
        )
    else:
        for label, pv, prompt_text in rendered_batches:
            lines.append(f"**Batch `{label}`** (prompt_version `{pv}`)\n")
            lines.append("```")
            lines.append(prompt_text)
            lines.append("```\n")
    lines.append("</details>\n")

    lines.append(
        "<details><summary>Scope-resolved substrate paths</summary>\n"
    )
    for p in sorted(substrate_paths):
        try:
            rel = p.relative_to(vault_root)
        except ValueError:
            rel = p
        lines.append(f"- `{rel}`")
    lines.append("\n</details>\n")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def run_inference(
    instrument_slug: str,
    instrument_version: str,
    vault_root: Path,
    instruments_root: Path | None = None,
    output_dir: Path | None = None,
    study_dir: Path | None = None,
) -> Path:
    """Run one full inference + persistence cycle. Returns report path."""
    if instruments_root is None:
        instruments_root = Path(__file__).resolve().parent / "instruments"
    instrument_dir = instruments_root / instrument_slug / f"v{instrument_version}"
    if not instrument_dir.is_dir():
        raise FileNotFoundError(f"Instrument not found: {instrument_dir}")

    print(f"Loading instrument: {instrument_dir}", flush=True)
    instrument = load_instrument(instrument_dir)
    lookback_days = instrument.meta.inference.default_lookback_days
    print(f"  slug={instrument.meta.slug} v{instrument.meta.version}  "
          f"items={instrument.total_items}  lookback={lookback_days}d", flush=True)

    print("Resolving substrate scope...", flush=True)
    paths = resolve_substrate_files(
        vault_root, CLINICAL_DEFAULT_SUBSTRATE_GLOBS, lookback_days
    )
    print(f"  {len(paths)} files matched.", flush=True)

    # Build prompt vars
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Load operator-supplied answers (subset of items the operator
    # filled in via `wiki study answer …`). These items are excluded
    # from the SDK prompt + take precedence over inferred answers at
    # scoring time. Empty dict when no operator_answers.yaml present.
    operator_answers = _load_operator_answers(study_dir, instrument.meta.slug)
    omit_ids = set(operator_answers.keys())
    if operator_answers:
        print(
            f"  operator-supplied answers: {len(operator_answers)} item(s) — "
            f"{sorted(operator_answers.keys())} (excluded from inference)",
            flush=True,
        )

    # Optional per-instrument model override from instrument.yaml's
    # `inference.model:` field. Defaults to the engine-default model
    # (claude-haiku-4-5) when not set. Used for instruments where
    # Haiku's confidence-conservativism caps coverage at 0% despite
    # substrate evidence (ISI sleep items 1-3 = Oura observable).
    instrument_model = instrument.meta.inference.model

    # Determine batches; drop operator-answered items per batch + skip
    # batches that become empty.
    raw_batches = default_batches(instrument)
    batches = []
    for b in raw_batches:
        filtered = tuple(it for it in b.items if it.id not in omit_ids)
        if filtered:
            batches.append(type(b)(label=b.label, items=filtered))
    if not batches:
        print("  all items operator-answered — skipping SDK call entirely.", flush=True)
    else:
        print(f"  batches: {len(batches)} ({', '.join(b.label for b in batches)})", flush=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    output_dir = output_dir or (vault_root / "reports" / "_adhoc" / timestamp)

    run = InferenceRun(
        instrument_slug=instrument.meta.slug,
        instrument_version=instrument.meta.version,
    )

    # Capture the ACTUAL prompt sent per batch (label, prompt_version,
    # rendered text) so the report embeds exactly what was hashed into
    # prompt_version — not a divergent second render with full items.
    rendered_batches: list[tuple[str, str, str]] = []

    # For multi-batch instruments we'd subset items_block per batch.
    # Wedge instruments are single-batch — items_block covers the
    # whole instrument. Post-wedge: render only this batch's items.
    for batch in batches:
        # Per-batch substrate block — wedge uses the same scope for
        # every batch since the substrate-set is instrument-level.
        substrate_block = _render_substrate_block(paths, vault_root)

        # Render items_block scoped to THIS batch's item-ids so the
        # agent's JSON output naturally constrains to just that subset.
        # Earlier design relied on `batch_label` alone — Haiku ignored
        # it and returned all items, tripping JSON-schema validation
        # (failure surfaced on first ASRS-v1.1 run, 2026-05-17).
        batch_items_block = _render_items_block(
            instrument_dir,
            only_ids={it.id for it in batch.items},
        )
        rendered_prompt = render(
            "reports/infer_instrument",
            instrument_slug=instrument.meta.slug,
            instrument_version=instrument.meta.version,
            instrument_title=instrument.meta.title,
            instrument_domain=instrument.meta.domain,
            likert_lo=instrument.meta.likert.lo,
            likert_hi=instrument.meta.likert.hi,
            lookback_days=lookback_days,
            today=today,
            batch_label=batch.label,
            items_block=batch_items_block,
            substrate_block=substrate_block,
        )
        prompt_version = hashlib.sha256(rendered_prompt.encode("utf-8")).hexdigest()[:16]
        rendered_batches.append((batch.label, prompt_version, rendered_prompt))
        print(f"  batch={batch.label}  prompt_chars={len(rendered_prompt):,}  "
              f"prompt_version={prompt_version}", flush=True)

        t0 = time.perf_counter()
        infer_kwargs = {
            "vault_cwd": vault_root,
            "prompt_version": prompt_version,
        }
        if instrument_model:
            infer_kwargs["model"] = instrument_model
        result = infer_batch(
            rendered_prompt,
            batch,
            **infer_kwargs,
        )
        dt = time.perf_counter() - t0
        print(f"    → answered={sum(1 for inf in result.items.values() if inf.answer is not None)}"
              f"/{len(result.items)}  "
              f"cost=${result.cost_usd:.4f}  elapsed={dt:.1f}s", flush=True)
        run.batches.append(result)

    # Score deterministically — merge operator-supplied answers
    # over inferred. Operator wins where both exist.
    answers = {**run.answers, **operator_answers}
    scored = score_instrument(instrument_dir, answers)
    print(f"\nScore: total={scored.score.total}  band={scored.band}  "
          f"coverage={scored.coverage_pct}%  bandable={scored.bandable}", flush=True)

    # Persist. First batch's prompt_version is the canonical frontmatter
    # identifier; every batch's ACTUAL prompt is embedded verbatim.
    first_pv = run.batches[0].prompt_version if run.batches else ""
    report_path = _persist_report(
        output_dir=output_dir,
        timestamp=timestamp,
        instrument=instrument,
        scored=scored,
        run=run,
        rendered_batches=rendered_batches,
        prompt_version=first_pv,
        lookback_days=lookback_days,
        substrate_paths=paths,
        vault_root=vault_root,
    )
    # M019-S04-T05: verify embedded-methodology contract on the freshly-
    # written report. Wedge philosophy = warn, don't abort: a single
    # bad report shouldn't block the rest of a multi-instrument run.
    verification = verify_report(report_path)
    if not verification.ok:
        print(
            f"  ⚠ embedded-methodology check FAILED: {verification.summary}",
            flush=True,
        )

    print(f"\nReport persisted: {report_path}", flush=True)
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--instrument", required=True, help="slug, e.g. phq-9")
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override output dir (defaults to <vault>/reports/_adhoc/<ts>/)",
    )
    args = parser.parse_args()
    try:
        run_inference(
            args.instrument,
            args.version,
            args.vault.expanduser().resolve(),
            output_dir=args.output_dir,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
