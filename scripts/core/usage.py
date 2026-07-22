"""Token-usage accounting, keyed by (provider, model).

The honest usage unit is tokens per provider/model — under a Claude
subscription `total_cost_usd` is meaningless, Ollama is local/free, and one
dollar figure conflates non-commensurable billing. Dollars only ever apply to a
provider explicitly registered as pay-per-token (none today). See
`.ytstack/DECISIONS.md` 2026-05-23 and `.ytstack/backlog/token-usage-accounting.md`.

A process-global `LEDGER` accumulates across a run; call sites record into it
(the Ollama client auto-records; Claude sites record from the SDK message
stream). `LEDGER.persist()` merges the run totals into `state/usage.json`,
bucketed `date -> "<provider>:<model>" -> {...}`, under an fcntl lock.
"""

from __future__ import annotations

import atexit
from dataclasses import dataclass
from pathlib import Path

from .errors import swallow
from .paths import STATE_DIR
from .state_store import locked
from .utils import load_json_state, save_json_state, today_iso

PROVIDER_CLAUDE = "claude"
PROVIDER_OLLAMA = "ollama"

USAGE_FILE = STATE_DIR / "usage.json"


def provider_for_model(model: str) -> str:
    """Infer the provider from a model id.

    `claude*` / `anthropic*` -> the Claude SDK (subscription). Everything else
    (gemma*, llama*, ...) runs on the local Ollama server. A real pay-per-token
    provider must be added here explicitly — only then may a dollar rate-card
    enter (DECISIONS 2026-05-23)."""
    m = (model or "").strip().lower()
    if m.startswith(("claude", "anthropic")):
        return PROVIDER_CLAUDE
    return PROVIDER_OLLAMA


def _fmt_k(n: int) -> str:
    return f"{n / 1000:.1f}K" if n >= 1000 else str(int(n))


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, *, input_tokens: int = 0, output_tokens: int = 0, calls: int = 1) -> None:
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)
        self.calls += int(calls or 0)


class UsageLedger:
    """Per-run accumulation of token usage, keyed by (provider, model)."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], Usage] = {}

    def record(
        self,
        *,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        calls: int = 1,
        provider: str | None = None,
    ) -> None:
        """The one method call sites use. `provider` is inferred when omitted."""
        provider = provider or provider_for_model(model)
        self._by_key.setdefault((provider, model), Usage()).add(
            input_tokens=input_tokens, output_tokens=output_tokens, calls=calls,
        )

    def record_ollama(self, model: str, stats: dict) -> None:
        """Record from a native /api/chat response (`prompt_eval_count`/`eval_count`)."""
        s = stats or {}
        self.record(
            model=model, provider=PROVIDER_OLLAMA,
            input_tokens=s.get("prompt_eval_count", 0) or 0,
            output_tokens=s.get("eval_count", 0) or 0,
        )

    def record_openai_usage(self, model: str, usage: dict) -> None:
        """Record from an OpenAI-compat `usage` block (`prompt_tokens`/`completion_tokens`)."""
        u = usage or {}
        self.record(
            model=model, provider=PROVIDER_OLLAMA,
            input_tokens=u.get("prompt_tokens", 0) or 0,
            output_tokens=u.get("completion_tokens", 0) or 0,
        )

    def is_empty(self) -> bool:
        return not self._by_key

    def totals(self) -> dict[tuple[str, str], Usage]:
        return dict(self._by_key)

    def summary_line(self) -> str:
        if self.is_empty():
            return "usage: (none)"
        parts = [
            f"{provider}/{model} {_fmt_k(u.input_tokens)} in / {_fmt_k(u.output_tokens)} out / {u.calls} call(s)"
            for (provider, model), u in sorted(self._by_key.items())
        ]
        return "usage: " + " | ".join(parts)

    def persist(self, path: Path | None = None, *, day: str | None = None) -> None:
        """Merge this run's totals into the per-date usage ledger on disk.

        Bucketed `day -> "<provider>:<model>" -> {input_tokens, output_tokens,
        calls}`. fcntl-locked read-merge-write so parallel compile/flush
        sessions don't clobber. Best-effort observability, never control flow."""
        if self.is_empty():
            return
        path = path or USAGE_FILE
        day = day or today_iso()
        path.parent.mkdir(parents=True, exist_ok=True)
        with locked(path.with_name(path.name + ".lock")):
            data = load_json_state(path, {})
            bucket = data.setdefault(day, {})
            for (provider, model), u in self._by_key.items():
                k = f"{provider}:{model}"
                prev = bucket.get(k, {})
                bucket[k] = {
                    "input_tokens": prev.get("input_tokens", 0) + u.input_tokens,
                    "output_tokens": prev.get("output_tokens", 0) + u.output_tokens,
                    "calls": prev.get("calls", 0) + u.calls,
                }
            save_json_state(path, data)


# Process-global default ledger. Call sites import and record into this.
LEDGER = UsageLedger()


@swallow("usage-ledger exit flush")
def _flush_on_exit() -> None:
    """Best-effort persist of the process-global ledger at exit (no-op if empty).

    Centralizes the run-boundary flush so no entrypoint needs its own persist
    call. Won't fire on SIGKILL/os._exit — acceptable: this is observability.
    Accounting must never break a run — a persist failure is swallowed, logged."""
    LEDGER.persist()


atexit.register(_flush_on_exit)
