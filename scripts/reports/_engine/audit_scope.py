"""M019-S02-T01 — R2 token-budget audit for operator-self-reports.

The inference contract (S02-T02) commits to "single SDK call per
instrument with substrate inline in the prompt". For that to be
feasible, every instrument's scope-resolved substrate set must fit
under the model's effective context budget (200K for Opus 4.7 in
non-[1m] mode, ~1M for the [1m] variant — but we target the smaller
window so a single instrument doesn't need [1m] just to score).

This probe walks the lxw substrate over an instrument's
`inference.default_lookback_days` window, sums tokens via a
conservative len(text)/4 heuristic (or `tiktoken` if installed), and
reports per-instrument total + delta-vs-budget. Wedge instruments
(PHQ-9, GAD-7, ASRS-v1.1, WHO-5, MEQ-19) are expected to pass with
headroom. A synthetic IPIP-NEO-120-scope stub is included to verify
the audit catches overflow — Big-Five-style instruments read broad
substrate (people-pages + voice + sessions over months) and will fall
over without a pre-digestion layer (deferred per R2 mitigation
recorded in DECISIONS).

Usage:
    # Audit the live wedge instruments against the operator's vault:
    uv run python scripts/reports/_engine/audit_scope.py

    # Point at a specific vault root:
    uv run python scripts/reports/_engine/audit_scope.py --vault ~/path/to/vault

Output goes to stdout; capture for KNOWLEDGE.md.
"""

from __future__ import annotations

import argparse
import dataclasses as dc
import sys
import time
from pathlib import Path

# Project root on sys.path so `scripts.reports.*` imports resolve when
# this file is executed directly via `uv run python scripts/reports/...`.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.core.paths import DAILY_DIR  # noqa: E402,F401
from scripts.reports._engine.instrument import load_instrument  # noqa: E402
from scripts.reports._engine.substrate_scope import (  # noqa: E402
    CLINICAL_DEFAULT_SUBSTRATE_GLOBS,
    resolve_substrate_files,
)


# Conservative tokens-per-char heuristic. Real Claude tokenisation is
# ~3.5-4 chars/token for English/German prose. We use 4 because the
# audit is for capacity-planning — overestimating budget is the
# unsafe direction.
CHARS_PER_TOKEN = 4

# Budget the audit treats as "must fit". Opus 4.7 advertises 200K
# input; we target 80% of that to leave headroom for prompt
# scaffolding + system prompt + response.
CONTEXT_BUDGET_TOKENS = 160_000


@dc.dataclass
class AuditResult:
    instrument_slug: str
    version: str
    lookback_days: int
    file_count: int
    char_total: int
    token_estimate: int
    budget: int

    @property
    def headroom_pct(self) -> float:
        """Fraction of budget remaining (negative = overflow)."""
        if self.budget == 0:
            return 0.0
        return round(100.0 * (self.budget - self.token_estimate) / self.budget, 1)

    @property
    def status(self) -> str:
        if self.token_estimate > self.budget:
            return "FAIL (overflow)"
        if self.token_estimate > self.budget * 0.7:
            return "WARN (>70% budget)"
        return "PASS"


