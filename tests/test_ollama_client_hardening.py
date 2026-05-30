"""ollama_client connection hardening — TCP keepalive + explicit phase
timeouts so a sleeping/down LAN GPU can't hang a call forever (review-wiki
19h half-open-socket incident 2026-05-30)."""

from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def test_keepalive_socket_options_enable_keepalive():
    from core import ollama_client
    opts = ollama_client._keepalive_socket_options()
    # SO_KEEPALIVE must be on — without it a half-open ESTABLISHED socket
    # never gets probed and recv() blocks indefinitely.
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in opts
    # Every entry is a well-formed (level, optname, value) int triple.
    assert all(len(o) == 3 and all(isinstance(x, int) for x in o) for o in opts)
    # The idle-before-probe option is present on this platform (macOS
    # TCP_KEEPALIVE / Linux TCP_KEEPIDLE), so dead-peer detection is bounded.
    assert len(opts) >= 2


def test_timeout_splits_connect_from_read(monkeypatch):
    from core import ollama_client
    monkeypatch.setattr(ollama_client.CONFIG.limits, "ollama_connect_timeout_s", 7)
    t = ollama_client._timeout(33.0)
    # A single httpx float would make connect == read; we want a short connect
    # cap (config) independent of the caller's read budget.
    assert t.connect == 7.0
    assert t.read == 33.0
    assert t.write == ollama_client._WRITE_TIMEOUT_S
    assert t.pool == ollama_client._POOL_TIMEOUT_S


def test_unreachable_host_fails_fast_not_hangs(monkeypatch):
    """The core anti-hang property: a call to a dead endpoint returns quickly
    instead of blocking (what the old single-float `timeout=300` failed to do
    against a half-open socket). TEST-NET-1 (192.0.2.0/24) is reserved and
    unroutable, so the connect is dropped → connect-timeout fires."""
    from core import ollama_client
    monkeypatch.setattr(ollama_client.CONFIG.models, "ollama_url", "http://192.0.2.1:11434")
    monkeypatch.setattr(ollama_client.CONFIG.limits, "ollama_connect_timeout_s", 2)
    start = time.time()
    ok = ollama_client.is_reachable(timeout=2.0)
    elapsed = time.time() - start
    assert ok is False
    assert elapsed < 8, f"is_reachable hung {elapsed:.1f}s — connect timeout ineffective"
