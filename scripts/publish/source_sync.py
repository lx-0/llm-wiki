"""Producer v3: per-file durable operation receipts and byte-for-byte read-back."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path
from uuid import uuid4

from core.state_store import StateStore
from publish.client import ToolCallError, tool_text
from publish.delta import PublishPlan, record_retracted
from publish.sources import SourcePlan, SourceWrite, inventory_sources

log = logging.getLogger(__name__)


def require_source_contract(client) -> None:
    tools = {t["name"]: t for t in client.list_tools().get("tools", [])}
    if (
        "move_wiki_files" not in tools
        or "write_wiki_file" not in tools
        or "source"
        not in tools.get("write_article", {}).get("inputSchema", {}).get("properties", {})
    ):
        raise ValueError("server does not support producer v3; upgrade before publishing sources")


def _body(result: dict) -> dict:
    value = json.loads(tool_text(result))
    if not isinstance(value, dict):
        raise ValueError("invalid source receipt")
    return value


def _operation(store: StateStore, key: str, arguments: dict) -> str:
    digest = hashlib.sha256(json.dumps(arguments, sort_keys=True).encode()).hexdigest()
    pending = store.load().get("pending_sources", {}).get(key)
    if pending:
        if pending["digest"] != digest:
            raise ValueError(
                f"pending source changed after an interrupted request: {key}; reconcile before continuing"
            )
        return pending["operation_id"]
    operation = str(uuid4())
    store.update(
        lambda d: d.setdefault("pending_sources", {}).update(
            {key: {"digest": digest, "operation_id": operation}}
        )
    )
    return operation


def _read_back(client, receipt: dict, expected: SourceWrite) -> None:
    if (
        receipt.get("path") != expected.file.path
        or receipt.get("sha256") != expected.file.sha256
        or not isinstance(receipt.get("revision"), int)
    ):
        raise ValueError("source receipt does not match the inventory")
    if expected.file.directory:
        return
    result = client.read_resource(f"wiki-source://file/{receipt['id']}/{receipt['revision']}")
    contents = result.get("contents", [])
    if len(contents) != 1:
        raise ValueError("source read-back missing")
    item = contents[0]
    content = (
        base64.b64decode(item["blob"], validate=True)
        if "blob" in item
        else item["text"].encode("utf-8")
    )
    if hashlib.sha256(content).hexdigest() != expected.file.sha256:
        raise ValueError("source read-back digest mismatch")


def _write(client, store: StateStore, vault: Path, wiki: str, item: SourceWrite, article) -> dict:
    source = {
        "key": item.key,
        "path": item.file.path,
        "expected_revision": item.previous.get("revision"),
    }
    if not item.file.directory:
        data = (vault / item.file.path).read_bytes()
        if hashlib.sha256(data).hexdigest() != item.file.sha256:
            raise ValueError(f"source changed during inventory: {item.file.path}")
        source["content_base64"] = base64.b64encode(data).decode("ascii")
    if article:
        arguments = {
            "wiki": wiki,
            "name": article.name,
            "description": article.description,
            "content": article.content,
            "source": source,
        }
        tool = "write_article"
    else:
        arguments = {"wiki": wiki, **source, "directory": item.file.directory}
        if item.article_id:
            arguments["article_id"] = item.article_id
        tool = "write_wiki_file"
    operation = _operation(store, item.key, {"tool": tool, **arguments})
    if article:
        arguments["source"]["operation_id"] = operation
    else:
        arguments["operation_id"] = operation
    response = _body(client.call_tool(tool, arguments))
    receipt = response["source"] if article else response
    _read_back(client, receipt, item)

    def acknowledge(data: dict) -> None:
        data["source_contract"] = 3
        data["layout"] = "vault-rel"
        data.setdefault("sources", {})[item.key] = {
            "path": item.file.path,
            "sha256": item.file.sha256,
            "directory": item.file.directory,
            "revision": receipt["revision"],
            "id": receipt["id"],
            "article_id": item.article_id,
        }
        data.setdefault("pending_sources", {}).pop(item.key, None)
        if article:
            data.setdefault("articles", {})[article.slug] = {
                "path": article.rel,
                "hash": article.content_hash,
            }
        elif item.article_id in data.get("articles", {}):
            data["articles"][item.article_id]["path"] = item.file.path

    store.update(acknowledge)
    return receipt


def _archive(client, store: StateStore, wiki: str, key: str, entry: dict) -> None:
    arguments = {
        "wiki": wiki,
        "key": key,
        "path": entry["path"],
        "expected_revision": entry["revision"],
        "archived": True,
        "directory": entry.get("directory", False),
    }
    if entry.get("article_id"):
        arguments["article_id"] = entry["article_id"]
    arguments["operation_id"] = _operation(store, key, arguments)
    receipt = _body(client.call_tool("write_wiki_file", arguments))
    if receipt.get("path") != entry["path"] or receipt.get("sha256") != entry.get("sha256"):
        raise ValueError("archive receipt mismatch")
    if entry.get("article_id"):
        client.call_tool("delete_object", {"object_id": entry["article_id"]})

    def acknowledge(data: dict) -> None:
        data["sources"][key] = {**entry, "archived": True, "revision": receipt["revision"]}
        data.setdefault("pending_sources", {}).pop(key, None)
        if entry.get("article_id"):
            data.setdefault("articles", {}).pop(entry["article_id"], None)

    store.update(acknowledge)


def execute_source_publish(
    client,
    store: StateStore,
    vault: Path,
    sources: SourcePlan,
    articles: PublishPlan,
    wiki: str,
    *,
    confirm_deletions: bool = False,
) -> dict:
    from publish.source_moves import apply_source_moves

    sources = apply_source_moves(client, store, wiki, sources)
    changed = {p.slug: p for p in articles.create + articles.update}
    report = {"written": 0, "archived": 0, "unchanged": sources.unchanged, "skipped": []}
    for item in sources.write:
        try:
            if not (
                item.previous.get("path") == item.file.path
                and not item.previous.get("archived")
                and item.previous.get("sha256") == item.file.sha256
                and item.article_id not in changed
            ):
                _write(client, store, vault, wiki, item, changed.get(item.article_id))
            report["written"] += 1
        except ToolCallError as exc:
            log.warning("publish: source %s rejected: %s", item.file.path, exc)
            report["skipped"].append({"path": item.file.path, "reason": str(exc)})
            store.update(lambda d, key=item.key: d.setdefault("pending_sources", {}).pop(key, None))
    # Do not retract anything while a source was rejected. Never turn a partial run into deletion.
    if report["skipped"]:
        return report
    if (
        not confirm_deletions
        and (sources.archive or articles.retract)
        and (any(not i.previous for i in sources.write) or store.load().get("pending_deletions"))
    ):
        report["pending_deletions"] = [e["path"] for _, e in sources.archive] + [
            rel for _, rel in articles.retract
        ]
        store.update(lambda d: d.update({"pending_deletions": report["pending_deletions"]}))
        log.warning(
            "publish: unresolved additions/deletions; reconcile moves or use --confirm-deletions after reviewing the dry run"
        )
        return report
    if (sources.archive or articles.retract) and inventory_sources(
        vault, sources.roots
    ) != sources.inventory:
        raise ValueError("source inventory changed during publication; retractions cancelled")
    for key, entry in sources.archive:
        _archive(client, store, wiki, key, entry)
        report["archived"] += 1
    archived_articles = {e.get("article_id") for _, e in sources.archive}
    for slug, _ in articles.retract:
        if slug not in archived_articles:
            client.call_tool("delete_object", {"object_id": slug})
            record_retracted(store, slug)

    def finish(data: dict) -> None:
        data.pop("pending_deletions", None)
        if sources.move_batch:
            data.setdefault("move_batches", {})[sources.move_batch] = True

    store.update(finish)
    return report