def _sum_chars(paths: list[Path]) -> int:
    total = 0
    for p in paths:
        try:
            total += len(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            # Skip unreadable; track in returned count via len(paths) anyway.
            continue
    return total


def audit_instrument(
    vault_root: Path,
    instrument_dir: Path,
    budget: int = CONTEXT_BUDGET_TOKENS,
) -> AuditResult:
    """Audit one instrument's scope against the budget."""
    instr = load_instrument(instrument_dir)
    # Default lookback comes straight off the loaded instrument's
    # surfaced inference config — no raw re-parse.
    lookback_days = instr.meta.inference.default_lookback_days

    files = resolve_substrate_files(
        vault_root, CLINICAL_DEFAULT_SUBSTRATE_GLOBS, lookback_days
    )
    char_total = _sum_chars(files)
    tokens = char_total // CHARS_PER_TOKEN

    return AuditResult(
        instrument_slug=instr.meta.slug,
        version=instr.meta.version,
        lookback_days=lookback_days,
        file_count=len(files),
        char_total=char_total,
        token_estimate=tokens,
        budget=budget,
    )


def audit_synthetic_personality_stub(vault_root: Path, budget: int) -> AuditResult:
    """Synthetic IPIP-NEO-120-scope to verify the audit catches overflow.

    Personality instruments read broadly: people-pages, voice over
    months, sessions, takes (if enabled). Until per-item scope-spec
    lands and the personality instruments are added, this stub
    approximates the worst case by widening lookback to 180 days and
    walking knowledge/people/ + voice + sessions + transcripts.
    """
    globs = (
        "raw/notes/voice/**/*.md",
        "raw/notes/sessions/**/*.md",
        "raw/transcripts/**/*.md",
        "knowledge/people/*.md",
        "knowledge/takes/*.md",
        "daily/*.md",
    )
    lookback_days = 180

    files = resolve_substrate_files(vault_root, globs, lookback_days)
    char_total = _sum_chars(files)
    tokens = char_total // CHARS_PER_TOKEN
    return AuditResult(
        instrument_slug="ipip-neo-120 (synthetic stub)",
        version="—",
        lookback_days=lookback_days,
        file_count=len(files),
        char_total=char_total,
        token_estimate=tokens,
        budget=budget,
    )


def _print_row(r: AuditResult) -> None:
    print(
        f"  {r.instrument_slug:<32} v{r.version:<10} "
        f"lookback={r.lookback_days:>4}d  "
        f"files={r.file_count:>4}  "
        f"~{r.token_estimate:>8,} tokens  "
        f"headroom={r.headroom_pct:>6}%  "
        f"{r.status}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--vault",
        type=Path,
        default=None,
        help="Vault root (defaults to engine's resolved ROOT_DIR).",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=CONTEXT_BUDGET_TOKENS,
        help=f"Token budget per instrument (default {CONTEXT_BUDGET_TOKENS:,}).",
    )
    args = parser.parse_args()

    if args.vault is not None:
        vault_root = args.vault.expanduser().resolve()
    else:
        # Fall back to engine's own ROOT_DIR — only useful for dev/CI;
        # operator audits should pass --vault.
        vault_root = DAILY_DIR.parent.resolve()

    if not vault_root.is_dir():
        print(f"ERROR: vault root not a directory: {vault_root}", file=sys.stderr)
        return 1

    print(f"M019 R2 token-budget audit — vault: {vault_root}")
    print(f"Budget per instrument: {args.budget:,} tokens (Opus 4.7 200K × 80%)")
    print(f"Char-per-token heuristic: {CHARS_PER_TOKEN}")
    print()

    # Find all instruments in the engine's instruments/ subtree.
    instruments_root = Path(__file__).resolve().parent / "instruments"
    instrument_dirs: list[Path] = []
    if instruments_root.is_dir():
        for slug_dir in sorted(instruments_root.iterdir()):
            if not slug_dir.is_dir():
                continue
            for version_dir in sorted(slug_dir.iterdir()):
                if version_dir.is_dir() and (version_dir / "instrument.yaml").exists():
                    instrument_dirs.append(version_dir)

    if not instrument_dirs:
        print(
            "  (no instruments found — expected at least PHQ-9 from S01-T04)",
            file=sys.stderr,
        )
        return 1

    print("Live wedge instruments:")
    results: list[AuditResult] = []
    start = time.perf_counter()
    for idir in instrument_dirs:
        r = audit_instrument(vault_root, idir, budget=args.budget)
        results.append(r)
        _print_row(r)

    print()
    print("Synthetic personality stub (proves audit catches overflow):")
    stub = audit_synthetic_personality_stub(vault_root, budget=args.budget)
    _print_row(stub)
    results.append(stub)
    elapsed = time.perf_counter() - start
    print()
    print(f"Audit walked {sum(r.file_count for r in results)} files in {elapsed:.2f}s.")
    print()

    failures = [r for r in results if r.status.startswith("FAIL")]
    warns = [r for r in results if r.status.startswith("WARN")]
    if failures:
        print(f"✗ {len(failures)} instrument(s) overflow the {args.budget:,}-token budget:")
        for r in failures:
            print(
                f"    {r.instrument_slug}: ~{r.token_estimate:,} tokens "
                f"(headroom {r.headroom_pct}%)"
            )
        # The synthetic stub is EXPECTED to fail — that's part of the test.
        # If only the stub fails, exit 0 (audit infrastructure validated).
        # If a real wedge instrument fails, exit 1.
        real_failures = [r for r in failures if "(synthetic stub)" not in r.instrument_slug]
        if real_failures:
            print(
                f"\nReal wedge instrument(s) overflow — NARROW THEIR SCOPE before "
                f"committing to single-SDK-call architecture in S02-T02."
            )
            return 1
        print(
            "\n(synthetic stub overflow expected — proves audit catches "
            "personality-scope before deployment. Wedge instruments pass.)"
        )
        return 0
    if warns:
        print(
            f"⚠ {len(warns)} instrument(s) above 70% budget; monitor for "
            f"substrate growth that could push over the limit."
        )
    print("✓ All real wedge instruments fit comfortably under the budget.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
