"""Original source inventory and restartable v3 publishing."""

import base64
import hashlib
import json
from pathlib import Path

import pytest

from publish.corpus import manifest_store
from publish.delta import PublishPlan
from publish.source_sync import execute_source_publish, require_source_contract
from publish.sources import inventory_sources, source_plan


def test_inventory_preserves_all_files_and_empty_directories(tmp_path: Path):
    (tmp_path / "knowledge/nested").mkdir(parents=True)
    (tmp_path / "knowledge/empty").mkdir()
    (tmp_path / "knowledge/index.md").write_bytes(b"index\r\n")
    (tmp_path / "knowledge/nested/image.bin").write_bytes(b"\x00\xff")
    rows = inventory_sources(tmp_path, ("knowledge",))
    assert {r.path for r in rows} == {
        "knowledge/index.md",
        "knowledge/nested/image.bin",
        "knowledge/empty",
    }
    assert sum(r.size for r in rows) == 9
    assert next(r for r in rows if r.directory).sha256 is None


def test_missing_root_or_symlink_prevents_retraction_plan(tmp_path: Path):
    with pytest.raises(ValueError, match="missing"):
        inventory_sources(tmp_path, ("knowledge",))
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge/outside").symlink_to(tmp_path.parent)
    with pytest.raises(ValueError, match="symlink"):
        inventory_sources(tmp_path, ("knowledge",))


def test_backfill_keeps_article_key_and_explicit_moves_keep_identity(tmp_path: Path):
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge/new.md").write_bytes(b"original")
    store = manifest_store(tmp_path / "state.json")
    store.update(
        lambda d: d.update(
            {
                "layout": "vault-rel",
                "articles": {"stable-slug": {"path": "knowledge/old.md", "hash": "projection"}},
                "sources": {
                    "stable-key": {
                        "path": "knowledge/old.md",
                        "sha256": "old",
                        "revision": 4,
                        "article_id": "stable-slug",
                    }
                },
            }
        )
    )
    plan = source_plan(
        inventory_sources(tmp_path, ("knowledge",)),
        store.load(),
        {"stable-slug": "knowledge/new.md"},
        {"knowledge/old.md": "knowledge/new.md"},
    )
    assert len(plan.write) == 1 and not plan.archive
    assert plan.write[0].key == "stable-key"
    assert plan.write[0].previous["revision"] == 4
    assert plan.write[0].article_id == "stable-slug"


class SourceServer:
    def __init__(self):
        self.rows = {}
        self.calls = []
        self.fail_after_commit = False

    def list_tools(self):
        return {
            "tools": [
                {"name": "write_wiki_file"},
                {"name": "move_wiki_files"},
                {"name": "write_article", "inputSchema": {"properties": {"source": {}}}},
            ]
        }

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "get_wiki":
            value = {"producer_contract": 3, "files": list(self.rows.values()), "pages": 1}
        else:
            source = arguments.get("source", arguments)
            content = base64.b64decode(source.get("content_base64", ""))
            key = source["key"]
            old = self.rows.get(key, {})
            if old.get("operation_id") == source["operation_id"]:
                value = old
            else:
                value = {
                    "key": key,
                    "id": key,
                    "revision": (source["expected_revision"] or 0) + 1,
                    "path": source["path"],
                    "sha256": None
                    if arguments.get("directory")
                    else hashlib.sha256(content).hexdigest(),
                    "content": content,
                    "operation_id": source["operation_id"],
                }
                self.rows[key] = value
            if self.fail_after_commit:
                self.fail_after_commit = False
                raise ConnectionError("lost response")
            if name == "write_article":
                value = {"source": value}
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {k: v for k, v in value.items() if k != "content"},
                        default=lambda b: "bytes",
                    ),
                }
            ]
        }

    def read_resource(self, uri):
        row = next(r for r in self.rows.values() if f"/{r['id']}/" in uri)
        return {"contents": [{"blob": base64.b64encode(row["content"]).decode()}]}


def test_sync_backfills_original_and_replays_lost_receipt(tmp_path: Path):
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge/file.bin").write_bytes(b"\x00\xff")
    store = manifest_store(tmp_path / "state.json")
    plan = source_plan(inventory_sources(tmp_path, ("knowledge",)), store.load(), {})
    server = SourceServer()
    server.fail_after_commit = True
    with pytest.raises(ConnectionError):
        execute_source_publish(server, store, tmp_path, plan, PublishPlan(), "wiki")
    assert not store.reload().get("sources")
    report = execute_source_publish(server, store, tmp_path, plan, PublishPlan(), "wiki")
    assert report["written"] == 1
    writes = [a for n, a in server.calls if n == "write_wiki_file"]
    assert writes[0]["operation_id"] == writes[1]["operation_id"]
    assert next(iter(store.reload()["sources"].values()))["revision"] == 1
    again = source_plan(inventory_sources(tmp_path, ("knowledge",)), store.load(), {})
    assert again.unchanged == 1 and not again.write


