"""Capture index — the `capture_id → {source_path, created, status}` map (M025).

The bridge the quick-capture-correction loop is built on. The capture collector
calls `record()` at ingest to register each new capture; downstream consumers
read the map via `load()`:

  - S02 (forward link): the daily-digest resolves a capture-ID to its raw
    article (and, later, the compiled interpretation).
  - S03 (supersede): an operator correction quoting a capture-ID flips that
    entry's `status` to "superseded", which the next compile cycle honours.

Idempotent on re-ingest: a re-drop of identical content yields the same
capture-ID, and `record()` leaves any existing entry untouched — so a
"superseded" status set by S03 is NOT reset to "open" by a re-ingest.

Concurrency: the read-modify-write runs under an fcntl flock (same pattern as
`core.usage` / `core.daily_capture`), so parallel collector runs / SessionEnd
flushes can't corrupt the file.
"""

from __future__ import annotations

import fcntl
import re
from contextlib import contextmanager
from pathlib import Path

import yaml

from .paths import KNOWLEDGE_DIR, STATE_DIR
from .utils import load_json_state, save_json_state

CAPTURE_INDEX_FILE = STATE_DIR / "capture_index.json"
_LOCK_FILE = STATE_DIR / "capture_index.lock"

STATUS_OPEN = "open"
STATUS_SUPERSEDED = "superseded"


@contextmanager
def _locked():
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = open(_LOCK_FILE, "w")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        finally:
            fd.close()


def load() -> dict[str, dict]:
    """Return the `capture_id → entry` map ({} if absent or unreadable).

    A corrupt / partially-written file is treated as empty rather than crashing
    the ingest path — the next `record()` rewrites it cleanly.
    """
    try:
        return load_json_state(CAPTURE_INDEX_FILE)
    except (ValueError, OSError):
        return {}


def record(capture_id: str, *, source_path: str, created: str) -> bool:
    """Register a capture at ingest. Idempotent: if `capture_id` is already
    present the existing entry (including any S03-set `status`) is preserved and
    this returns False. Returns True when a new entry was added.
    """
    with _locked():
        index = load()
        if capture_id in index:
            return False
        index[capture_id] = {
            "source_path": source_path,
            "created": created,
            "status": STATUS_OPEN,
        }
        save_json_state(CAPTURE_INDEX_FILE, index)
        return True


_FM_RE = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)


def _compiled_from(path: Path) -> list[str]:
    """The `compiled_from` frontmatter of a compiled article, as a list of source
    strings (str or list in the YAML — both normalised to a list)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    m = _FM_RE.match(text)
    if not m:
        return []
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return []
    if not isinstance(fm, dict):
        return []
    cf = fm.get("compiled_from")
    if isinstance(cf, str):
        return [cf]
    if isinstance(cf, list):
        return [c for c in cf if isinstance(c, str)]
    return []


def resolve_articles(knowledge_dir: Path | None = None) -> dict[str, list[str]]:
    """Map each captured `capture_id` → the knowledge article(s) it was compiled
    into, by joining the index `source_path` against each article's `compiled_from`
    frontmatter (the compile prompts stamp the source path the LLM compiled from).

    Returns `{capture_id: [article_relpath, …]}` — an empty list means the capture
    is recorded but not (yet) compiled into any article. Matching is by the capture
    filename (`capture-<id>.md`), so a differing path prefix in `compiled_from` still
    joins. Pure filesystem scan: no compile/agent dependency (the S02 forward link
    must not forward-depend on S03). `{}` when the index is empty.
    """
    index = load()
    if not index:
        return {}
    name_to_id = {
        Path(entry["source_path"]).name: cid
        for cid, entry in index.items()
        if isinstance(entry, dict) and entry.get("source_path")
    }
    result: dict[str, list[str]] = {cid: [] for cid in index}
    kdir = knowledge_dir or KNOWLEDGE_DIR
    if not kdir.is_dir():
        return result
    root = kdir.parent
    for art in sorted(kdir.rglob("*.md")):
        for cf in _compiled_from(art):
            cid = name_to_id.get(Path(cf.strip()).name)
            if cid is not None:
                rel = str(art.relative_to(root))
                if rel not in result[cid]:
                    result[cid].append(rel)
    return result


def _capture_gist(source_path: str, *, vault_root: Path) -> str:
    """The first non-empty body line of a raw capture, for a one-line digest row."""
    try:
        text = (vault_root / source_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    body = _FM_RE.sub("", text, count=1)
    for line in body.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s if len(s) <= 80 else s[:77].rstrip() + "…"
    return ""


def build_captures_section(date_iso: str, *, vault_root: Path | None = None) -> str | None:
    """The deterministic `## Captures` digest block for one day: each capture
    created on `date_iso`, keyed by short-id, with the interpretation (the article
    it was compiled into, via `resolve_articles()`) and a superseded marker.

    Returns the markdown (trailing newline) or None if no captures that day. Built
    Python-side — a table lookup, NOT an LLM call — so it's exact and testable; the
    runner injects it into the agent-written digest.
    """
    from .paths import ROOT_DIR

    root = vault_root or ROOT_DIR
    index = load()
    todays = {
        cid: e
        for cid, e in index.items()
        if isinstance(e, dict) and str(e.get("created", ""))[:10] == date_iso
    }
    if not todays:
        return None
    resolved = resolve_articles(root / "knowledge")
    lines = ["## Captures", ""]
    for cid in sorted(todays, key=lambda c: str(todays[c].get("created", ""))):
        entry = todays[cid]
        short = cid[:8]
        gist = _capture_gist(entry.get("source_path", ""), vault_root=root)
        gist_part = f" · {gist}" if gist else ""
        articles = resolved.get(cid, [])
        if articles:
            interp = ", ".join(f"[[{a}]]" for a in articles)
            mark = " · _superseded_" if entry.get("status") == STATUS_SUPERSEDED else ""
            lines.append(f"- `{short}`{gist_part} → {interp}{mark}")
        else:
            lines.append(f"- `{short}`{gist_part} → _not yet compiled_")
    return "\n".join(lines) + "\n"
