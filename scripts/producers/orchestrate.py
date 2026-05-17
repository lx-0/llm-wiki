"""Producer orchestrator — gate evaluation + dispatch.

Single entry point used by compile.py's post-pass loop and by `wiki produce`
CLI dispatch. Evaluates the two declarative gates on each Producer's Spec
(``enabled_config_key`` + ``source_glob_config_key``) and short-circuits to
``skipped`` when either fails; otherwise delegates to ``producer.run(source)``
and returns its ProducerResult verbatim.

Failure handling lives in the Producer wrapper (S02), not here. The wrappers
catch exceptions from their legacy free-function delegates and return a
``failed`` ProducerResult; this orchestrator does NOT add a second
try/except — a single failure path keeps result-aggregation honest.

Gates use dotted attribute paths against CONFIG (e.g. ``"features.extract_takes"``
resolves to ``CONFIG.features.extract_takes``). A missing attribute is treated
as falsy (graceful-agnostic, matches the Collector pattern).

Source-glob matching is against the source path **relative to ROOT_DIR**
(the vault root), using fnmatch semantics. Empty allowlist = nothing
matches (mirrors today's takes_producer behavior).
"""

from __future__ import annotations

import fnmatch
import logging
from pathlib import Path

from core.config import CONFIG
from core.paths import ROOT_DIR

from .base import Producer, ProducerResult

log = logging.getLogger(__name__)


def _resolve_dotted(root: object, dotted: str) -> object | None:
    """Walk ``root.a.b.c`` from ``dotted="a.b.c"``. None on any miss."""
    obj: object | None = root
    for part in dotted.split("."):
        if obj is None:
            return None
        obj = getattr(obj, part, None)
    return obj


def _source_relative_to_root(source: Path) -> str:
    """Source path relative to ROOT_DIR as a POSIX string, for fnmatch.

    Falls back to the source's name when the path can't be made relative
    (e.g. test fixtures outside the vault tree).
    """
    try:
        return source.resolve().relative_to(ROOT_DIR.resolve()).as_posix()
    except (ValueError, OSError):
        return source.name


async def evaluate_and_run(producer: Producer, source: Path) -> ProducerResult:
    """Gate-evaluate ``producer.SPEC`` against ``source`` + CONFIG, then run.

    Returns a ProducerResult with status:
    - ``skipped`` — a gate rejected this source. ``reason`` names which gate.
    - whatever the producer's ``run()`` returned (``ok`` / ``failed``).
    """
    spec = producer.SPEC

    if spec.enabled_config_key is not None:
        flag = _resolve_dotted(CONFIG, spec.enabled_config_key)
        if not flag:
            return ProducerResult(
                producer=spec.name,
                status="skipped",
                reason=f"disabled (CONFIG.{spec.enabled_config_key} = {flag!r})",
            )

    if spec.source_glob_config_key is not None:
        globs = _resolve_dotted(CONFIG, spec.source_glob_config_key) or []
        rel = _source_relative_to_root(source)
        if not any(fnmatch.fnmatch(rel, pat) for pat in globs):
            return ProducerResult(
                producer=spec.name,
                status="skipped",
                reason=(
                    f"source {rel!r} did not match any glob in "
                    f"CONFIG.{spec.source_glob_config_key} (={list(globs)})"
                ),
            )

    return await producer.run(source)
