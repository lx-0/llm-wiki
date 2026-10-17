"""Original-file sync and article projection over the meinKontext producer contract."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC
from pathlib import Path

from core.console import say
from core.state_store import StateStore
from publish.corpus import (
    DEFAULT_ROOTS,
    load_manifest,
    manifest_store,
    map_slugs,
)
from publish.delta import PublishPlan, build_payloads, plan_delta
from publish.describe import description_index
from publish.sources import (
    effective_moves,
    inventory_sources,
    move_batch_id,
    source_plan,
    validate_moves,
)


def build_publish_plan(
    vault: Path,
    store: StateStore,
    roots: tuple[str, ...] = DEFAULT_ROOTS,
    moves: dict[str, str] | None = None,
) -> tuple[PublishPlan, dict[str, str]]:
    """Manifest (layout-migrated) → stable slug map → payloads → delta plan."""
    manifest = {slug: dict(entry) for slug, entry in load_manifest(store).items()}
    if store.load().get("layout") != "vault-rel":
        for entry in manifest.values():
            if entry.get("path") and not entry["path"].startswith("knowledge/"):
                entry["path"] = "knowledge/" + entry["path"]
    previous = {
        slug: (moves or {}).get(entry.get("path", ""), entry.get("path", ""))
        for slug, entry in manifest.items()
    }
    for entry in store.load().get("sources", {}).values():
        if entry.get("article_id"):
            previous.setdefault(
                entry["article_id"], (moves or {}).get(entry["path"], entry["path"])
            )
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
    parser.add_argument(
        "--dry-run", action="store_true", help="print the publish plan without writing anywhere"
    )
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="machine-readable output"
    )
    parser.add_argument(
        "--auth", action="store_true", help="connect the producer: one-time browser OAuth consent"
    )
    parser.add_argument(
        "--piggyback",
        action="store_true",
        help="cadence mode: quiet no-op when publish is disabled",
    )
    parser.add_argument(
        "--move",
        action="append",
        default=[],
        metavar="OLD=NEW",
        help="reconcile a moved source without changing its identity",
    )
    parser.add_argument(
        "--confirm-deletions",
        action="store_true",
        help="confirm deletion candidates after checking that they are not moves",
    )
    parser.add_argument(
        "--accept-scope-change",
        action="store_true",
        help="accept a changed root list after reviewing its dry run",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="only attach original paths/bytes to existing articles; no article versions or archives",
    )
    args = parser.parse_args(argv)

    if args.auth:
        from core.config import CONFIG
        from publish.oauth import DEFAULT_TOKEN_PATH, mint_interactive

        if not CONFIG.publish.endpoint:
            say("set publish.endpoint first (wiki config set publish.endpoint …)", file=sys.stderr)
            return 1
        mint_interactive(CONFIG.publish.endpoint)
        say(f"producer connected — tokens stored at {DEFAULT_TOKEN_PATH}")
        return 0

    # Imported lazily so tests can drive the plan builder with explicit paths.
    from core.config import CONFIG
    from core.paths import ROOT_DIR

    # Enabled-gate BEFORE any corpus walk: the piggyback fires on cadence and
    # must be a designed no-op (exit 0) on disabled vaults; a human gets the
    # actionable error. Dry-run stays available either way.
    if not args.dry_run and not CONFIG.publish.enabled:
        if args.piggyback:
            say("publish piggyback: publish.enabled=false — skipping", file=sys.stderr)
            return 0
        say(
            "publish is disabled — enable with `wiki config set publish.enabled true` "
            "(and set publish.endpoint)",
            file=sys.stderr,
        )
        return 1

    return run_publish(ROOT_DIR, CONFIG.publish, args)


def source_summary(sources) -> dict:
    return {
        "write": [
            {"key": i.key, "path": i.file.path, "bytes": i.file.size, "directory": i.file.directory}
            for i in sources.write
        ],
        "archive": [{"key": k, "path": e["path"]} for k, e in sources.archive],
        "unchanged": sources.unchanged,
        "bytes": sum(f.size for f in sources.inventory),
    }


def source_publish_plan(vault, store, roots, requested_moves, backfill):
    moves = effective_moves(store.load(), requested_moves)
    inventory = inventory_sources(vault, roots)
    validate_moves(inventory, store.load(), moves)
    plan, slug_map = build_publish_plan(vault, store, roots, moves)
    sources = source_plan(
        inventory,
        store.load(),
        slug_map,
        moves,
        {p.slug for p in plan.create + plan.update},
        roots=roots,
    )
    if backfill:
        sources.write = [
            i
            for i in sources.write
            if i.article_id in store.load().get("articles", {}) and not i.previous
        ]
        sources.archive = []
        plan = PublishPlan()
    sources.move_batch = move_batch_id(requested_moves) if moves else None
    return plan, slug_map, sources


def run_publish(vault: Path, cfg, args) -> int:
    import os
    from datetime import datetime

    from core.state_store import locked
    from publish.bootstrap import ensure_wiki, start_page_payload
    from publish.client import ContextMcpClient
    from publish.corpus import migrate_manifest_layout
    from publish.executor import execute_publish
    from publish.oauth import current_access_token
    from publish.source_sync import execute_source_publish, require_source_contract

    roots = tuple(cfg.roots)
    store = manifest_store()
    moves = {}
    for move in args.move:
        old, separator, new = move.partition("=")
        if not separator or old in moves:
            raise ValueError("--move expects distinct OLD=NEW source paths")
        moves[old] = new
    requested_moves = moves
    plan, slug_map, sources = source_publish_plan(
        vault, store, roots, requested_moves, args.backfill
    )
    summary = source_summary(sources)
    if args.dry_run:
        if args.as_json:
            say(json.dumps({**to_json_payload(plan), "sources": summary}, ensure_ascii=False))
        else:
            say(render_human(plan))
            say(
                f"sources: {len(sources.write)} write, {len(sources.archive)} archive, {sources.unchanged} unchanged; {summary['bytes']} bytes"
            )
        return 0
    target = {"endpoint": cfg.endpoint, "wiki": cfg.wiki_slug}
    if store.load().get("source_target", target) != target:
        raise ValueError(
            "publish destination changed; use a separate manifest for the new destination"
        )
    env_token = os.environ.get("MEINKONTEXT_TOKEN", "").strip()

    def provider(force: bool = False) -> str:
        return current_access_token(force_refresh=force)

    client = (
        ContextMcpClient(cfg.endpoint, env_token)
        if env_token
        else ContextMcpClient(cfg.endpoint, token_provider=provider)
    )
    with locked(store.path.with_suffix(".publish.lock")), client:
        # Re-plan under the run lock so a waiting invocation never uses stale revisions.
        store.reload()
        plan, slug_map, sources = source_publish_plan(
            vault, store, roots, requested_moves, args.backfill
        )
        if (
            store.load().get("source_roots", list(roots)) != list(roots)
            and not args.accept_scope_change
        ):
            raise ValueError(
                "publish roots changed; review --dry-run and explicitly --accept-scope-change"
            )
        if store.load().get("source_target", target) != target:
            raise ValueError("publish destination changed while waiting for the run lock")
        require_source_contract(client)
        ensure_wiki(client, cfg.wiki_slug, cfg.wiki_name)
        migrate_manifest_layout(store)
        store.update(lambda d: d.update({"source_target": target, "source_roots": list(roots)}))
        store.update(
            lambda d: d.update(
                {
                    "last_source_run": {
                        "status": "running",
                        "started_at": datetime.now(UTC).isoformat(),
                        "files": len(sources.inventory),
                        "bytes": sum(f.size for f in sources.inventory),
                    }
                }
            )
        )
        report = execute_source_publish(
            client,
            store,
            vault,
            sources,
            plan,
            cfg.wiki_slug,
            confirm_deletions=args.confirm_deletions,
        )
        store.update(
            lambda d: d["last_source_run"].update(
                {
                    "status": "incomplete"
                    if report["skipped"] or report.get("pending_deletions")
                    else "complete",
                    "finished_at": datetime.now(UTC).isoformat(),
                    "report": report,
                }
            )
        )
        if not report["skipped"] and not report.get("pending_deletions") and not args.backfill:
            execute_publish(
                client,
                store,
                PublishPlan(),
                start_page_payload(slug_map, cfg.wiki_name),
                cfg.wiki_slug,
            )
    if args.as_json:
        say(json.dumps(report, ensure_ascii=False))
    else:
        say(
            f"sources: {report['written']} written, {report['archived']} archived, {report['unchanged']} unchanged, {len(report['skipped'])} rejected, {len(report.get('pending_deletions', []))} pending deletions"
        )
    return 1 if report["skipped"] or report.get("pending_deletions") else 0


if __name__ == "__main__":
    raise SystemExit(main())
