"""Collector base — substrate-shaped registration + Protocol + Registry.

A Collector is a substrate-specific module that turns a substrate (mailbox,
calendar, browser history, screenshots, …) into files under `<vault>/raw/`.
Each Collector subclass declares a `SPEC` and implements `is_configured()`
+ `run()`. Decorating with `@register` adds it to the Registry.

The Registry is consumed by:
- `flush.py` to discover piggyback Collectors at runtime (no hardcoded list)
- `wiki collect <name>` CLI to dispatch operator-invoked runs
- `wiki collect --list` to show what's available
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable


# ── Spec ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CollectorSpec:
    """Static declaration on each Collector subclass.

    Read by Registry queries, drives piggyback discovery + CLI dispatch.
    """

    name: str
    """Collector identity. Becomes the CLI argument: `wiki collect email`."""

    output_subfolder: str
    """Path under `<vault>/raw/` where this collector writes."""

    piggyback_default: bool
    """True if `flush.py` should auto-spawn this collector after compile.
    False for collectors that are operator-invoked only (e.g. ingest-html).
    """

    piggyback_cooldown_hours: int = 24
    """Default cooldown. CONFIG.piggybacks.<name>.cooldown_hours overrides."""

    supports_incremental: bool = False
    """True if `run(incremental=True)` is meaningful (delta vs. full sweep)."""

    supports_account_loop: bool = False
    """True for substrates with N accounts (email, calendar). False for
    singletons (browser, screenshots, tabs).
    """


# ── Result type ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class RunResult:
    """What `Collector.run()` returns — metrics for logging + state updates."""

    files_written: tuple[Path, ...] = ()
    files_skipped: int = 0
    state_keys_touched: tuple[str, ...] = ()
    message: str = ""  # one-line operator-facing summary
    errors: tuple[str, ...] = ()  # per-account scan failures (e.g. MailboxReadError)


# ── Collector Protocol ───────────────────────────────────────────────

@runtime_checkable
class Collector(Protocol):
    """Each collector is a substrate-specific reader → raw/ writer."""

    SPEC: ClassVar[CollectorSpec]

    def is_configured(self) -> bool:
        """Graceful-agnostic gate.

        Returns False when CONFIG lacks what this collector needs (e.g.
        EmailCollector with zero accounts whose Reader-kind resolves;
        BrowserCollector with both `firefox_profile` and Chrome paths
        empty). Empty config → empty work, no error.
        """
        ...

    def run(self, *, dry_run: bool = False, incremental: bool = False) -> RunResult:
        """Execute one scan cycle.

        - dry_run=True: log what would happen but don't write to disk.
        - incremental=True: only scan deltas since last run (when
          supports_incremental=True; otherwise a no-op flag).

        Returns metrics (files written, skipped, state keys touched).
        """
        ...


# ── Registry ─────────────────────────────────────────────────────────

_COLLECTORS: dict[str, type[Collector]] = {}


def register(cls: type[Collector]) -> type[Collector]:
    """Decorator. Auto-registers a Collector subclass in the Registry.

    Usage:

        @register
        class EmailCollector:
            SPEC = CollectorSpec(name="email", ...)
            def is_configured(self): ...
            def run(self, *, dry_run=False, incremental=False): ...

    Importing the module that defines the class triggers registration.
    `collectors/__init__.py` imports each submodule for this reason.
    """
    if not hasattr(cls, "SPEC"):
        raise TypeError(
            f"@register: {cls.__name__} must define a SPEC class attribute "
            "(CollectorSpec instance)."
        )
    spec = cls.SPEC  # type: ignore[attr-defined]
    if spec.name in _COLLECTORS:
        existing = _COLLECTORS[spec.name]
        # A Collector module run as `__main__` gets re-imported as
        # `collectors.<name>` by the package __init__'s auto-import — same
        # SPEC.name appears twice with classes of the same qualname. Treat
        # same-class re-registration as a no-op; only flag genuine collisions.
        if existing.__qualname__ == cls.__qualname__:
            return cls
        raise ValueError(
            f"@register: collector name {spec.name!r} already registered "
            f"by {existing.__name__}; would overwrite with {cls.__name__}."
        )
    _COLLECTORS[spec.name] = cls
    return cls


def all_collectors() -> list[Collector]:
    """Yield instantiated collectors (one per registered class).

    Used by `wiki collect --list` and `wiki collect <name>` dispatch.
    """
    return [cls() for cls in _COLLECTORS.values()]


def piggyback_collectors() -> list[Collector]:
    """Yield only collectors that should auto-spawn from flush.py.

    Filters by `SPEC.piggyback_default and is_configured()`. Collectors
    whose CONFIG isn't populated are silently skipped (graceful agnostic).
    """
    return [
        c
        for c in all_collectors()
        if c.SPEC.piggyback_default and c.is_configured()
    ]


def get_collector(name: str) -> Collector | None:
    """Resolve a collector by SPEC.name. Returns None if not registered."""
    cls = _COLLECTORS.get(name)
    return cls() if cls is not None else None
