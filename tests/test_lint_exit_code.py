"""Exit-code semantics for lint (scripts/lint.py:_lint_exit_code).

`--structural-only` is the piggyback path: finding content issues is DATA (it
lands in the lint report + the home-screen lint probe), not a task failure, so
it must exit 0 — otherwise the piggyback runner stamps a healthy sweep
`failed:1` and false-alarms the dashboard (the observed lxw symptom). Interactive
full lint keeps exit 1 on errors as a non-zero "issues present" gate.
"""

from __future__ import annotations

import lint


def test_structural_only_exits_zero_even_with_errors():
    assert lint._lint_exit_code(errors=5, structural_only=True) == 0
    assert lint._lint_exit_code(errors=0, structural_only=True) == 0


def test_interactive_full_lint_signals_errors_nonzero():
    assert lint._lint_exit_code(errors=5, structural_only=False) == 1
    assert lint._lint_exit_code(errors=0, structural_only=False) == 0
