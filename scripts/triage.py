"""`wiki triage` — review + clear the intent-dispatch inbox (workspace/inbox/).

Detected intents (task/idea/note) land with `status: pending`. Triage decides
keep vs drop:
  - accept  → keep it. note/idea = filed; task = greenlit for the
              orchestrate-tasks agent (which runs `status: accepted` tasks).
  - dismiss → drop as noise.

Two separate axes: triage sets `pending → accepted | dismissed`; the
orchestrate-tasks agent later sets a task `accepted → done | blocked` once it has
actually executed it. So `done` always means "task executed", never "triaged".

    wiki triage                  list pending records, grouped by type
    wiki triage --all            list every record (incl. accepted/dismissed/done)
    wiki triage accept <stem>    keep  → status: accepted
    wiki triage dismiss <stem>   drop  → status: dismissed

`<stem>` matches the record filename (a unique prefix is enough). Status is set
by an in-place line-replace — formatting is preserved byte-for-byte.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.paths import WORKSPACE_INBOX_DIR  # noqa: E402

_FM_RE = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)
_ORDER = {"task": 0, "idea": 1, "note": 2}


def _fields(text: str) -> dict[str, str]:
    m = _FM_RE.match(text)
    out: dict[str, str] = {}
    if not m:
        return out
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip('"')
    return out


def _records() -> list[tuple[Path, dict]]:
    if not WORKSPACE_INBOX_DIR.is_dir():
        return []
    recs = []
    for f in sorted(WORKSPACE_INBOX_DIR.glob("*.md")):
        recs.append((f, _fields(f.read_text(encoding="utf-8"))))
    return recs


def _resolve(stem: str) -> Path | None:
    cands = [f for f, _ in _records() if f.stem == stem]
    if not cands:
        cands = [f for f, _ in _records() if f.stem.startswith(stem)]
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


def _list(show_all: bool) -> int:
    recs = _records()
    if not recs:
        print("workspace/inbox/ is empty — nothing to triage.")
        return 0
    shown = [(f, fm) for f, fm in recs if show_all or fm.get("status") == "pending"]
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
        summ = fm.get("summary") or f.stem
        print(f"  • {f.stem}")
        print(f"      ({conf}{flag}) {summ}")
    pend = sum(1 for _, fm in recs if fm.get("status") == "pending")
    print(f"\n{pend} pending · {len(recs)} total.  "
          "Act: wiki triage accept|dismiss <stem>")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="wiki triage", description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd")
    pl = sub.add_parser("list", help="list records (default)")
    pl.add_argument("--all", action="store_true", help="include accepted/dismissed/done")
    # Triage verbs only: keep (accept) / drop (dismiss). `done`/`blocked` are the
    # orchestrate-tasks agent's execution outcomes, not triage decisions.
    _VERB_STATUS = {"accept": "accepted", "dismiss": "dismissed"}
    for verb in _VERB_STATUS:
        sp = sub.add_parser(verb, help=f"{verb} a record → status: {_VERB_STATUS[verb]}")
        sp.add_argument("stem", help="record filename stem (unique prefix ok)")
    ap.add_argument("--all", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.cmd in (None, "list"):
        return _list(getattr(args, "all", False))
    if args.cmd in _VERB_STATUS:
        p = _resolve(args.stem)
        return _set_status(p, _VERB_STATUS[args.cmd]) if p else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
