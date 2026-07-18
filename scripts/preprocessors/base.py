"""Preprocessor base — normalize-staged-material registration + Protocol + Registry.

Mirrors `scripts/collectors/base.py` + `scripts/producers/base.py`. A Preprocessor
normalizes material that is *already inside the vault* — the `inbox/` drop-zone,
the Obsidian Web Clipper `Clippings/` folder, a single HTML file/URL — into the
`raw/**` shape the compile loop reads. It sits *before* compile, whereas a
Producer runs *after* it.

Distinct from a Collector: a Collector reads a Substrate from *outside* the vault
(mailbox, calendar, browser) and writes `raw/`. A Preprocessor never touches an
external Substrate — it only reshapes what a human or another tool already staged
locally. Preprocessors are singletons (no `accounts.<id>` fan-out), so this seam
is lighter than the Collector one: no Reader/Filter sub-split, no account loop.

The Registry is consumed by:
- `wiki preprocess <name>` CLI (`preprocessors/cli.py`) to dispatch a run
- `wiki preprocess --list` to show what is available
- `compile.py`'s pre-compile step (today only the `clippings` sweep is wired in;
  the Registry lets future pre-steps discover the rest without a hardcoded list)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable


# ── Spec ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PreprocessorSpec:
    """Static declaration on each Preprocessor class.

    Read by Registry queries + CLI dispatch. No piggyback/cooldown fields
    (unlike CollectorSpec) — preprocessors run synchronously as an explicit
    step, never as a background piggyback.
    """

    name: str
    """Preprocessor identity. Becomes the CLI argument: `wiki preprocess html`."""

    output_subfolder: str
    """Path under `<vault>/raw/` where this preprocessor writes normalized files."""

    takes_source: bool = False
    """True when `run()` requires a `source` argument (a path or URL) — the
    `html` preprocessor converts one named source. False for folder-sweep
    singletons (`inbox`, `clippings`) that scan a fixed staging directory and
    ignore `source`.
    """


# ── Result type ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class PreprocessResult:
    """What `Preprocessor.run()` returns — metrics for logging + CLI output."""

    files_written: tuple[Path, ...] = ()
    files_skipped: int = 0
    message: str = ""  # one-line operator-facing summary
    errors: tuple[str, ...] = ()  # non-fatal problems (e.g. a bad source)


# ── Preprocessor Protocol ────────────────────────────────────────────

@runtime_checkable
class Preprocessor(Protocol):
    """Each preprocessor reshapes already-staged local material into `raw/`."""

    SPEC: ClassVar[PreprocessorSpec]

    def run(self, *, dry_run: bool = False, source: str | None = None) -> PreprocessResult:
        """Execute one normalization pass.

        - dry_run=True: log/announce what would happen but write nothing.
        - source: required when `SPEC.takes_source` is True (the `html`
          preprocessor's file/URL); ignored by folder-sweep singletons.

        Returns metrics (files written, skipped, one-line message, errors).
        """
        ...


# ── Registry ─────────────────────────────────────────────────────────

_PREPROCESSORS: dict[str, type[Preprocessor]] = {}


def register(cls: type[Preprocessor]) -> type[Preprocessor]:
    """Decorator. Auto-registers a Preprocessor class in the Registry.

    Usage::

        @register
        class HtmlPreprocessor:
            SPEC = PreprocessorSpec(name="html", ...)
            def run(self, *, dry_run=False, source=None): ...

    Importing the module that defines the class triggers registration.
    `preprocessors/__init__.py` imports each submodule for this reason.

    Same-class re-registration is a no-op (handles a module double-load);
    a different class claiming the same SPEC.name is an error.
    """
    if not hasattr(cls, "SPEC"):
        raise TypeError(
            f"@register: {cls.__name__} must define a SPEC class attribute "
            "(PreprocessorSpec instance)."
        )
    spec = cls.SPEC  # type: ignore[attr-defined]
    if spec.name in _PREPROCESSORS:
        existing = _PREPROCESSORS[spec.name]
        if existing.__qualname__ == cls.__qualname__:
            return cls
        raise ValueError(
            f"@register: preprocessor name {spec.name!r} already registered "
            f"by {existing.__name__}; would overwrite with {cls.__name__}."
        )
    _PREPROCESSORS[spec.name] = cls
    return cls


def all_preprocessors() -> list[Preprocessor]:
    """Yield instantiated preprocessors (one per registered class).

    Used by `wiki preprocess --list` and `wiki preprocess <name>` dispatch.
    """
    return [cls() for cls in _PREPROCESSORS.values()]


def get_preprocessor(name: str) -> Preprocessor | None:
    """Resolve a preprocessor by SPEC.name. Returns None if not registered."""
    cls = _PREPROCESSORS.get(name)
    return cls() if cls is not None else None
