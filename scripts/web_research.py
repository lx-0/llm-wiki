"""Dream web-research — public-entity enrichment via Exa AI (issue #2).

A dream POST-PASS (not a compile producer — see the placement note in
`.ytstack/backlog/dream-web-research.md`): after `wiki dream <slug>`
re-synthesizes a `type: person` page, this researches PUBLIC individuals
(founders, execs, speakers) on the open web and writes a sentinel-managed
`## Public Profile` block into the page.

Hard guarantees:
- **Doubly gated.** `features.dream_web_research` (vault flag, default off) AND
  a per-entity opt-in (`web_research: true` frontmatter OR the `public-person`
  tag). Never fires on every page.
- **Air-gapped from `raw/`.** The block is written ONLY into the entity page
  under `knowledge/` — never echoed into `raw/`. Feeding web text into `raw/`
  would let the compiler re-synthesize it as operator-authored substrate
  (compile-loop contamination). `run_web_research` refuses any target outside
  `knowledge/`.
- **Own cooldown.** `scheduling.web_research_cooldown_days` (default 30) — the
  block stamps its own `last updated:` date; a fresh stamp short-circuits.
- **Provider-isolated.** Exa is its own lane; it does NOT fall back to
  Ollama/Claude, and the dream cycle does NOT fall back to it.

The Exa HTTP call uses the authoritative shape from the `exa-search-api` skill
(`POST https://api.exa.ai/search`, `x-api-key` header). v1 writes a
deterministic link-list block (title · url · snippet); LLM distillation into
the richer `Company / LinkedIn / Known for` shape is a documented Phase-2
deferral (see the backlog).
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Literal

import yaml

from core import markers

log = logging.getLogger("web_research")

SENTINEL_BEGIN = "<!-- web-research:begin -->"
SENTINEL_END = "<!-- web-research:end -->"
PUBLIC_PERSON_TAG = "public-person"
EXA_ENDPOINT = "https://api.exa.ai/search"

_LAST_UPDATED_RE = re.compile(r"last updated:\s*(\d{4}-\d{2}-\d{2})")

# Backend signature: (query, api_key, num_results) -> list of result dicts,
# each {"title": str, "url": str, "text": str}. Injectable for tests.
Backend = Callable[[str, str, int], list[dict]]

ResearchStatus = Literal["ok", "skipped", "failed"]


@dataclass(frozen=True)
class WebResearchResult:
    status: ResearchStatus
    reason: str | None = None
    block: str | None = None
    wrote: bool = False


# ── Frontmatter + opt-in ─────────────────────────────────────────────


def split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    try:
        fm = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, text[end + 5 :]


def is_opted_in(fm: dict) -> bool:
    """A page opts in via `web_research: true` OR the `public-person` tag."""
    if fm.get("web_research") is True:
        return True
    tags = fm.get("tags")
    if isinstance(tags, str):
        tags = [tags]
    if isinstance(tags, list) and PUBLIC_PERSON_TAG in tags:
        return True
    return False


def _entity_title(fm: dict, slug: str) -> str:
    return (fm.get("title") or fm.get("name") or "").strip() or slug.replace("-", " ").title()


# ── Cooldown ─────────────────────────────────────────────────────────


def _block_last_updated(text: str) -> date | None:
    """The `last updated: YYYY-MM-DD` date inside an existing Public Profile
    block, or None if there is no block / no parseable stamp. Region location
    (incl. the stray/reversed-marker contract) is `core.markers`."""
    region = markers.find_region(text, SENTINEL_BEGIN, SENTINEL_END)
    if region is None:
        return None
    m = _LAST_UPDATED_RE.search(text[region.start : region.end])
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def cooldown_active(text: str, *, cooldown_days: int, now: date) -> bool:
    last = _block_last_updated(text)
    if last is None:
        return False
    return now < last + timedelta(days=cooldown_days)


# ── Block rendering ──────────────────────────────────────────────────


def build_block(entity_name: str, results: list[dict], *, today: date, source: str = "exa") -> str:
    """Render the sentinel-managed `## Public Profile` block. Deterministic —
    one bullet per result (title linked to url + a trimmed snippet)."""
    lines = [
        SENTINEL_BEGIN,
        "## Public Profile",
        f"_auto-researched · last updated: {today.isoformat()} · source: {source}_",
        "",
    ]
    if results:
        for r in results:
            title = (r.get("title") or r.get("url") or "untitled").strip()
            url = (r.get("url") or "").strip()
            snippet = " ".join((r.get("text") or "").split())[:220]
            head = f"- **[{title}]({url})**" if url else f"- **{title}**"
            lines.append(f"{head} — {snippet}" if snippet else head)
    else:
        lines.append("_No public sources found._")
    lines += [
        "",
        "_This section is auto-generated from public sources and may not reflect current state._",
        SENTINEL_END,
    ]
    return "\n".join(lines)


def upsert_block(text: str, block: str) -> str:
    """Replace an existing sentinel block in place, else append it. Idempotent
    on structure (re-running swaps the block, never stacks duplicates). Region
    location (incl. the stray/reversed-marker contract) is `core.markers`; the
    append seam (exactly one blank line + trailing newline) stays ours."""

    def _append(t: str, blk: str) -> str:
        sep = "" if t.endswith("\n\n") else ("\n" if t.endswith("\n") else "\n\n")
        return t + sep + blk + "\n"

    return markers.ensure_region(text, SENTINEL_BEGIN, SENTINEL_END, block, insert=_append)


# ── Exa backend (live-unverified: no key available at build time) ────


def search_exa(query: str, api_key: str, num_results: int = 5) -> list[dict]:
    """POST to the Exa search API and return [{title,url,text}, …].

    Shape per the `exa-search-api` skill (authoritative): `POST
    https://api.exa.ai/search`, header `x-api-key`, body with `contents.text`
    so each result carries a snippet. NB: this live HTTP path is structurally
    correct per the skill but UNVERIFIED against the live API (no Exa key was
    available when it was written) — see the backlog. All unit tests inject a
    fake backend; this function is only exercised against the real endpoint."""
    payload = json.dumps({
        "query": query,
        "num_results": num_results,
        "type": "auto",
        "use_autoprompt": True,
        "contents": {"text": {"max_characters": 1000}},
    }).encode("utf-8")
    req = urllib.request.Request(
        EXA_ENDPOINT,
        data=payload,
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out: list[dict] = []
    for r in data.get("results", []):
        out.append({
            "title": r.get("title") or "",
            "url": r.get("url") or "",
            "text": r.get("text") or "",
        })
    return out


# ── Orchestrator ─────────────────────────────────────────────────────


def _resolve_api_key(config) -> str:
    try:
        key = (config.personal.exa_api_key or "").strip()
    except AttributeError:
        key = ""
    return key or os.environ.get("EXA_API_KEY", "").strip()


def run_web_research(
    page: Path,
    *,
    config,
    knowledge_dir: Path,
    now: date | None = None,
    dry_run: bool = False,
    force: bool = False,
    backend: Backend | None = None,
) -> WebResearchResult:
    """Research one entity page + upsert its `## Public Profile` block.

    Gates (skipped, not failed): feature flag, per-entity opt-in, cooldown,
    API key. `force=True` bypasses the feature flag + opt-in + cooldown (the
    standalone `wiki dream web-research <slug>` path) but still needs a key.
    Fail-soft: a backend error returns a `failed` result, never raises — the
    dream flow must not break on a web hiccup."""
    today = now or datetime.now(timezone.utc).date()

    # Air-gap guard: refuse any target outside knowledge/. The block must never
    # land in raw/ (compile-loop contamination).
    try:
        page.resolve().relative_to(knowledge_dir.resolve())
    except ValueError:
        return WebResearchResult("skipped", reason="outside_knowledge")

    enabled = getattr(getattr(config, "features", None), "dream_web_research", False)
    if not enabled and not force:
        return WebResearchResult("skipped", reason="feature_disabled")

    if not page.exists():
        return WebResearchResult("skipped", reason="no_page")
    text = page.read_text(encoding="utf-8")
    fm, _ = split_frontmatter(text)

    if not force and not is_opted_in(fm):
        return WebResearchResult("skipped", reason="not_opted_in")

    cooldown_days = getattr(getattr(config, "scheduling", None), "web_research_cooldown_days", 30)
    if not force and cooldown_active(text, cooldown_days=cooldown_days, now=today):
        return WebResearchResult("skipped", reason="cooldown")

    api_key = _resolve_api_key(config)
    if not api_key:
        return WebResearchResult("skipped", reason="no_api_key")

    name = _entity_title(fm, page.stem)
    call = backend or search_exa
    try:
        results = call(name, api_key, 5)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        log.warning("web-research backend failed for %s: %s", page.stem, exc)
        return WebResearchResult("failed", reason=f"{type(exc).__name__}: {exc}")

    block = build_block(name, results, today=today)
    new_text = upsert_block(text, block)

    if dry_run:
        return WebResearchResult("ok", reason="dry_run", block=block, wrote=False)
    page.write_text(new_text, encoding="utf-8")
    return WebResearchResult("ok", block=block, wrote=True)
