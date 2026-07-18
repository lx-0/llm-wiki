"""Preprocessors — normalize already-staged local material into `raw/**`.

Importing this package triggers `@register` for every Preprocessor subclass in
the submodules listed below. New Preprocessor? Add a submodule and import it
here. See CONTEXT.md for the Preprocessor / PreprocessorSpec / PreprocessResult
vocabulary and how the seam differs from Collector (outside-vault) and Producer
(post-compile).
"""

from __future__ import annotations

from preprocessors.base import (  # noqa: F401  re-export the public API
    PreprocessResult,
    Preprocessor,
    PreprocessorSpec,
    all_preprocessors,
    get_preprocessor,
    register,
)

# Trigger @register side-effects. `html_ingest` is imported before `inbox`
# because `inbox` imports `ingest` from it at module load (the in-process HTML
# path). Module is `html_ingest`, not `html`, to avoid shadowing the stdlib
# `html` package — see the note in html_ingest.py.
from preprocessors import html_ingest as _html_ingest  # noqa: F401,E402
from preprocessors import inbox as _inbox  # noqa: F401,E402
from preprocessors import clippings as _clippings  # noqa: F401,E402

__all__ = [
    "PreprocessResult",
    "Preprocessor",
    "PreprocessorSpec",
    "all_preprocessors",
    "get_preprocessor",
    "register",
]