def test_old_server_is_rejected_before_any_write():
    class OldServer(SourceServer):
        def list_tools(self):
            return {"tools": [{"name": "write_article"}]}

    server = OldServer()
    with pytest.raises(ValueError, match="v3"):
        require_source_contract(server)
    assert server.calls == []


def test_explicit_path_swap_preserves_keys_and_repeated_move_is_not_reversed(tmp_path: Path):
    from publish.sources import effective_moves, validate_moves

    (tmp_path / "raw").mkdir()
    (tmp_path / "raw/a").write_bytes(b"B")
    (tmp_path / "raw/b").write_bytes(b"A")
    state = {
        "sources": {
            "a": {"path": "raw/a", "sha256": hashlib.sha256(b"A").hexdigest(), "revision": 1},
            "b": {"path": "raw/b", "sha256": hashlib.sha256(b"B").hexdigest(), "revision": 1},
        }
    }
    moves = {"raw/a": "raw/b", "raw/b": "raw/a"}
    files = inventory_sources(tmp_path, ("raw",))
    validate_moves(files, state, moves)
    plan = source_plan(files, state, {}, moves)
    assert [(i.key, i.file.path) for i in plan.write] == [("b", "raw/a"), ("a", "raw/b")]
    state["move_batches"] = {plan.move_batch: True}
    assert effective_moves(state, moves) == {}


def test_unresolved_deletions_stay_pending_on_the_next_run(tmp_path: Path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw/new.bin").write_bytes(b"new")
    store = manifest_store(tmp_path / "state.json")
    store.update(
        lambda d: d.update(
            {
                "sources": {
                    "old": {
                        "path": "raw/old.bin",
                        "sha256": "old",
                        "revision": 1,
                    }
                }
            }
        )
    )
    server = SourceServer()
    for _ in range(2):
        plan = source_plan(inventory_sources(tmp_path, ("raw",)), store.load(), {})
        result = execute_source_publish(server, store, tmp_path, plan, PublishPlan(), "wiki")
        assert result["pending_deletions"] == ["raw/old.bin"]
        assert not any(a.get("archived") for _, a in server.calls)


def test_move_receipt_loss_retries_atomic_batch_without_reversing_identity(tmp_path: Path):
    class MoveServer(SourceServer):
        def __init__(self):
            super().__init__()
            self.operations = {}
            self.fail_move = True

        def call_tool(self, name, arguments):
            if name != "move_wiki_files":
                return super().call_tool(name, arguments)
            self.calls.append((name, arguments))
            receipts = []
            for move in arguments["moves"]:
                op = move["operation_id"]
                if op not in self.operations:
                    row = self.rows[move["key"]]
                    assert row["revision"] == move["expected_revision"]
                    row.update(path=move["path"], revision=row["revision"] + 1)
                    self.operations[op] = {k: v for k, v in row.items() if k != "content"}
                receipts.append(self.operations[op])
            if self.fail_move:
                self.fail_move = False
                raise ConnectionError("lost move receipt")
            return {"content": [{"type": "text", "text": json.dumps({"files": receipts})}]}

    (tmp_path / "raw").mkdir()
    for name in ("a", "b"):
        (tmp_path / "raw" / name).write_bytes(name.encode())
    store = manifest_store(tmp_path / "state.json")
    server = MoveServer()
    plan = source_plan(inventory_sources(tmp_path, ("raw",)), store.load(), {})
    execute_source_publish(server, store, tmp_path, plan, PublishPlan(), "wiki")
    for name, body in (("a", b"b"), ("b", b"a")):
        (tmp_path / "raw" / name).write_bytes(body)
    moves = {"raw/a": "raw/b", "raw/b": "raw/a"}
    plan = source_plan(inventory_sources(tmp_path, ("raw",)), store.load(), {}, moves)
    with pytest.raises(ConnectionError):
        execute_source_publish(server, store, tmp_path, plan, PublishPlan(), "wiki")
    assert all(e["revision"] == 1 for e in store.reload()["sources"].values())
    execute_source_publish(server, store, tmp_path, plan, PublishPlan(), "wiki")
    assert all(e["revision"] == 2 for e in store.reload()["sources"].values())
    assert not store.load()["pending_sources"]
    assert len([n for n, _ in server.calls if n == "write_wiki_file"]) == 2


def test_failed_readback_does_not_acknowledge_manifest(tmp_path: Path):
    class CorruptServer(SourceServer):
        def read_resource(self, uri):
            return {"contents": [{"text": "wrong bytes"}]}

    (tmp_path / "raw").mkdir()
    (tmp_path / "raw/a").write_bytes(b"a")
    store = manifest_store(tmp_path / "state.json")
    plan = source_plan(inventory_sources(tmp_path, ("raw",)), store.load(), {})
    with pytest.raises(ValueError, match="digest mismatch"):
        execute_source_publish(CorruptServer(), store, tmp_path, plan, PublishPlan(), "wiki")
    assert not store.reload().get("sources")
    assert store.load()["pending_sources"]
