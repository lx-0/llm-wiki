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

# Dispatched as a child process (`python scripts/publish/cli.py`): sys.path[0]
# is THIS directory, so `publish`/`core` need scripts/ on the path first —
# same bootstrap as bridge/cli.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from publish.corpus import (  # noqa: E402
    DEFAULT_ROOTS,
    count_non_markdown,
    load_manifest,
    manifest_store,
    map_slugs,
    migrate_manifest_layout,
)
from publish.delta import PublishPlan, build_payloads, plan_delta  # noqa: E402
from publish.describe import description_index  # noqa: E402

from core.state_store import StateStore  # noqa: E402


def build_publish_plan(
    vault: Path, store: StateStore, roots: tuple[str, ...] = DEFAULT_ROOTS
) -> tuple[PublishPlan, dict[str, str]]:
    """Manifest (layout-migrated) → stable slug map → payloads → delta plan."""
    migrate_manifest_layout(store)
    manifest = load_manifest(store)
    previous = {slug: entry.get("path", "") for slug, entry in manifest.items()}
    slug_map = map_slugs(vault, roots, previous=previous)
    knowledge_dir = vault / "knowledge"
    index_file = knowledge_dir / "index.md"
    index_text = index_file.read_text(encoding="utf-8") if index_file.exists() else ""
    index = description_index(index_text, knowledge_dir, vault)
    payloads = build_payloads(vault, slug_map, index)
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


def render_report(report) -> str:
    lines = [
        f"published: {len(report.created)} created, {len(report.updated)} updated, "
        f"{len(report.retracted)} retracted, {report.unchanged} unchanged"
        + (", start page written" if report.start_page_written else "")
    ]
    for slug, reason in report.skipped:
        lines.append(f"  SKIPPED  {slug}: {reason}")
    return "\n".join(lines)


def report_json(report) -> dict:
    return {
        "created": report.created,
        "updated": report.updated,
        "retracted": report.retracted,
        "skipped": [{"slug": s, "reason": r} for s, r in report.skipped],
        "start_page_written": report.start_page_written,
        "unchanged": report.unchanged,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wiki publish",
        description="Mirror knowledge/ into meinkontext (producer contract).",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="print the publish plan without writing anywhere")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="machine-readable output")
    parser.add_argument("--auth", action="store_true",
                        help="connect the producer: one-time browser OAuth consent")
    args = parser.parse_args(argv)

    if args.auth:
        from core.config import CONFIG

        from publish.oauth import DEFAULT_TOKEN_PATH, mint_interactive

        if not CONFIG.publish.endpoint:
            print("set publish.endpoint first (wiki config set publish.endpoint …)",
                  file=sys.stderr)
            return 1
        mint_interactive(CONFIG.publish.endpoint)
        print(f"producer connected — tokens stored at {DEFAULT_TOKEN_PATH}")
        return 0

    # Imported lazily so tests can drive the plan builder with explicit paths.
    from core.config import CONFIG
    from core.paths import ROOT_DIR

    roots = tuple(CONFIG.publish.roots)
    store = manifest_store()
    plan, slug_map = build_publish_plan(ROOT_DIR, store, roots)
    non_md = count_non_markdown(ROOT_DIR, roots)

    by_root: dict[str, int] = {}
    for rel in slug_map.values():
        root = rel.split("/", 1)[0]
        by_root[root] = by_root.get(root, 0) + 1
    breakdown = " · ".join(f"{r} {n}" for r, n in sorted(by_root.items()))

    if args.dry_run:
        if args.as_json:
            payload = to_json_payload(plan)
            payload["non_markdown_skipped"] = non_md
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(render_human(plan))
            print(f"corpora: {breakdown}")
            if non_md:
                print(
                    f"note: {non_md} non-markdown files in the publish roots have "
                    "no contract channel (markdown-only) and are not published"
                )
        return 0

    from publish.bootstrap import ensure_wiki, start_page_payload
    from publish.client import ContextMcpClient
    from publish.executor import execute_publish
    from publish.oauth import current_access_token

    cfg = CONFIG.publish
    if not cfg.enabled:
        print(
            "publish is disabled — enable with `wiki config set publish.enabled true` "
            "(and set publish.endpoint)",
            file=sys.stderr,
        )
        return 1

    # Token order: explicit env override wins (must be a USER token — org
    # api-keys are read-only for the write tools); default = the OAuth store
    # minted by `wiki publish --auth`, refreshed headlessly.
    import os

    token = os.environ.get("MEINKONTEXT_TOKEN", "").strip() or current_access_token()

    with ContextMcpClient(cfg.endpoint, token) as client:
        ensure_wiki(client, cfg.wiki_slug, cfg.wiki_name)
        start = start_page_payload(slug_map, cfg.wiki_name)
        report = execute_publish(client, store, plan, start, cfg.wiki_slug)

    if args.as_json:
        print(json.dumps(report_json(report), ensure_ascii=False))
    else:
        print(render_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
