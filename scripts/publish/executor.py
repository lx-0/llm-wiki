"""Publish executor (M030-S02-T03) — the plan, executed sequentially.

Error posture: a server-side tool reject (secret gate, cross-wiki conflict,
validation) is PER-ARTICLE fail-soft — skip, WARNING, run continues (mirrors
compile's per-item posture). A transport/auth failure aborts the run; every
article already accepted is persisted in the manifest, so the rerun resumes
where it stopped. The manifest is written only AFTER server success — never
optimistically.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from publish.bootstrap import needs_start_page, record_start_page
from publish.client import ToolCallError
from publish.delta import ArticlePayload, PublishPlan, record_published, record_retracted

from core.state_store import StateStore

log = logging.getLogger(__name__)


@dataclass
class PublishReport:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    retracted: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    start_page_written: bool = False
    unchanged: int = 0


def _write_article(client, wiki_slug: str, payload: ArticlePayload, **extra) -> dict:
    return client.call_tool(
        "write_article",
        {
            "wiki": wiki_slug,
            "name": payload.name,
            "description": payload.description,
            "content": payload.content,
            **extra,
        },
    )


def execute_publish(
    client,
    store: StateStore,
    plan: PublishPlan,
    start_payload: ArticlePayload | None,
    wiki_slug: str,
) -> PublishReport:
    report = PublishReport(unchanged=plan.unchanged)

    if start_payload is not None and needs_start_page(store, start_payload):
        try:
            _write_article(client, wiki_slug, start_payload, start_page=True)
            record_start_page(store, start_payload)
            report.start_page_written = True
        except ToolCallError as exc:
            log.warning("publish: start page rejected: %s", exc)
            report.skipped.append((start_payload.slug, str(exc)))

    for bucket, payloads in (("created", plan.create), ("updated", plan.update)):
        for payload in payloads:
            try:
                _write_article(client, wiki_slug, payload)
            except ToolCallError as exc:
                log.warning("publish: %s rejected: %s", payload.slug, exc)
                report.skipped.append((payload.slug, str(exc)))
                continue
            record_published(store, payload)
            getattr(report, bucket).append(payload.slug)

    for slug, rel in plan.retract:
        try:
            client.call_tool("delete_object", {"object_id": slug})
        except ToolCallError as exc:
            log.warning("publish: retraction of %s (%s) rejected: %s", slug, rel, exc)
            report.skipped.append((slug, str(exc)))
            continue
        record_retracted(store, slug)
        report.retracted.append(slug)

    return report
