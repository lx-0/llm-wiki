"""Producer-lifecycle integration test (M030-S02-T04).

Mirrors context-mcp's REFERENCE PRODUCER RUN (wiki-tools.test.ts:266):
managed wiki -> publish -> update -> retract -> re-publish. Drives the REAL
ContextMcpClient + bootstrap + executor against a stateful in-process fake
speaking the observed wire shape — including the server-side re-slugification
(slugifySkillName), so the S01 fixpoint property is asserted end-to-end.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx

from publish.bootstrap import ensure_wiki, start_page_payload
from publish.client import ContextMcpClient
from publish.cli import build_publish_plan
from publish.corpus import manifest_store, server_slug
from publish.executor import execute_publish


class FakeContextMcp:
    """Stateful stand-in for context-mcp's wiki surface."""

    def __init__(self) -> None:
        self.wikis: dict[str, dict] = {}
        self.articles: dict[str, dict] = {}
        self.write_calls = 0

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    # ── wire ────────────────────────────────────────────────────────────

    def _handle(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode()) if request.content else {}
        method = payload.get("method")
        if method == "initialize":
            return self._rpc(payload, {
                "protocolVersion": "2025-06-18",
                "serverInfo": {"name": "context-mcp", "version": "0.0.56"},
                "capabilities": {},
            })
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/call":
            name = payload["params"]["name"]
            args = payload["params"].get("arguments", {})
            return self._rpc(payload, self._tool(name, args))
        raise AssertionError(f"unexpected method {method}")

    @staticmethod
    def _rpc(payload: dict, result: dict) -> httpx.Response:
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": payload.get("id"), "result": result,
        })

    @staticmethod
    def _json_result(value: dict) -> dict:
        return {"content": [{"type": "text",
                             "text": json.dumps(value, indent=2)}],
                "isError": False}

    @staticmethod
    def _error(text: str) -> dict:
        return {"content": [{"type": "text", "text": text}], "isError": True}

    # ── tools (semantics per wiki-tools.ts) ─────────────────────────────

    def _tool(self, name: str, args: dict) -> dict:
        if name == "list_wikis":
            return self._json_result({"wikis": list(self.wikis.values())})
        if name == "create_wiki":
            slug = server_slug(args.get("slug") or args["name"])
            if slug in self.wikis:
                return self._error(f'a wiki with slug "{slug}" already exists')
            self.wikis[slug] = {"slug": slug, "name": args["name"],
                                "managed_by": args.get("managed_by")}
            return self._json_result({"wiki": self.wikis[slug]})
        if name == "write_article":
            return self._write_article(args)
        if name == "delete_object":
            entry = self.articles.get(args["object_id"])
            if entry is None:
                return self._error(f'unknown object "{args["object_id"]}"')
            entry["archived"] = True
            return self._json_result({"archived": args["object_id"]})
        raise AssertionError(f"unexpected tool {name}")

    def _write_article(self, args: dict) -> dict:
        self.write_calls += 1
        if args["wiki"] not in self.wikis:
            return self._error(f'unknown wiki "{args["wiki"]}"')
        # THE server behavior the producer must be a fixpoint of:
        slug = server_slug(args["name"])
        if not slug:
            return self._error("`name` must slugify to a usable flat article id")
        if not args.get("description", "").strip():
            return self._error("`description` must not be empty")
        entry = self.articles.get(slug)
        created = entry is None
        if created:
            entry = {"wiki": args["wiki"], "seq": 0, "archived": False}
            self.articles[slug] = entry
        if entry["wiki"] != args["wiki"]:
            return self._error(
                f'article "{slug}" belongs to wiki "{entry["wiki"]}"')
        if entry["archived"]:
            entry["archived"] = False  # restore-on-write (contract §5)
        entry["seq"] += 1
        entry["content"] = args["content"]
        return self._json_result({
            "article_id": slug, "wiki": args["wiki"],
            "version_seq": entry["seq"], "created": created,
            **({"start_page": True} if args.get("start_page") else {}),
        })


def _vault(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    k = vault / "knowledge"
    for rel, body in {
        "concepts/foo.md": "Foo body linking [[../people/alex|Alex]].\n",
        "people/alex.md": "Alex body.\n",
        "concepts/alex.md": "Concept alex body.\n",
        "MOCs/hub.md": "Hub.\n",
    }.items():
        p = k / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    (k / "index.md").write_text(
        "| Article | Summary | Compiled From | Updated |\n"
        "|---------|---------|---------------|---------|\n"
        "| [[concepts/foo]] | About foo. | raw/a.md | 2026-08-01 |\n",
        encoding="utf-8",
    )
    return vault, k


def _run_publish(server: FakeContextMcp, store, k: Path, vault: Path):
    client = ContextMcpClient("https://fake.test/mcp", "tok",
                              transport=server.transport())
    ensure_wiki(client, "llm-wiki", "LLM Wiki")
    plan, slug_map = build_publish_plan(k, vault, store)
    start = start_page_payload(slug_map, "LLM Wiki")
    return execute_publish(client, store, plan, start, "llm-wiki")


def test_reference_producer_run_lifecycle(tmp_path: Path) -> None:
    server = FakeContextMcp()
    store = manifest_store(tmp_path / "publish.json")
    vault, k = _vault(tmp_path)

    # 1) managed wiki + first publish: everything created at seq 1
    report = _run_publish(server, store, k, vault)
    assert server.wikis["llm-wiki"]["managed_by"] == "llm-wiki"
    assert sorted(report.created) == ["concepts-alex", "foo", "hub", "people-alex"]
    assert report.start_page_written is True
    assert server.articles["foo"]["seq"] == 1
    assert "[[people-alex|Alex]]" in server.articles["foo"]["content"]
    assert server.articles["start"]["seq"] == 1

    # 2) update: body edit publishes seq 2 for exactly that article
    (k / "concepts" / "foo.md").write_text("Foo body v2.\n", encoding="utf-8")
    report = _run_publish(server, store, k, vault)
    assert report.updated == ["foo"] and not report.created
    assert server.articles["foo"]["seq"] == 2

    # 3) retract: local delete archives upstream, manifest entry gone
    (k / "concepts" / "foo.md").unlink()
    report = _run_publish(server, store, k, vault)
    assert report.retracted == ["foo"]
    assert server.articles["foo"]["archived"] is True
    assert "foo" not in store.reload()["articles"]

    # 4) re-publish restores: same slug comes back, next version (seq 3 —
    #    mirroring the upstream run's version_seq: 3)
    (k / "concepts" / "foo.md").write_text("Foo body v3.\n", encoding="utf-8")
    report = _run_publish(server, store, k, vault)
    assert report.created == ["foo"]  # new manifest entry; server restored
    assert server.articles["foo"]["archived"] is False
    assert server.articles["foo"]["seq"] == 3

    # 5) unchanged rerun: zero write calls
    before = server.write_calls
    report = _run_publish(server, store, k, vault)
    assert not report.created and not report.updated and not report.retracted
    assert server.write_calls == before
