"""Vault Health Check — colored ASCII status dashboard.

Run from a vault root (or with --vault <path>) to print a one-shot snapshot
of knowledge counts, raw-source distribution, compile backlog, active compile
run, graph density, and pipeline cadence.

Read-only. Never mutates state. Never triggers compile / piggyback.

Usage:
    cd <vault>
    uv run --project .wiki python .wiki/scripts/health.py

    # from anywhere
    uv run --project ~/path/to/.wiki python ~/path/to/.wiki/scripts/health.py \
        --vault ~/path/to/vault
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

# ---------- ANSI ----------
RST = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GRN = "\033[32m"
YEL = "\033[33m"
BLU = "\033[34m"
MAG = "\033[35m"
CYN = "\033[36m"
GRY = "\033[90m"


def supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


# strip ANSI when not a TTY
def maybe(*codes: str) -> str:
    return "".join(codes) if supports_color() else ""


# ---------- helpers ----------
def count_md(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(1 for f in path.rglob("*.md"))


def count_md_flat(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(1 for f in path.iterdir() if f.is_file() and f.suffix == ".md")


def bar(pct: float, width: int = 26, fill: str = "", empty_color: str = "") -> str:
    pct = max(0.0, min(100.0, pct))
    n = int(round(width * pct / 100))
    return f"{fill}{'█' * n}{empty_color or maybe(GRY)}{'░' * (width - n)}{maybe(RST)}"


SPARK = "▁▂▃▄▅▆▇█"


def sparkline(values: list[int]) -> str:
    if not values:
        return ""
    mn, mx = min(values), max(values)
    if mn == mx:
        return SPARK[3] * len(values)
    step = (mx - mn) / (len(SPARK) - 1)
    return "".join(SPARK[min(len(SPARK) - 1, int((v - mn) / step))] for v in values)


def box_top(title: str, width: int = 60, suffix: str = "") -> str:
    sfx = f" {suffix} " if suffix else ""
    pad = width - len(title) - len(sfx) - 4
    return f"{maybe(DIM)}╭─ {maybe(RST)}{maybe(BOLD)}{title}{maybe(RST)} {maybe(DIM)}{'─' * max(1, pad)}{sfx}╮{maybe(RST)}"


def box_bot(width: int = 60) -> str:
    return f"{maybe(DIM)}╰{'─' * (width - 2)}╯{maybe(RST)}"


def line(text: str, width: int = 60) -> str:
    visible = re.sub(r"\033\[[0-9;]*m", "", text)
    pad = width - 4 - len(visible)
    return f"{maybe(DIM)}│ {maybe(RST)}{text}{' ' * max(0, pad)}{maybe(DIM)} │{maybe(RST)}"


# ---------- collectors ----------
def collect_knowledge(vault: Path) -> dict[str, int]:
    out = {}
    for sub in ["concepts", "connections", "projects", "people", "qa"]:
        out[sub] = count_md_flat(vault / "knowledge" / sub)
    return out


def collect_raw(vault: Path) -> dict[str, int]:
    return {
        "memories": count_md_flat(vault / "raw" / "memories"),
        "notes": count_md(vault / "raw" / "notes"),
        "articles": count_md_flat(vault / "raw" / "articles"),
        "daily": count_md_flat(vault / "daily"),
        "inbox": count_md_flat(vault / "inbox"),
        "Clippings": count_md_flat(vault / "Clippings"),
    }


def collect_state(vault: Path) -> dict:
    """Try both old and new state locations."""
    candidates = [
        vault / ".wiki" / "scripts" / "state" / "state.json",
        vault / ".wiki" / "state" / "state.json",
    ]
    for p in candidates:
        if p.exists():
            return json.loads(p.read_text())
    return {"ingested": {}}


def collect_run_progress(vault: Path) -> tuple[int, int]:
    """Tail the most recent compile log under /tmp; return (done, started)."""
    tmp = Path("/tmp")
    logs = sorted(tmp.glob("compile-run-*.log"), reverse=True)
    if not logs:
        return (0, 0)
    txt = logs[0].read_text(errors="ignore")
    return (txt.count("Done:"), txt.count("Compiling:"))


def count_inline_links(vault: Path) -> tuple[int, int]:
    """Sum of [[…]] occurrences across all concept bodies; concept count."""
    folder = vault / "knowledge" / "concepts"
    if not folder.is_dir():
        return (0, 0)
    pat = re.compile(r"\[\[")
    total = 0
    n = 0
    for f in folder.iterdir():
        if f.suffix != ".md":
            continue
        n += 1
        total += len(pat.findall(f.read_text(errors="ignore")))
    return (total, n)


def count_orphans(vault: Path) -> int:
    folder = vault / "knowledge" / "concepts"
    if not folder.is_dir():
        return 0
    return sum(1 for f in folder.iterdir() if f.suffix == ".md" and "[[" not in f.read_text(errors="ignore"))


def daily_activity(vault: Path, days: int = 14) -> list[int]:
    folder = vault / "daily"
    if not folder.is_dir():
        return []
    files = {f.stem for f in folder.iterdir() if f.suffix == ".md"}
    today = dt.date.today()
    return [1 if (today - dt.timedelta(days=i)).isoformat() in files else 0 for i in range(days - 1, -1, -1)]


def latest_in(folder: Path, suffix: str = ".md") -> str | None:
    if not folder.is_dir():
        return None
    files = sorted([f.name for f in folder.iterdir() if f.suffix == suffix])
    return files[-1] if files else None


# ---------- render ----------
def render(vault: Path) -> str:
    W = 62
    out: list[str] = []

    now = dt.datetime.now()
    knowledge = collect_knowledge(vault)
    raw = collect_raw(vault)
    state = collect_state(vault)
    inline_links, concept_n = count_inline_links(vault)
    orphan_n = count_orphans(vault)
    activity = daily_activity(vault)

    total_raw = sum(raw.values())
    ingested = len(state.get("ingested", {}))
    backlog = max(0, total_raw - ingested)
    pct_ingested = 100 * ingested / total_raw if total_raw else 0

    done, started = collect_run_progress(vault)
    run_active = done > 0 and started >= done

    inline_per_concept = inline_links / concept_n if concept_n else 0
    target_min, target_max = 15, 25

    hour = now.hour
    gate = 18

    # Header
    out.append(f"{maybe(BOLD, CYN)}╔{'═' * (W - 2)}╗{maybe(RST)}")
    title = f"  WIKI HEALTH  ·  {now:%Y-%m-%d %H:%M}"
    out.append(f"{maybe(BOLD, CYN)}║{title}{' ' * (W - 2 - len(title))}║{maybe(RST)}")
    out.append(f"{maybe(BOLD, CYN)}╚{'═' * (W - 2)}╝{maybe(RST)}")
    out.append("")

    # KNOWLEDGE
    total_k = sum(knowledge.values())
    out.append(box_top("KNOWLEDGE", W, suffix=f"{total_k} articles "))
    if total_k:
        max_n = max(knowledge.values())
        for label, n in knowledge.items():
            if n == 0:
                continue
            barw = 24
            filled = int(round(barw * n / max_n))
            color = maybe(CYN if label == "concepts" else MAG if label == "connections" else BLU)
            out.append(line(f"{label:12s} {color}{'█' * filled}{maybe(GRY)}{'░' * (barw - filled)}{maybe(RST)}  {n:>4}", W))
    out.append(box_bot(W))
    out.append("")

    # RAW SOURCES
    out.append(box_top("RAW SOURCES", W, suffix=f"{total_raw} total "))
    if total_raw:
        max_r = max(raw.values()) or 1
        for label, n in raw.items():
            barw = 24
            filled = int(round(barw * n / max_r))
            pct = 100 * n / total_raw
            pct_str = f"{pct:>4.1f}%" if pct >= 0.1 else " <0.1%"
            out.append(line(f"{label:12s} {maybe(CYN)}{'█' * filled}{maybe(GRY)}{'░' * (barw - filled)}{maybe(RST)}  {n:>4}  {pct_str}", W))
    out.append(box_bot(W))
    out.append("")

    # COMPILE BACKLOG
    color = GRN if pct_ingested > 70 else YEL if pct_ingested > 30 else RED
    out.append(box_top("COMPILE BACKLOG", W))
    out.append(line(f"ingested  {bar(pct_ingested, fill=maybe(color))} {pct_ingested:>5.1f}%   {ingested}/{total_raw}", W))
    out.append(line(f"{maybe(DIM)}backlog: {backlog} files open{maybe(RST)}", W))
    out.append(box_bot(W))
    out.append("")

    # ACTIVE RUN (if any)
    if run_active:
        cap = 100  # default; could be parsed from log
        run_pct = 100 * done / cap
        out.append(box_top("ACTIVE COMPILE RUN", W, suffix=f"cap={cap} "))
        out.append(line(f"progress  {bar(run_pct, fill=maybe(CYN))} {run_pct:>5.1f}%   {done}/{cap}", W))
        out.append(box_bot(W))
        out.append("")

    # GRAPH DENSITY
    out.append(box_top("GRAPH DENSITY", W))
    barw = 18
    density_pct = min(100, 100 * inline_per_concept / target_max)
    color = GRN if inline_per_concept >= target_min else YEL if inline_per_concept >= target_min / 2 else RED
    filled = int(round(barw * density_pct / 100))
    out.append(line(f"links/concept  {maybe(color)}{'█' * filled}{maybe(GRY)}{'░' * (barw - filled)}{maybe(RST)}  {inline_per_concept:>4.1f}  {maybe(DIM)}target {target_min}-{target_max}{maybe(RST)}", W))
    orphan_color = GRN if orphan_n == 0 else RED
    icon = "✓" if orphan_n == 0 else "✕"
    out.append(line(f"orphans        {maybe(orphan_color)}{icon} {orphan_n} concepts without [[wikilinks]]{maybe(RST)}", W))
    cc_ratio = concept_n / max(knowledge["connections"], 1)
    out.append(line(f"c:cn ratio     {cc_ratio:>4.1f} : 1  {maybe(DIM)}({concept_n}c / {knowledge['connections']}cn){maybe(RST)}", W))
    out.append(box_bot(W))
    out.append("")

    # PIPELINE CADENCE
    out.append(box_top("PIPELINE CADENCE", W))
    gate_open = hour >= gate
    gate_str = f"{maybe(GRN)}✓ open  (hour={hour}≥{gate}){maybe(RST)}" if gate_open else f"{maybe(YEL)}● gated (hour={hour}<{gate}){maybe(RST)}"
    out.append(line(f"compile gate     {gate_str}", W))

    latest_d = latest_in(vault / "daily")
    today_str = now.strftime("%Y-%m-%d")
    d_color = GRN if latest_d and latest_d.startswith(today_str) else YEL
    out.append(line(f"latest daily     {maybe(d_color)}{latest_d or '—'}{maybe(RST)}", W))

    # search reports/ at vault root and at .wiki/reports
    reports_dir = vault / "reports"
    if not reports_dir.is_dir():
        reports_dir = vault / ".wiki" / "reports"
    latest_r = latest_in(reports_dir)
    r_color = GRN if latest_r and today_str in latest_r else YEL
    out.append(line(f"latest review    {maybe(r_color)}{latest_r or '—'}{maybe(RST)}", W))

    if activity:
        spark = sparkline(activity)
        out.append(line(f"daily activity   {maybe(CYN)}{spark}{maybe(RST)}  {maybe(DIM)}(last {len(activity)}d){maybe(RST)}", W))
    out.append(box_bot(W))

    return "\n".join(out)


# ---------- main ----------
def main() -> int:
    p = argparse.ArgumentParser(description="Vault health snapshot.")
    p.add_argument("--vault", type=Path, default=Path.cwd(), help="Vault root (default: cwd).")
    args = p.parse_args()

    vault = args.vault.resolve()
    if not (vault / "knowledge").is_dir() and not (vault / ".wiki").is_dir():
        print(f"error: {vault} doesn't look like a wiki vault (no knowledge/ or .wiki/)", file=sys.stderr)
        return 1

    print(render(vault))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
