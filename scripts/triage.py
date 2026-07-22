"""`wiki triage` — review + clear the intent-dispatch inbox (workspace/inbox/).

Detected intents (task/idea/note) land with `status: pending`. Triage decides
keep vs drop:
  - accept a TASK → it MOVES out of inbox/ into `workspace/tasks/<NNN>.md`
    (numbered) and a checkbox line `- [ ] <summary> — [[tasks/<NNN>]]` is added
    to `workspace/todo.md` (the todo list). That is the action: an accepted task
    is a real, listed, actionable item — not just a status flag.
  - accept an idea/note → filed in place (`status: accepted`, stays in inbox/).
  - dismiss → drop as noise (`status: dismissed`, stays in inbox/).

    wiki triage                  list pending records, grouped by type
    wiki triage --all            list every record (incl. accepted/dismissed/done)
    wiki triage list --json      machine-readable list (desktop app / agents)
    wiki triage accept <stem>    task → moved to tasks/ + listed in todo.md
    wiki triage dismiss <stem>   drop  → status: dismissed

`<stem>` matches the record filename (a unique prefix is enough).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import frontmatter  # noqa: E402
from core.paths import (  # noqa: E402
    WORKSPACE_INBOX_DIR,
    WORKSPACE_TASKS_DIR,
    WORKSPACE_TODO,
)

_ORDER = {"task": 0, "idea": 1, "note": 2}
# Anchor line in todo.md after which accepted-task checkbox lines are inserted.
_TODO_MARKER = "<!-- accepted-tasks"


def _fields(text: str) -> dict[str, str]:
    """Record frontmatter as a flat str dict, via the single core.frontmatter
    grammar (C03). Real YAML parsing decodes quoted/escaped `summary:` values —
    the old bare `.strip('\"')` reader surfaced json.dumps-escaped umlauts and
    quotes as garbage (and copied them into todo.md on accept). Non-string
    scalars (YAML timestamps etc.) are coerced to str for display."""
    fm, _body = frontmatter.parse(text)
    out: dict[str, str] = {}
    for k, v in fm.items():
        if isinstance(v, str):
            out[str(k)] = v
        else:
            out[str(k)] = "" if v is None else str(v)
    return out


def _capture_date(source: str) -> str:
    """Capture date (photo/voice recorded), parsed from the source filename —
    photos `2026-06-04-213644`, voice `voice-2026-05-17-…`, screenshots
    `Screenshot_20240904_…`. NOT detected_at (which is when it was classified)."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", source) or re.search(r"(\d{4})(\d{2})(\d{2})", source)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _detail(text: str) -> str:
    """Human rationale for one record: the first body paragraph minus the
    provenance prefix and the CLI-instruction suffix that `_record.py` writes
    (`_Detected from [[stem]] · kind · confidence X. {hint} Set \\`status:
    dismissed\\` to drop._`). Owning this scrub HERE keeps the record-format
    coupling engine-internal — GUI/agent consumers get the clean hint via
    `wiki triage list --json` instead of re-scrubbing the template prose
    (rephrase the hint in `_record.py` and only this one reader must follow)."""
    _fm, body = frontmatter.parse(text)
    para = re.sub(r"^\s*#[^\n]*\n", "", body).strip()
    para = re.split(r"\n\s*\n", para)[0] if para else ""
    para = re.sub(r"Detected from[^.]*\.\s*", "", para, flags=re.I)
    para = re.sub(r"\s*Set\s+`?status.*$", "", para, flags=re.I | re.S)
    para = re.sub(r"\[\[([^\]]+)\]\]", lambda m: m.group(1).split("|")[0], para)
    para = re.sub(r"[_*`]", "", para)
    return re.sub(r"\s+", " ", para).strip()[:240]


