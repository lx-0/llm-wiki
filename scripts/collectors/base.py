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

import logging
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Generic, Protocol, TypeVar, runtime_checkable

_log = logging.getLogger(__name__)


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


# ── Account-loop harness ─────────────────────────────────────────────
# One home for the run() orchestration skeleton that gmeet / jamie /
# calendar / health each hand-replicated: a kind-discriminated account
# resolver, a --account filter, a failure-isolating per-account loop with
# message aggregation, and a typed watermark helper. State-file SHAPES stay
# decision-locked per substrate — the harness never normalises them on disk;
# it owns failure isolation + aggregation + the save-if-touched signal only.

A = TypeVar("A")
P = TypeVar("P")


def _account_id_attr(acct: Any) -> str:
    """Default id extractor — the per-account dataclasses all carry it."""
    return acct.account_id


def resolve_accounts(
    accounts: dict[str, Any],
    kind: str,
    build: Callable[[str, dict[str, Any]], A],
    *,
    block_key: str | Sequence[str],
) -> list[A]:
    """Resolve per-account config for a kind-discriminated sub-block.

    ``accounts`` is the ``CONFIG.personal.accounts`` mapping (passed in so the
    harness stays CONFIG-free and each collector's own CONFIG reference is the
    one that resolves — tests patch the collector module's CONFIG). For every
    account body that is a dict whose ``block_key`` sub-block is itself a dict
    with ``kind == <kind>``, calls ``build(account_id, block)`` and collects
    the result. ``block_key`` is a single key (``"gmeet"``) or a sequence for a
    nested block (``("health", "oura")``). Unknown kinds / missing blocks are
    silently skipped — the graceful-agnostic contract (empty config -> empty
    work, no error).

    This is the one home for the resolver skeleton gmeet / jamie / calendar /
    health each re-typed (the ``resolve_reader`` / ``resolve_filter`` dispatch
    on ``kind``).
    """
    keys: tuple[str, ...] = (block_key,) if isinstance(block_key, str) else tuple(block_key)
    out: list[A] = []
    for account_id, body in (accounts or {}).items():
        if not isinstance(body, dict):
            continue
        block: Any = body
        for key in keys:
            if not isinstance(block, dict):
                block = None
                break
            block = block.get(key)
        if not isinstance(block, dict) or block.get("kind") != kind:
            continue
        out.append(build(account_id, block))
    return out


def filter_accounts(
    accounts: Sequence[A],
    account_id: str | None,
    *,
    id_of: Callable[[A], str] = _account_id_attr,
) -> list[A]:
    """Restrict a resolved account list to a single ``--account`` id.

    ``account_id=None`` (no ``--account`` flag) returns every account. An id
    that matches nothing returns ``[]`` — the caller reports the miss.
    ``id_of`` extracts the comparable id (email keeps ``(id, body, reader)``
    tuples; the others carry a ``.account_id`` dataclass field). This is the
    seam that makes ``wiki collect <name> --account <id>`` land once for every
    account substrate instead of per-collector.
    """
    if account_id is None:
        return list(accounts)
    return [a for a in accounts if id_of(a) == account_id]


def migrate_flat_state(
    state: dict,
    watermark_key: str,
    *,
    account_id: str = "default",
    log: logging.Logger,
    name: str,
) -> None:
    """Fold a pre-multi-tenant flat watermark into a per-account bucket.

    gmeet + jamie both shipped a flat ``{<watermark_key>: <iso>}`` state
    before the multi-tenant lift; this migrates it into
    ``state["default"][<watermark_key>]`` so a clean lift never loses the
    watermark. No-op once any per-account bucket carrying ``watermark_key``
    exists. Mutates ``state`` in place. The one home for the block gmeet /
    jamie carried verbatim-identical.
    """
    if watermark_key in state and not any(
        isinstance(v, dict) and watermark_key in v for v in state.values()
    ):
        legacy = state.pop(watermark_key)
        state.setdefault(account_id, {})[watermark_key] = legacy
        log.info("%s: migrated legacy flat state -> state[%r]", name, account_id)


@dataclass
class Watermark:
    """Monotonic high-water mark with advance-on-success / hold-on-failure.

    The one home for the watermark discipline gmeet / jamie / health each
    re-typed (``highest is None or str(x) > str(highest)`` — twice in one
    gmeet method). Seed with the stored value, feed candidates through
    ``observe`` (None ignored; string-wise compare — ISO-8601 sorts
    lexically), then persist ``value`` iff ``advanced``. Hold-on-failure is
    structural: a collector that returns early on a scan failure never
    reaches the ``if wm.advanced`` write, so the mark stays put.
    """

    _initial: str | None
    _current: str | None

    @classmethod
    def seed(cls, value: str | None) -> Watermark:
        return cls(_initial=value, _current=value)

    def observe(self, candidate: str | None) -> None:
        if candidate and (self._current is None or str(candidate) > str(self._current)):
            self._current = str(candidate)

    @property
    def value(self) -> str | None:
        return self._current

    @property
    def advanced(self) -> bool:
        return self._current is not None and self._current != self._initial


@dataclass
class AccountLoopOutcome(Generic[P]):
    """Aggregate of one account-loop run — payload-generic.

    ``payloads`` are the per-account scan results (files+skipped for
    gmeet/jamie/health, event-blocks+concepts for calendar — the harness
    never inspects them). ``messages`` are the ``"<label>: <msg>"`` /
    ``"<label>: ERROR ..."`` lines the collector joins with `` · ``.
    ``any_state_touched`` ORs each scan's flag so the collector saves state
    once iff something advanced. ``error_ids`` lists accounts that raised.
    """

    payloads: list[P]
    messages: list[str]
    any_state_touched: bool
    error_ids: list[str]


