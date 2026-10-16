"""`wiki usage` — read back the token-usage ledger (state/usage.json).

Tokens per (provider, model), bucketed by date — the honest usage view that
replaced dollar tracking (DECISIONS 2026-05-23). Read-only; the ledger is
written by every LLM call site via core/usage.py.
"""

import argparse
import json
import sys

from core.console import say
from core.usage import USAGE_FILE


def _fmt(n: int) -> str:
    return f"{n / 1000:.1f}K" if n >= 1000 else str(int(n))


def _row(key: str, i: int, o: int, c: int) -> str:
    return f"  {key:34}  {_fmt(i):>8} in  {_fmt(o):>8} out  {c:>4} call(s)"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Token-usage ledger report (tokens per provider/model)."
    )
    ap.add_argument("--days", type=int, default=7, help="show the last N days (default 7; 0 = all)")
    ap.add_argument("--json", action="store_true", help="print raw JSON")
    args = ap.parse_args()

    if not USAGE_FILE.exists():
        say(
            "No usage recorded yet (state/usage.json absent). "
            "Run a compile / dream / reconcile / collect first."
        )
        return 0

    data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    if args.json:
        say(json.dumps(data, indent=2, sort_keys=True))
        return 0

    days = sorted(data.keys(), reverse=True)
    if args.days > 0:
        days = days[: args.days]

    agg: dict[str, list[int]] = {}
    for day in days:
        say(f"\n{day}")
        for key in sorted(data[day]):
            u = data[day][key]
            i, o, c = u.get("input_tokens", 0), u.get("output_tokens", 0), u.get("calls", 0)
            say(_row(key, i, o, c))
            a = agg.setdefault(key, [0, 0, 0])
            a[0] += i
            a[1] += o
            a[2] += c

    say(f"\nTotals ({len(days)} day(s) shown):")
    for key in sorted(agg):
        i, o, c = agg[key]
        say(_row(key, i, o, c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
