"""The lint corpus model: the `Issue` type and the `LintContext` every check runs over.

C04 (link-graph + corpus model seam): the context is the single corpus read of a lint
run — canonical article enumeration (`core.utils.list_wiki_articles`, includes
`knowledge/MOCs/`), parsed frontmatter (`core.frontmatter`), stripped bodies,
footer-aware outgoing slugs (`core.links.outgoing_canonical_slugs` — the engine-written
`## Backlinks` footers are NOT link edges), and the derived inbound map (the one-O(N)-pass
rule from the 2026-05-30 incident lives in the builder). The checks live in
`lint_checks` (structural) and `lint_schema` (frontmatter schema); `lint` runs them.
"""

from dataclasses import dataclass
from pathlib import Path

from core import frontmatter
from core.backlinks import BACKLINKS_BEGIN, BACKLINKS_END
from core.links import canonical_slug, outgoing_canonical_slugs
from core.paths import KNOWLEDGE_DIR, ROOT_DIR
from core.utils import list_raw_files, list_wiki_articles, load_state

# ── Issue type ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Issue:
    """One lint finding. `fact_slug` / `target_slug` are the structured
    payload consumers key on (reconcile groups by fact, dashboards link the
    target) — the `detail` prose is display-only, never parsed."""

    severity: str  # error, warning, suggestion
    check: str
    file: str
    detail: str
    auto_fixable: bool = False
    fact_slug: str | None = None
    target_slug: str | None = None


def issue(
    severity: str,
    check: str,
    file: str,
    detail: str,
    auto_fixable: bool = False,
    *,
    fact_slug: str | None = None,
    target_slug: str | None = None,
) -> Issue:
    """Create a structured Issue (factory keeps the historic call shape)."""
    return Issue(
        severity=severity,
        check=check,
        file=file,
        detail=detail,
        auto_fixable=auto_fixable,
        fact_slug=fact_slug,
        target_slug=target_slug,
    )


# ── Corpus model ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Article:
    """One knowledge article, read + parsed exactly once per lint run."""

    path: Path
    rel: str  # posix path relative to knowledge_dir, e.g. "concepts/foo.md"
    text: str  # full file content
    fm: dict  # tolerant frontmatter (core.frontmatter grammar)
    body: str  # frontmatter-stripped body
    slug: str | None  # canonical knowledge slug, e.g. "concepts/foo"
    outgoing: frozenset[str]  # footer-aware outgoing canonical slugs


@dataclass(frozen=True)
class LintContext:
    """The corpus model every check runs over — built ONCE per run.

    `inbound` maps target slug → source slugs and is derived from the
    footer-aware `outgoing` sets, so the engine-materialized `## Backlinks`
    footers (M020) never count as link edges. This builder IS the one-O(N)-pass
    inbound computation (2026-05-30 decision); a per-article corpus rescan can
    only be reintroduced here, nowhere else.
    """

    vault: Path
    knowledge_dir: Path
    articles: tuple[Article, ...]
    index_content: str
    inbound: dict[str, set[str]]
    state: dict
    raw_files: tuple[Path, ...]


def build_context(
    *,
    vault: Path | None = None,
    knowledge_dir: Path | None = None,
    state: dict | None = None,
    raw_files: list[Path] | None = None,
) -> LintContext:
    """Build the LintContext: the single corpus read of a lint run.

    Defaults target the live vault; tests pass a temp ``vault`` /
    ``knowledge_dir`` (+ ``state={}``) to lint an in-memory corpus without
    monkeypatching module globals.
    """
    vault = vault if vault is not None else ROOT_DIR
    kdir = knowledge_dir if knowledge_dir is not None else KNOWLEDGE_DIR

    articles: list[Article] = []
    for path in list_wiki_articles(kdir):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm, body = frontmatter.parse(text)
        articles.append(
            Article(
                path=path,
                rel=path.relative_to(kdir).as_posix(),
                text=text,
                fm=fm,
                body=body,
                slug=canonical_slug(path, kdir),
                outgoing=frozenset(
                    outgoing_canonical_slugs(
                        text, path, vault, kdir, BACKLINKS_BEGIN, BACKLINKS_END
                    )
                ),
            )
        )

    inbound: dict[str, set[str]] = {}
    for art in articles:
        if art.slug is None:
            continue
        for tgt in art.outgoing:
            if tgt == art.slug:
                continue  # self-links are not inbound edges
            inbound.setdefault(tgt, set()).add(art.slug)

    index_file = kdir / "index.md"
    try:
        index_content = index_file.read_text(encoding="utf-8") if index_file.exists() else ""
    except OSError:
        index_content = ""

    if state is None:
        state = load_state()
    if raw_files is None:
        raw_files = list_raw_files(daily_dir=vault / "daily", raw_dir=vault / "raw")

    return LintContext(
        vault=vault,
        knowledge_dir=kdir,
        articles=tuple(articles),
        index_content=index_content,
        inbound=inbound,
        state=state,
        raw_files=tuple(raw_files),
    )


def _in_folder(ctx: LintContext, folder: str) -> list[Article]:
    """Articles under ``knowledge/<folder>/``, index.md/log.md filtered."""
    prefix = f"{folder}/"
    return [
        a
        for a in ctx.articles
        if a.rel.startswith(prefix) and a.path.name not in ("index.md", "log.md")
    ]


def _read_frontmatter(path: Path) -> dict:
    """Frontmatter dict via the single core.frontmatter grammar (C03) —
    returns {} on unreadable file / no fence / malformed YAML. Values carry
    YAML types (lists, bools). Used for files OUTSIDE the knowledge corpus
    (raw/, daily/, inbox/ walks); knowledge articles carry their parsed
    frontmatter on `Article.fm`."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return frontmatter.parse(text)[0]
