"""Atomic move batches; the manifest follows only verified remote receipts."""

from dataclasses import replace
from uuid import UUID, uuid5

from publish.sources import SourcePlan


def apply_source_moves(client, store, wiki: str, plan: SourcePlan) -> SourcePlan:
    from publish.source_sync import _body, _operation, _read_back

    moving = [i for i in plan.write if i.previous and i.previous["path"] != i.file.path]
    if not moving:
        return plan
    if not plan.move_batch:
        raise ValueError("source move requires an explicit reconciliation batch")
    arguments = {
        "wiki": wiki,
        "moves": [
            {"key": i.key, "path": i.file.path, "expected_revision": i.previous["revision"]}
            for i in moving
        ],
    }
    pending_key = f"moves-{plan.move_batch}"
    operation = _operation(store, pending_key, arguments)
    for move in arguments["moves"]:
        move["operation_id"] = str(uuid5(UUID(operation), move["key"]))
    receipts = _body(client.call_tool("move_wiki_files", arguments)).get("files", [])
    if len(receipts) != len(moving):
        raise ValueError("move receipt count mismatch")
    updated = {}
    for item, receipt in zip(moving, receipts, strict=True):
        previous_file = replace(item.file, sha256=item.previous.get("sha256"))
        _read_back(client, receipt, replace(item, file=previous_file))
        updated[item.key] = {
            **item.previous,
            "path": item.file.path,
            "revision": receipt["revision"],
        }

    def acknowledge(data: dict) -> None:
        data.setdefault("sources", {}).update(updated)
        for item in moving:
            if item.article_id in data.get("articles", {}):
                data["articles"][item.article_id]["path"] = item.file.path
        data.setdefault("move_batches", {})[plan.move_batch] = True
        data.setdefault("pending_sources", {}).pop(pending_key, None)

    store.update(acknowledge)
    return replace(
        plan, write=[replace(i, previous=updated.get(i.key, i.previous)) for i in plan.write]
    )
