"""`wiki publish` — mirror knowledge/ into meinkontext (M030).

S01 ships the PLAN side: `--dry-run` prints exactly what a live publish would
do (create/update/retract/unchanged, per the content-hash delta), with a
`--json` seam for GUI/agent consumers. Live execution lands in S02.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from publish.corpus import load_manifest, manifest_store, map_slugs
from publish.delta import PublishPlan, build_payloads, plan_delta
from publish.describe import description_index

from core.state_store import StateStore


def build_publish_plan(
    knowledge_dir: Path, vault: Path, store: StateStore
) -> tuple[PublishPlan, dict[str, str]]:
    """Manifest → stable slug map → payloads → delta plan."""
    manifest = load_manifest(store)
    previous = {slug: entry.get("path", "") for slug, entry in manifest.items()}
    slug_map = map_slugs(knowledge_dir, previous=previous)
    index_file = knowledge_dir / "index.md"
    index_text = index_file.read_text(encoding="utf-8") if index_file.exists() else ""
    index = description_index(index_text, knowledge_dir, vault)
    payloads = build_payloads(knowledge_dir, vault, slug_map, index)
    return plan_delta(payloads, manifest), slug_map


def to_json_payload(plan: PublishPlan) -> dict:
    """Machine seam (C07): stable shape for GUI/agent consumers."""
    return {
        "create": [{"slug": p.slug, "path": p.rel} for p in plan.create],
        "update": [{"slug": p.slug, "path": p.rel} for p in plan.update],
        "retract": [{"slug": slug, "path": rel} for slug, rel in plan.retract],
        "unchanged": plan.unchanged,
    }


def render_human(plan: PublishPlan) -> str:
    lines = [
        f"publish plan: {len(plan.create)} create, {len(plan.update)} update, "
        f"{len(plan.retract)} retract, {plan.unchanged} unchanged"
    ]
    for label, payloads in (("create", plan.create), ("update", plan.update)):
        for p in payloads:
            lines.append(f"  {label}   {p.slug}  ({p.rel})")
    for slug, rel in plan.retract:
        lines.append(f"  retract  {slug}  ({rel})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wiki publish",
        description="Mirror knowledge/ into meinkontext (producer contract).",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="print the publish plan without writing anywhere")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="machine-readable plan output")
    args = parser.parse_args(argv)

    # Imported lazily so tests can drive the plan builder with explicit paths.
    from core.paths import KNOWLEDGE_DIR, ROOT_DIR

    store = manifest_store()
    plan, _ = build_publish_plan(KNOWLEDGE_DIR, ROOT_DIR, store)

    if args.as_json:
        print(json.dumps(to_json_payload(plan), ensure_ascii=False))
    else:
        print(render_human(plan))

    if not args.dry_run:
        print(
            "live publish is not implemented yet (M030-S02) — run with --dry-run",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