def _records() -> list[tuple[Path, dict, str]]:
    if not WORKSPACE_INBOX_DIR.is_dir():
        return []
    recs = []
    for f in sorted(WORKSPACE_INBOX_DIR.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        recs.append((f, _fields(text), text))
    return recs


def _resolve(stem: str) -> Path | None:
    cands = [f for f, _, _ in _records() if f.stem == stem]
    if not cands:
        cands = [f for f, _, _ in _records() if f.stem.startswith(stem)]
    if len(cands) == 1:
        return cands[0]
    if len(cands) > 1:
        print(f"ambiguous '{stem}' — matches {len(cands)}: {[c.stem for c in cands][:5]}", file=sys.stderr)
    else:
        print(f"no inbox record matching '{stem}'", file=sys.stderr)
    return None


def _set_status(path: Path, status: str) -> int:
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(r"^status:.*$", f"status: {status}", text, count=1, flags=re.M)
    if n == 0:
        print(f"no status: line in {path.name}", file=sys.stderr)
        return 1
    path.write_text(new, encoding="utf-8")
    print(f"{path.stem} → status: {status}")
    return 0


def _next_task_number() -> str:
    """Next free sequence number across workspace/tasks/, zero-padded to 3."""
    nums = [
        int(m.group(1))
        for f in WORKSPACE_TASKS_DIR.glob("*.md")
        if (m := re.match(r"(\d+)", f.stem))
    ]
    return f"{(max(nums) + 1) if nums else 1:03d}"


def _append_todo(num: str, summary: str) -> None:
    """Add a checkbox line for the accepted task to todo.md (after the anchor)."""
    line = f"- [ ] {summary} — [[tasks/{num}]]"
    if WORKSPACE_TODO.exists():
        lines = WORKSPACE_TODO.read_text(encoding="utf-8").splitlines()
        idx = next((i for i, ln in enumerate(lines) if _TODO_MARKER in ln), None)
        lines.insert(idx + 1 if idx is not None else len(lines), line)
        WORKSPACE_TODO.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        WORKSPACE_TODO.parent.mkdir(parents=True, exist_ok=True)
        WORKSPACE_TODO.write_text(f"# Todo\n\n## Tasks\n\n{line}\n", encoding="utf-8")


def _accept(path: Path) -> int:
    """Accept a record. A TASK moves to workspace/tasks/<NNN>.md and gets a
    checkbox line in todo.md; an idea/note is filed in place (status: accepted)."""
    text = path.read_text(encoding="utf-8")
    fm = _fields(text)
    if fm.get("type") != "task":
        return _set_status(path, "accepted")
    num = _next_task_number()
    text = re.subn(r"^status:.*$", "status: accepted", text, count=1, flags=re.M)[0]
    WORKSPACE_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    (WORKSPACE_TASKS_DIR / f"{num}.md").write_text(text, encoding="utf-8")
    path.unlink()
    _append_todo(num, fm.get("summary") or path.stem)
    print(f"{path.stem} → accepted: moved to tasks/{num}.md + listed in todo.md")
    return 0


def _json_payload(show_all: bool) -> dict:
    """`wiki triage list --json` — a serializer over the same `_fields`/`_ORDER`
    contract the human list renders (plus the `_detail` body scrub). Machine
    seam for the desktop app + agents; same posture as `wiki doctor --json`."""
    recs = _records()
    shown = [(f, fm, text) for f, fm, text in recs if show_all or fm.get("status") == "pending"]
    shown.sort(key=lambda x: (_ORDER.get(x[1].get("type", ""), 9), x[0].name))
    records = [
        {
            "stem": f.stem,
            "type": fm.get("type", "note"),
            "status": fm.get("status", "pending"),
            "kind": fm.get("kind", ""),
            "summary": fm.get("summary") or f.stem,
            "source": fm.get("source", ""),
            "confidence": fm.get("confidence", ""),
            "detected_at": fm.get("detected_at", ""),
            "date": _capture_date(fm.get("source", "")) or (fm.get("detected_at") or "")[:10],
            "detail": _detail(text),
        }
        for f, fm, text in shown
    ]
    return {
        "records": records,
        "pending": sum(1 for _, fm, _ in recs if fm.get("status") == "pending"),
        "total": len(recs),
    }


def _list(show_all: bool, as_json: bool = False) -> int:
    if as_json:
        print(json.dumps(_json_payload(show_all), indent=2))
        return 0
    recs = _records()
    if not recs:
        print("workspace/inbox/ is empty — nothing to triage.")
        return 0
    shown = [(f, fm) for f, fm, _ in recs if show_all or fm.get("status") == "pending"]
    if not shown:
        print("No pending records. (use --all to see accepted/dismissed/done)")
        return 0
    shown.sort(key=lambda x: (_ORDER.get(x[1].get("type", ""), 9), x[0].name))
    cur = None
    for f, fm in shown:
        t = fm.get("type", "?")
        if t != cur:
            cur = t
            print(f"\n## {t.upper()}")
        st = fm.get("status", "?")
        flag = "" if st == "pending" else f" [{st}]"
        conf = fm.get("confidence", "?")
        date = _capture_date(fm.get("source", "")) or (fm.get("detected_at") or "")[:10] or "—"
        summ = fm.get("summary") or f.stem
        print(f"  • {f.stem}")
        print(f"      ({date} · {conf}{flag}) {summ}")
    pend = sum(1 for _, fm, _ in recs if fm.get("status") == "pending")
    print(f"\n{pend} pending · {len(recs)} total.  "
          "Act: wiki triage accept|dismiss <stem>")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="wiki triage", description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd")
    pl = sub.add_parser("list", help="list records (default)")
    pl.add_argument("--all", action="store_true", help="include accepted/dismissed/done")
    pl.add_argument(
        "--json", action="store_true",
        help="machine-readable list (desktop app / agents)",
    )
    # Triage verbs: accept (task → tasks/ + todo.md; idea/note → filed) / dismiss.
    for verb, helptext in (
        ("accept", "task → moved to tasks/ + listed in todo.md; idea/note filed"),
        ("dismiss", "drop → status: dismissed"),
    ):
        sp = sub.add_parser(verb, help=helptext)
        sp.add_argument("stem", help="record filename stem (unique prefix ok)")
    ap.add_argument("--all", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.cmd in (None, "list"):
        return _list(getattr(args, "all", False), as_json=getattr(args, "json", False))
    if args.cmd == "accept":
        p = _resolve(args.stem)
        return _accept(p) if p else 1
    if args.cmd == "dismiss":
        p = _resolve(args.stem)
        return _set_status(p, "dismissed") if p else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
