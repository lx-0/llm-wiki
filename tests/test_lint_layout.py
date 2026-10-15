"""M033-S04-T07 — `lint` is the facade over `lint_model` (the corpus model),
`lint_checks` (the structural checks) and `lint_schema` (the frontmatter-schema
checks).

The facade re-exports what `dashboard/lint_results.py`, `reconcile.py` and the tests
reach as `lint.X`, but never a name a test patches: a patch on the facade would change
an attribute no check reads. `_domain_tags` is read by two structural checks, so its
patch belongs on `lint_checks` — on the facade it raises.
"""

from __future__ import annotations

import pytest

import lint


def test_the_facade_binds_no_patched_name() -> None:
    assert "_domain_tags" not in vars(lint)


def test_a_stale_facade_patch_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(AttributeError):
        monkeypatch.setattr(lint, "_domain_tags", lambda: ())


def test_the_facade_keeps_the_consumer_api() -> None:
    for name in (
        "Issue",
        "issue",
        "Article",
        "LintContext",
        "build_context",
        "CHECKS",
        "FOLDER_TO_TYPE",
        "SPARSE_THRESHOLD",
        "generate_report",
        "check_contradictions",
        "_lint_exit_code",
    ):
        assert hasattr(lint, name), name
    for _label, check in lint.CHECKS:
        assert getattr(lint, check.__name__) is check
