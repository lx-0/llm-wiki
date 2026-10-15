"""The frontmatter-schema lint checks: the takes substrate's shape (M011) and the
enum / required-field contracts — `domain:` (M013), `compile_role:` and the `author:`
a source-and-final page must carry (M007).

Every check is a pure function ``check(ctx) -> list[Issue]`` over the `LintContext`
(`lint_model`); `lint.CHECKS` runs them in report order.
"""

import re

from core.compile_role import VALID_ROLES as _COMPILE_ROLE_VALID
from core.config import CONFIG
from lint_model import Issue, LintContext, _in_folder, _read_frontmatter, issue

# ── Takes substrate (M011) ──────────────────────────────────────────

_TAKE_LINE_RE = re.compile(r"^- \*\*\d{4}-\d{2}-\d{2}\*\* \[(?:low|medium|high)\] · `[^`]+` — .+$")


def check_takes_consistency(ctx: LintContext) -> list[Issue]:
    """Validate `knowledge/takes/*.md` shape (M011, v1 — shape-only).

    Per-file checks:
      - Frontmatter `type: takes` is present.
      - Frontmatter `holder:` is present (non-empty).
      - Every body line that starts with `- **` matches the canonical
        take regex; malformed lines surface as warnings.
    """
    issues: list[Issue] = []
    for art in _in_folder(ctx, "takes"):
        if art.fm.get("type") != "takes":
            issues.append(
                issue(
                    "error",
                    "takes_frontmatter_type",
                    art.rel,
                    "Takes file must carry `type: takes` in frontmatter.",
                )
            )
        holder = art.fm.get("holder")
        if not holder or not str(holder).strip():
            issues.append(
                issue(
                    "error",
                    "takes_frontmatter_holder_missing",
                    art.rel,
                    "Takes file must carry a non-empty `holder:` field in frontmatter.",
                )
            )
        for lineno, line in enumerate(art.body.splitlines(), start=1):
            if not line.startswith("- **"):
                continue
            if not _TAKE_LINE_RE.match(line):
                issues.append(
                    issue(
                        "warning",
                        "takes_line_malformed",
                        art.rel,
                        f"Line {lineno} does not match canonical take shape: {line[:120]}",
                    )
                )
    return issues


# ── compile_role enum validation (M007-S01-T03) ─────────────────────


def check_domain_value(ctx: LintContext) -> list[Issue]:
    """Warn on `domain:` frontmatter values outside CONFIG.personal.domains.

    Optional axis (M013). When `domain:` is set on a knowledge/ article, it
    MUST be one of the configured values (default `["company", "personal",
    "ai", "meta"]`, extensible per vault). Articles without `domain:` are
    silently ignored — the feature is opt-in. WARNING (not error): the
    operator gets a grace period to fix typos / introduce new domains via
    config before drift becomes a hard fail. Empty `personal.domains` list
    disables the check entirely (operator opted out).

    Spec: `.ytstack/backlog/domain-frontmatter.md`.
    """
    issues: list[Issue] = []
    domains_cfg = getattr(CONFIG.personal, "domains", None) or []
    valid = {d for d in domains_cfg if isinstance(d, str)}
    if not valid:
        return issues
    for art in ctx.articles:
        value = art.fm.get("domain")
        if value is None:
            continue
        if not isinstance(value, str) or value not in valid:
            allowed = ", ".join(sorted(valid))
            issues.append(
                issue(
                    "warning",
                    "domain_invalid_value",
                    art.rel,
                    f"`domain: {value!r}` is not in CONFIG.personal.domains "
                    f"({allowed}). Fix the value, or add it to config.yaml "
                    f"under `personal.domains:`.",
                )
            )
    return issues


def _iter_vault_frontmatters(ctx: LintContext):
    """Yield ``(vault_rel, fm)`` for every `.md` under raw/, daily/, inbox/
    (walked + parsed here) and knowledge/ (reused from the corpus model —
    no second knowledge read)."""
    for root in (ctx.vault / "raw", ctx.vault / "daily", ctx.vault / "inbox"):
        if not root.exists():
            continue
        for md in root.rglob("*.md"):
            yield str(md.relative_to(ctx.vault)), _read_frontmatter(md)
    for art in ctx.articles:
        try:
            rel = art.path.relative_to(ctx.vault).as_posix()
        except ValueError:
            rel = f"knowledge/{art.rel}"
        yield rel, art.fm


def check_compile_role(ctx: LintContext) -> list[Issue]:
    """Reject frontmatter `compile_role:` values not in VALID_ROLES.

    Walks every `.md` under raw/, daily/, knowledge/, inbox/. Files that omit
    `compile_role:` get no issue (default-by-location inference handles them
    at compile time per `scripts.core.compile_role.infer_compile_role`).

    Cross-location-move warning (slice plan mentions detecting renames across
    top-level boundaries without explicit override) is deferred — needs
    git-history walk, tracked as follow-up.
    """
    issues: list[Issue] = []
    for rel, fm in _iter_vault_frontmatters(ctx):
        role = fm.get("compile_role")
        if role is None:
            continue
        if role not in _COMPILE_ROLE_VALID:
            valid_list = ", ".join(sorted(_COMPILE_ROLE_VALID))
            issues.append(
                issue(
                    "error",
                    "compile_role_invalid",
                    rel,
                    f"`compile_role: {role!r}` is not a valid value. Allowed: {valid_list}.",
                )
            )
    return issues


def check_author_required_on_source_and_final(ctx: LintContext) -> list[Issue]:
    """`compile_role: source-and-final` pages MUST carry `author:` frontmatter.

    Provenance protection: when operator-personal content sits in
    knowledge/concepts/ alongside compile-output concepts, the only thing
    distinguishing them is the frontmatter author + compile_role pair. If a
    source-and-final page loses its `author:` field, the page becomes
    indistinguishable from a regular compile-output concept and can drown in
    the noise. This check makes that loss detectable at lint time.

    (Operator-feedback after M014 dream-cycle: "ich will nicht, dass meine
    persoenlichen texte irgendwann einfach rausgefiltert werden oder
    unbedeutend werden". Lint is the enforcement surface.)
    """
    issues: list[Issue] = []
    for rel, fm in _iter_vault_frontmatters(ctx):
        if fm.get("compile_role") != "source-and-final":
            continue
        if not fm.get("author"):
            issues.append(
                issue(
                    "error",
                    "source_and_final_missing_author",
                    rel,
                    "`compile_role: source-and-final` requires an `author:` "
                    "frontmatter field. Without it, operator-authored content "
                    "is indistinguishable from compile-output and can drown "
                    "in the noise. Add `author: <name>` (or set "
                    "`personal.implicit_operator_author` and operator-author "
                    "files inherit it).",
                )
            )
    return issues
