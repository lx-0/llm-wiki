"""M033-S04-T07 — the module-size gate (exit criterion: god modules split where it pays).

Every module under `scripts/` is at most `LIMIT` lines, unless `docs/engine-layout.md`
§ "Large modules" lists it with the reason it stays one module. The doc IS the
allowlist — one place, read by people and by this test. A listed module that has
shrunk under the limit fails too, so the list can only shrink (the same rule as the
function gate, `tests/test_function_length.py`).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
LAYOUT = REPO / "docs" / "engine-layout.md"
LIMIT = 1000

# `- \`scripts/<path>.py\` — <reason>` under the "## Large modules" heading.
_ENTRY_RE = re.compile(r"^- `(scripts/[^`]+\.py)` — (.+)$")


def _sizes() -> dict[str, int]:
    return {
        str(p.relative_to(REPO)): len(p.read_text(encoding="utf-8").splitlines())
        for p in sorted(SCRIPTS.rglob("*.py"))
    }


def _reasons() -> dict[str, str]:
    """The "Large modules" section of docs/engine-layout.md as {path: reason}."""
    text = LAYOUT.read_text(encoding="utf-8")
    m = re.search(r"^## Large modules\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert m, 'docs/engine-layout.md has no "## Large modules" section'
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        e = _ENTRY_RE.match(line.strip())
        if e:
            out[e.group(1)] = e.group(2).strip()
    return out


def test_no_module_over_the_limit_without_a_reason() -> None:
    reasons = _reasons()
    offenders = sorted(
        ((n, path) for path, n in _sizes().items() if n > LIMIT and path not in reasons),
        reverse=True,
    )
    assert offenders == [], (
        f"modules over {LIMIT} lines without a reason in docs/engine-layout.md "
        '§ "Large modules" (split them, or state why they stay one module):\n'
        + "\n".join(f"  {n:5d}  {path}" for n, path in offenders)
    )


def test_the_large_module_list_only_shrinks() -> None:
    sizes = _sizes()
    stale = [
        f"{path}: {'gone' if path not in sizes else f'{sizes[path]} lines'} — remove the entry"
        for path in _reasons()
        if path not in sizes or sizes[path] <= LIMIT
    ]
    assert stale == [], "stale Large-modules entries:\n" + "\n".join(f"  {s}" for s in stale)


def test_every_reason_is_a_sentence() -> None:
    short = [path for path, reason in _reasons().items() if len(reason.split()) < 6]
    assert short == [], f"a reason is a sentence, not a label: {short}"
