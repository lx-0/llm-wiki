# Lazy collector registration (M034 candidate, surfaced in M033-S02)

**Status:** collectors **shipped** in M034-S06-T03 (`collectors.MODULES`, DECISIONS
2026-10-16 "The collector registry is a lazy table").
- The cost below had shrunk to ~10 ms by then. `import collectors` is 0.014 s after.
- `--list` still imports every collector, because the desktop shows each one's
  `configured`.
- Left: `preprocessors/` and `producers/` keep the eager shape. Their cost is small, so
  that is low priority, for the milestone-close fan-out to decide.

Recorded 2026-10-14 (M033-S02-T05 / T06).

**Today:** `collectors/__init__.py` imports every collector module so the `@register`
decorators run — the Registry is populated by package import. Consequences: (1) every
`wiki index`, `wiki collect …`, `wiki ingest-youtube` and the three by-path entry scripts
import the whole package (httpx, yt-dlp, pillow, the Google clients …) — ~0.25 s on the dev
Mac (measured 2026-10-14: `import collectors` 0.28–0.33 s against a 0.07 s interpreter
baseline); (2) a module the package imports cannot run as `python -m collectors.<x>` (runpy
double import, double registration) — the reason the entry scripts exist; (3) the
`__package__` guard in `folder_index.py` existed only to dodge (1) and is gone since T05. The
same shape holds for `preprocessors/` and `producers/`.

**Proposal:** discovery without import — a static table in `collectors/__init__.py` (name →
module path plus the SPEC fields `--list` needs) or entry-point metadata; `get_collector(name)`
imports one module, `all_collectors()` imports all (for `--list` and piggyback discovery).
Keeps the listing / run order explicit (today the `# isort: off` block).

**Cost / risk:** registry tests + the oracle (`collect --list --json` is a desktop seam);
piggyback discovery in `core/piggybacks.py` reads SPECs and must not regress; the
`is_configured()` probes in `wiki doctor` call into every collector anyway. Not a docs change
and not an S03 fold (no duplicate helper here) — a dispatcher-surface decision.
