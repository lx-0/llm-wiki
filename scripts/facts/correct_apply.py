"""Agentically propagate a hard fact across the vault (knowledge/, daily/, raw/).

Reads `knowledge/facts/<slug>.md`, then spawns a Claude Agent SDK session with
edit permissions over the vault. The agent strikes false claims, renames files
for disambiguation, and fixes wikilinks. On success the fact's frontmatter
gets `applied: <iso-ts>` written back.

Usage:
    uv run python scripts/facts/correct_apply.py <slug>           # apply one fact
    uv run python scripts/facts/correct_apply.py <slug> --dry-run # plan only, no edits
"""

import os
os.environ["CLAUDE_INVOKED_BY"] = "correct_apply"

import argparse
import asyncio
import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claude_agent_sdk import query

from core import frontmatter
from core.paths import (
    CONCEPTS_DIR,
    DAILY_DIR,
    FACTS_DIR,
    INDEX_FILE,
    KNOWLEDGE_DIR,
    LOG_FILE,
    ROOT_DIR,
)
from core.utils import now_iso, today_iso
from core.config import CONFIG  # noqa: E402
from core.prompts import render  # noqa: E402
from core.sdk_helpers import SdkCallSpec, WriteScope, run_sdk_query  # noqa: E402
from core.ollama_client import parse_json_lenient  # noqa: E402
from core.links import (  # noqa: E402
    WIKILINK_RE,
    rename_article,
    resolve_link,
    strip_table_escape,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("correct-apply")


# Frontmatter read/backup via the single core.frontmatter grammar (C03).
# Writebacks stamp single keys with `frontmatter.update_fields` — surgical
# line-replace, never a safe_dump round-trip of the operator's on-disk YAML
# (DECISIONS 2026-05-15).


_ACTION_KEYS = ("superseded", "edited", "renamed", "deleted")


def _parse_proposed_actions(text: str) -> dict:
    """Extract the agent's `## Proposed actions` JSON block, shape-guarded.

    Never raises — a malformed or absent block yields all-empty lists, so a bad
    agent run degrades to "nothing to execute" rather than crashing the apply.
    LLM output lies about types (CLAUDE.md), so every value is `isinstance`-
    guarded and malformed `renamed` entries are dropped.
    """
    empty = {k: [] for k in _ACTION_KEYS}
    try:
        data = parse_json_lenient(text)
    except (json.JSONDecodeError, ValueError):
        return empty
    if not isinstance(data, dict):
        return empty
    out = {k: [] for k in _ACTION_KEYS}
    for key in _ACTION_KEYS:
        value = data.get(key)
        if not isinstance(value, list):
            continue
        if key == "renamed":
            out[key] = [
                {"from": e["from"], "to": e["to"]}
                for e in value
                if isinstance(e, dict) and "from" in e and "to" in e
            ]
        else:
            out[key] = [x for x in value if isinstance(x, str)]
    return out


def _execute_renames(actions: dict, vault: Path) -> list:
    """Perform the agent's proposed renames engine-side (move + wikilink rewrite).

    The agent never renames files itself (no shell); it nominates {from,to} in
    the proposal block and the engine executes here, skipping unsafe entries.
    Returns the list of renames actually performed (so reporting can tell an
    engine rename apart from an unexplained deletion).
    """
    executed = []
    for entry in actions.get("renamed", []):
        old = (vault / entry["from"]).resolve()
        new = (vault / entry["to"]).resolve()
        if not old.exists():
            log.warning("rename skipped — source missing: %s", entry["from"])
            continue
        if new.exists():
            log.warning("rename skipped — target exists: %s", entry["to"])
            continue
        try:
            counts = rename_article(old, new, KNOWLEDGE_DIR, vault)
            log.info(
                "Renamed %s → %s (%d ref(s) rewritten)",
                entry["from"], entry["to"], counts["articles_rewritten"],
            )
            executed.append(entry)
        except Exception as exc:  # noqa: BLE001 — a bad rename must not abort the run
            log.warning("rename failed %s → %s: %s", entry["from"], entry["to"], exc)
    return executed


def _scan_candidates(terms: list, roots: list) -> list:
    """Files matching any negation term, with a planned per-file action.

    Files outer, terms inner — one read per file, not an O(terms·files) re-scan.
    A term in the title/H1/slug → "primary" (supersede, delete-eligible); a
    body-only hit → "mention" (edit). Skips `index.md`. Vault-relative paths.
    """
    lowered = [t.lower() for t in terms if t]
    if not lowered:
        return []
    out = []
    for base in roots:
        base = Path(base)
        if not base.exists():
            continue
        vault = base.parent
        for path in sorted(base.rglob("*.md")):
            if path.name == "index.md" and path.parent == base:
                continue
            # facts/ are authoritative source-of-truth, never an apply target —
            # and a fact file matches its own negation term.
            if path.parent.name == "facts" and path.parent.parent == base:
                continue
            try:
                text = path.read_text(encoding="utf-8").lower()
            except OSError:
                continue
            hits = [t for t in lowered if t in text]
            if not hits:
                continue
            # "primarily about" = the term is in the H1 title or the slug, not
            # merely somewhere in the body (a short file's body must not fool us).
            title_line = next((ln for ln in text.split("\n") if ln.startswith("# ")), "")
            head = title_line + " " + path.stem.lower()
            primary = any(t in head for t in hits)
            out.append({
                "path": path.relative_to(vault).as_posix(),
                "action": "supersede (delete-eligible)" if primary else "edit",
                "primary": primary,
            })
    return out


def _tree_safe_for_deletion(vault: Path) -> tuple[bool, str]:
    """A deletion run is only safe on a clean git tree — that is what makes
    `.trash` + `git restore` recovery trustworthy. The just-created fact under
    `knowledge/facts/` is expected to be uncommitted, so it is excluded.
    """
    if not (vault / ".git").exists():
        return False, "vault is not a git repository — deletions would be unrecoverable"
    try:
        proc = subprocess.run(
            ["git", "-C", str(vault), "status", "--porcelain",
             "--", "knowledge", ":(exclude)knowledge/facts"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False, "git status failed — cannot verify a clean tree"
    if proc.returncode != 0:
        return False, "git status failed — cannot verify a clean tree"
    if proc.stdout.strip():
        return False, "knowledge/ has uncommitted changes — commit or stash before a deletion run"
    return True, ""


def _deletion_allowed(fm: dict, allow_delete_flag: bool) -> bool:
    """Whether `apply` may execute deletions: the per-run CLI flag OR a per-fact
    `disposition: delete` field. Default (neither) → False → supersede only.

    A `supersession` fact (was true, now outdated) is annotate-only — neither the
    flag nor `disposition` can open the gate; only `negation` is delete-eligible.
    """
    if fm.get("status") == "supersession":
        return False
    return bool(allow_delete_flag) or fm.get("disposition") == "delete"


def _clear_index_rows(index_file: Path, doomed: set, vault: Path) -> int:
    """Drop `index.md` rows whose wikilink resolves to a to-be-deleted file.

    Runs BEFORE the files move to `.trash` (resolution needs them present).
    """
    if not index_file.exists():
        return 0
    kept, dropped = [], 0
    for line in index_file.read_text(encoding="utf-8").split("\n"):
        drop = False
        for m in WIKILINK_RE.finditer(line):
            target, _ = strip_table_escape(m.group(2), m.group(4))
            resolved = resolve_link(target, index_file, vault)
            if resolved is not None and resolved.resolve() in doomed:
                drop = True
                break
        if drop:
            dropped += 1
        else:
            kept.append(line)
    if dropped:
        index_file.write_text("\n".join(kept), encoding="utf-8")
    return dropped


def _execute_deletes(actions: dict, vault: Path, *, allowed: bool) -> list:
    """Move agent-nominated articles to `.trash/<ts>/` (never `unlink`), gated.

    The move IS the backup — deletions stay recoverable. Off by default
    (`allowed=False`): a nomination is logged and ignored, the article is kept
    (superseded instead). Only files under `knowledge/` are eligible. Returns the
    executed rel-paths so reporting treats them as accounted-for.
    """
    nominated = actions.get("deleted", [])
    if not allowed:
        if nominated:
            log.info(
                "deletion gate off — %d nominated file(s) kept (superseded, not deleted)",
                len(nominated),
            )
        return []

    knowledge = KNOWLEDGE_DIR.resolve()
    doomed: set = set()
    targets: list[tuple[str, Path]] = []
    for rel in nominated:
        path = (vault / rel).resolve()
        if not path.exists():
            log.warning("delete skipped — missing: %s", rel)
            continue
        try:
            path.relative_to(knowledge)
        except ValueError:
            log.warning("delete skipped — outside knowledge/: %s", rel)
            continue
        doomed.add(path)
        targets.append((rel, path))

    if not targets:
        return []

    _clear_index_rows(INDEX_FILE, doomed, vault)

    trash_root = vault / ".trash" / datetime.now().strftime("%Y%m%d-%H%M%S")
    executed = []
    for rel, path in targets:
        dest = trash_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        path.rename(dest)
        log.info("Trashed %s → %s", rel, dest)
        executed.append(rel)
    return executed


# ── Ground-truth filesystem-delta reporting (issue #5) ──
# The engine records what ACTUALLY changed on disk — never the agent's free-text
# summary, which under-reported 17 deletions as 6. git porcelain when the vault
# is a repo, else a pre/post mtime snapshot.

def _parse_porcelain(out: str) -> dict:
    """Classify `git status --porcelain` lines into created/modified/deleted/renamed."""
    delta = {"created": [], "modified": [], "deleted": [], "renamed": []}
    for line in out.splitlines():
        if not line.strip():
            continue
        code, rest = line[:2], line[3:]
        if "R" in code:
            delta["renamed"].append(rest)
        elif "D" in code:
            delta["deleted"].append(rest)
        elif code == "??" or "A" in code:
            delta["created"].append(rest)
        elif "M" in code:
            delta["modified"].append(rest)
    return delta


def _git_delta(vault: Path) -> dict | None:
    """Real delta via git porcelain (scoped to knowledge/), or None if not a repo."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(vault), "status", "--porcelain", "--", "knowledge"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return _parse_porcelain(proc.stdout)


def _snapshot(roots) -> dict:
    """`{path: (mtime_ns, size)}` for every file under the given roots."""
    snap: dict[str, tuple[int, int]] = {}
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        paths = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for p in paths:
            try:
                st = p.stat()
                snap[str(p)] = (st.st_mtime_ns, st.st_size)
            except OSError:
                continue
    return snap


def _delta_from_snapshot(before: dict, after: dict) -> dict:
    """created/modified/deleted from two `_snapshot` dicts (non-git fallback)."""
    delta = {"created": [], "modified": [], "deleted": [], "renamed": []}
    for path, sig in after.items():
        if path not in before:
            delta["created"].append(path)
        elif before[path] != sig:
            delta["modified"].append(path)
    for path in before:
        if path not in after:
            delta["deleted"].append(path)
    return delta


def _divergence(actions: dict, delta: dict, executed_renames: list) -> list:
    """Warnings where the real filesystem delta contradicts what the engine did.

    Load-bearing check: a file vanished that neither a declared deletion nor an
    engine-executed rename explains — the issue-#5 failure (an article gone with
    no accounting). Renames look like delete(old)+create(new) in a snapshot or an
    unstaged git tree, so engine-executed renames are subtracted first; otherwise
    every rename would false-alarm. Basename-normalized because porcelain paths
    (repo-relative) and snapshot paths (absolute) differ by mode.
    """
    def _base(p: str) -> str:
        return Path(p).name

    rename_froms = {_base(r["from"]) for r in executed_renames}
    declared_del = {_base(d) for d in actions.get("deleted", [])}
    real_del = {_base(d) for d in delta.get("deleted", [])}
    surprise = real_del - rename_froms - declared_del
    warnings = []
    if surprise:
        warnings.append(
            f"{len(surprise)} file(s) vanished with no accounting "
            f"({', '.join(sorted(surprise))}) — not a declared deletion or an "
            f"engine rename. Investigate before trusting this run (issue #5)."
        )
    return warnings


def _report_filesystem_delta(delta: dict, divergences: list) -> None:
    log.info(
        "Filesystem delta — created: %d, modified: %d, renamed: %d, deleted: %d",
        len(delta["created"]), len(delta["modified"]),
        len(delta["renamed"]), len(delta["deleted"]),
    )
    for category in ("created", "modified", "renamed", "deleted"):
        for path in delta[category]:
            log.info("  %s: %s", category, path)
    for warning in divergences:
        log.warning(warning)


def _apply_call_spec(*, source: str, input_chars: int) -> SdkCallSpec:
    """Sandboxed ``SdkCallSpec`` for the `apply()` agent (M028, issue #5).

    Non-destructive by construction: no `Bash` (the agent cannot `rm`/`git mv`),
    the harness wires a PreToolUse path-scope hook constraining Write/Edit to the
    wiki's editable surfaces, `permission_mode="default"`, and a config-knob turn
    bound. Mirrors the safe `reconcile_fact()` pattern. Destructive ops (delete,
    rename) are engine-owned post-steps, not agent actions.

    Scope note: writes are allowed across `knowledge/` (minus `facts/`),
    `daily/`, `index.md`, and the operations log; `knowledge/facts/` is
    write-protected via ``denied_subpaths`` (deny takes precedence over the
    allowed `knowledge/` root) — the fact files are the source of truth the
    agent must never edit. No ``legacy_allowed_tools`` → the harness always
    uses the hook shape here, regardless of the compile rollback flag.
    """
    return SdkCallSpec(
        label="correct_apply",
        logger=log,
        model=CONFIG.models.compile_model,
        cwd=ROOT_DIR,
        max_turns=CONFIG.limits.correct_apply_max_turns,
        system_prompt={"type": "preset", "preset": "claude_code"},
        allowed_tools=("Read", "Glob", "Grep", "Write", "Edit"),
        write_scope=WriteScope(
            roots=(KNOWLEDGE_DIR, DAILY_DIR, INDEX_FILE, LOG_FILE),
            denied_subpaths=(FACTS_DIR,),
        ),
        source=source,
        input_chars=input_chars,
    )


async def apply(slug: str, dry_run: bool, allow_delete: bool = False, force: bool = False) -> int:
    fact_path = FACTS_DIR / f"{slug}.md"
    if not fact_path.exists():
        log.error("No such fact: %s (looked at %s)", slug, fact_path)
        return 1

    fact_text = fact_path.read_text(encoding="utf-8")
    fm, _body = frontmatter.parse(fact_text)
    if fm.get("type") != "fact":
        log.warning("File %s does not have type: fact — proceeding anyway.", fact_path)

    deletion_allowed = _deletion_allowed(fm, allow_delete)
    # The guard blocks only a REAL deletion run — a --dry-run is non-destructive
    # and must always reach the blast-radius preview (it is the run you make to
    # decide whether to clean the tree first).
    if deletion_allowed and not force and not dry_run:
        safe, reason = _tree_safe_for_deletion(ROOT_DIR)
        if not safe:
            log.error(
                "Refusing deletion-enabled run: %s. Re-run with --force to override.", reason
            )
            return 3

    rel_fact_path = fact_path.relative_to(ROOT_DIR)
    prompt = render(
        "correct_apply",
        fact_content=fact_text,
        fact_path=str(rel_fact_path),
        slug=slug,
        today=today_iso(),
        now=now_iso(),
        deletion_allowed="true" if deletion_allowed else "false",
    )

    if dry_run:
        log.info("[dry-run] Would spawn Claude Agent SDK with:")
        log.info("  cwd=%s", ROOT_DIR)
        log.info("  model=%s", CONFIG.models.compile_model)
        log.info("  fact=%s", rel_fact_path)
        log.info("  status=%s", fm.get("status"))
        terms = fm.get("negation_terms") or []
        log.info("  negation_terms=%s", terms)
        log.info("  deletion permitted=%s", deletion_allowed)
        candidates = _scan_candidates(terms, [KNOWLEDGE_DIR, DAILY_DIR])
        log.info("[dry-run] Blast radius — %d candidate file(s):", len(candidates))
        for c in candidates:
            log.info("  %s — %s", c["path"], c["action"])
        if not candidates and terms:
            log.info("  (no files match the negation terms)")
        return 0

    log.info("Spawning agent over vault root %s for fact %s", ROOT_DIR, slug)

    # Snapshot before the agent runs — the non-git fallback for delta reporting.
    is_git = (ROOT_DIR / ".git").exists()
    before_snapshot = None if is_git else _snapshot([KNOWLEDGE_DIR, INDEX_FILE])

    # The harness owns the mechanics (options assembly, path-scope hook,
    # stderr capture, cache-aware usage extraction, LEDGER recording, failure
    # diagnostics); `_apply_call_spec` keeps the sandbox policy here.
    result = await run_sdk_query(
        prompt,
        _apply_call_spec(source=f"fact:{slug}", input_chars=len(prompt)),
        query_fn=query,
    )
    if result.failure is not None:
        return 2

    total_input_tokens = result.input_tokens
    total_output_tokens = result.output_tokens
    result_text = result.result_text

    log.info("Agent done. Tokens — input: %d, output: %d", total_input_tokens, total_output_tokens)
    if result_text:
        print("\n" + result_text + "\n")

    # Execute engine-owned destructive ops the agent proposed (it has no shell).
    # Renames here; deletions are deferred to S02's `.trash` executor.
    actions = _parse_proposed_actions(result_text)
    executed_renames = _execute_renames(actions, ROOT_DIR)
    executed_deletes = _execute_deletes(actions, ROOT_DIR, allowed=deletion_allowed)

    # Ground-truth reporting: what ACTUALLY changed on disk, and a warning when
    # it contradicts the agent's declared actions (issue #5: claimed 6, did 17).
    # Engine-executed deletes are accounted-for (not a surprise).
    accounted = dict(actions)
    accounted["deleted"] = list(actions.get("deleted", [])) + executed_deletes
    delta = _git_delta(ROOT_DIR)
    if delta is None:
        delta = _delta_from_snapshot(before_snapshot or {}, _snapshot([KNOWLEDGE_DIR, INDEX_FILE]))
    _report_filesystem_delta(delta, _divergence(accounted, delta, executed_renames))

    # Mark fact as applied. Re-read to avoid stomping if the agent edited it
    # (it shouldn't — the prompt forbids it — but be safe).
    current_text = fact_path.read_text(encoding="utf-8")
    fm_now, _body_now = frontmatter.parse(current_text)
    if fm_now:
        frontmatter.backup(fact_path)
        applied_at = now_iso()
        frontmatter.update_fields(fact_path, applied=applied_at, updated=today_iso())
        log.info("Marked %s as applied=%s", rel_fact_path, applied_at)
    else:
        log.warning("Could not parse fact frontmatter after run; not updating `applied:`.")

    return 0


# ── Strict concept-reconciliation path (concept-consistency-routine) ──
# Separate from apply(): same module + helpers, but a TIGHT scope. apply()
# is the broad operator-driven "propagate one fact across the whole vault"
# (acceptEdits + Bash + 50 turns). reconcile_fact() is the autonomous-routine
# primitive: writes locked to knowledge/concepts/ via a PreToolUse hook, no
# Bash, bounded turns; structural file-count gate lives in reconcile.py.
# apply() is left untouched.


@dataclass
class ReconcileResult:
    slug: str
    status: str            # ok | skipped | failed | dry_run
    cost_usd: float = 0.0
    files: list[str] = field(default_factory=list)
    detail: str = ""


async def reconcile_fact(
    slug: str,
    violating_files: list[str],
    *,
    dry_run: bool,
) -> ReconcileResult:
    """Reconcile the given concept files against one hard fact, strict-scoped.

    `violating_files` are vault-relative paths the caller (reconcile.py, from
    lint.check_facts_violations) already identified. The agent may only edit
    files under knowledge/concepts/ (enforced by the PreToolUse hook); the
    prompt forbids touching anything else, deleting, renaming, or editing
    provenance frontmatter. On success the fact is stamped `last_reconciled:`.
    """
    fact_path = FACTS_DIR / f"{slug}.md"
    if not fact_path.exists():
        return ReconcileResult(slug, "failed", detail=f"no such fact: {slug}")
    if not violating_files:
        return ReconcileResult(slug, "skipped", detail="no violating files")

    fact_text = fact_path.read_text(encoding="utf-8")
    files_block = "\n".join(f"- `{f}`" for f in violating_files)
    prompt = render(
        "reconcile_concept",
        fact_content=fact_text,
        fact_path=str(fact_path.relative_to(ROOT_DIR)),
        slug=slug,
        today=today_iso(),
        now=now_iso(),
        violating_files=files_block,
    )

    if dry_run:
        return ReconcileResult(
            slug, "dry_run", files=violating_files,
            detail=f"would reconcile {len(violating_files)} file(s)",
        )

    # Strict scope: writes locked to knowledge/concepts/ + the operations log
    # via the harness PreToolUse hook. No `legacy_allowed_tools`, so the hook
    # shape applies regardless of the compile rollback flag. The harness owns
    # usage extraction + LEDGER recording (cache-inclusive, on every outcome).
    result = await run_sdk_query(
        prompt,
        SdkCallSpec(
            label=f"reconcile_fact:{slug}",
            logger=log,
            model=CONFIG.models.compile_model,
            cwd=ROOT_DIR,
            max_turns=CONFIG.limits.concept_reconcile_max_turns,
            system_prompt={"type": "preset", "preset": "claude_code"},
            allowed_tools=("Read", "Glob", "Grep", "Write", "Edit"),
            write_scope=WriteScope(roots=(CONCEPTS_DIR, LOG_FILE)),
            source=f"fact:{slug}",
            input_chars=len(prompt),
        ),
        query_fn=query,
    )
    if result.failure is not None:
        return ReconcileResult(slug, "failed", files=violating_files, detail="SDK call failed")

    cost = result.cost_usd

    # Stamp the fact as reconciled (cooldown key). Re-read to avoid stomping.
    current_text = fact_path.read_text(encoding="utf-8")
    fm_now, _body_now = frontmatter.parse(current_text)
    if fm_now:
        frontmatter.backup(fact_path)
        frontmatter.update_fields(
            fact_path, last_reconciled=now_iso(), updated=today_iso()
        )

    return ReconcileResult(slug, "ok", cost_usd=cost, files=violating_files, detail="reconciled")


def main() -> int:
    parser = argparse.ArgumentParser(description="Propagate a hard fact across the vault.")
    parser.add_argument("slug", help="fact slug (filename without .md)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would happen without spawning the agent",
    )
    parser.add_argument(
        "--allow-delete",
        action="store_true",
        help="permit deletion of factually-false articles (default: supersede only). "
        "Deleted files go to .trash/, never rm. A fact's `disposition: delete` "
        "frontmatter opens the gate per-fact without this flag.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="bypass the clean-git-tree precondition for deletion runs (use with care)",
    )
    args = parser.parse_args()
    return asyncio.run(apply(args.slug, args.dry_run, args.allow_delete, args.force))


if __name__ == "__main__":
    sys.exit(main())