def run_account_loop(
    accounts: Sequence[A],
    scan_one: Callable[[A], tuple[str, P, bool]],
    *,
    log: logging.Logger,
    name: str,
    id_of: Callable[[A], str] = _account_id_attr,
    describe: Callable[[A], str] | None = None,
) -> AccountLoopOutcome[P]:
    """Run ``scan_one`` per account with failure isolation + aggregation.

    ``scan_one(acct)`` returns ``(message, payload, state_touched)`` — its own
    per-account body, unchanged (bind the collector's extra kwargs with
    ``functools.partial``). The harness owns the cross-account concerns the
    five collectors each re-typed: a per-account try/except so one bad account
    never aborts the rest (the exception is logged under ``<name>[<id>]``,
    surfaced as ``"<label>: ERROR <type>: <e>"``, and recorded in
    ``error_ids``), and the `` · ``-joinable message list.

    ``describe`` maps an account to its message label (default = its id);
    health passes ``lambda a: f"{a.account_id} oura"`` to keep the per-source
    sub-label. State load / migrate / save-if-touched stay in the collector
    (state-file shapes are decision-locked per substrate — email keeps
    ``{"accounts": {...}}``, the rest keep flat ``{id: {...}}`` — and must not
    be normalised on disk).
    """
    label_of = describe or id_of
    payloads: list[P] = []
    messages: list[str] = []
    error_ids: list[str] = []
    any_state_touched = False
    for acct in accounts:
        try:
            message, payload, state_touched = scan_one(acct)
        except Exception as exc:  # noqa: BLE001 — collector boundary, isolate one account
            log.exception("%s[%s]: unexpected", name, id_of(acct))
            messages.append(f"{label_of(acct)}: ERROR {type(exc).__name__}: {exc}")
            error_ids.append(id_of(acct))
            continue
        payloads.append(payload)
        messages.append(f"{label_of(acct)}: {message}")
        any_state_touched = any_state_touched or state_touched
    return AccountLoopOutcome(
        payloads=payloads,
        messages=messages,
        any_state_touched=any_state_touched,
        error_ids=error_ids,
    )


# ── Inbox-intake harness (M022 two-zone folder-watch) ────────────────
# One home for the folder-watch skeleton voice / capture / pictures each
# replicated: scan a watched inbox for accepted suffixes, transform per file
# (collector-specific — kept in the collector), two-zone archive the source
# as the dedup mechanism, append a daily-rollup line as a swallowed
# side-effect. The two load-bearing invariants — archive-move-is-the-dedup,
# rollup-never-breaks-the-write — live here instead of in three parallel
# comment blocks.


def scan_inbox(inbox: Path, suffixes: Sequence[str]) -> list[Path]:
    """List ingestible files in a watched inbox, oldest first.

    Skips sub-directories, dot-files, and any suffix outside ``suffixes``
    (compared lower-case). Sorted by mtime ascending so a batch reads
    chronologically. A missing inbox is not an error -> ``[]``. The one home
    for the ``_scan_inbox`` skeleton voice / capture / pictures replicated.
    """
    if not inbox.exists():
        return []
    accepted = tuple(s.lower() for s in suffixes)
    items = [
        p
        for p in inbox.iterdir()
        if not p.is_dir() and not p.name.startswith(".") and p.suffix.lower() in accepted
    ]
    return sorted(items, key=lambda p: p.stat().st_mtime)


def archive_to_zone(src: Path, zone: Path) -> Path:
    """Move a processed source into the vault audit zone (M022 two-zone).

    The archive-move IS the per-source dedup mechanism, so the collision
    policy never clobbers an earlier archive: on a same-name hit (a re-run
    after a manual restore) the copy is suffixed with the source mtime.
    Returns the final destination path. Raises ``OSError`` on move failure —
    callers surface it (a swallowed archive failure would silently re-ingest
    the source on the next run).
    """
    zone.mkdir(parents=True, exist_ok=True)
    dest = zone / src.name
    if dest.exists():
        dest = zone / f"{src.stem}-{int(src.stat().st_mtime)}{src.suffix}"
    shutil.move(str(src), str(dest))
    return dest


def append_rollup(
    date_iso: str,
    source: str,
    line: str,
    *,
    source_ref: str | None = None,
    log: logging.Logger | None = None,
    context: str = "",
) -> None:
    """Append a one-liner to ``daily/<date>/<source>.md``, swallowing failures.

    The rollup is a side-effect — a failure must never break the collector's
    primary write. ``source_ref`` routes through
    ``daily_capture.append_with_source`` (machine-readable provenance in the
    ``sources:`` frontmatter, no dead in-body ``[[raw/…]]`` link); without it,
    a plain ``daily_capture.append``. The one home for the swallowed-failure
    rollup append voice / capture / pictures each re-typed.
    """
    from core import daily_capture

    try:
        if source_ref is not None:
            daily_capture.append_with_source(date_iso, source, line, source_ref)
        else:
            daily_capture.append(date_iso, source, line)
    except Exception:  # noqa: BLE001 — rollup is a side-effect, never fatal
        detail = f" for {context}" if context else ""
        (log or _log).exception("daily-rollup append failed%s", detail)
