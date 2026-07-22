"""core.state_store — the locked/atomic JSON state seam (StateStore arc).

Covers the three layers: flock primitives (locked / try_locked /
acquire_process_lock), the state.json merge-under-lock seam (update_state +
ingested-ledger API), and the StateStore load-once facade the dream stores
ride on. The concurrency tests pin the exact race this arc kills: compile
holding its state copy for a whole multi-minute run while query/lint bump
counters — whole-dict last-writer-wins dropped one side's keys.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import state_store  # noqa: E402
from core.state_store import (  # noqa: E402
    StateStore,
    acquire_process_lock,
    locked,
    try_locked,
)
from core.utils import file_hash, save_json_state  # noqa: E402


# ── flock primitives ─────────────────────────────────────────────────


def test_locked_blocks_second_acquirer(tmp_path: Path) -> None:
    """While `locked` holds the flock, a try-lock on the same file fails;
    after release it succeeds."""
    lock = tmp_path / "x.lock"
    with locked(lock):
        with try_locked(lock) as acquired:
            assert acquired is False
    with try_locked(lock) as acquired:
        assert acquired is True


def test_try_locked_releases_on_exit(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    with try_locked(lock) as first:
        assert first is True
        with try_locked(lock) as second:
            assert second is False
    with try_locked(lock) as again:
        assert again is True


def test_acquire_process_lock_contention_and_release(tmp_path: Path) -> None:
    lock = tmp_path / "proc.lock"
    first = acquire_process_lock(lock)
    assert first is not None
    assert acquire_process_lock(lock) is None
    first.close()
    second = acquire_process_lock(lock)
    assert second is not None
    second.close()


# ── atomic save_json_state ───────────────────────────────────────────


def test_save_json_state_no_tmp_residue_and_default_bytes(tmp_path: Path) -> None:
    """Atomic write leaves no `.tmp` behind, and the default serialization is
    byte-identical to the pre-atomic `json.dumps(indent=2, default=str)`."""
    p = tmp_path / "state.json"
    data = {"b": 1, "a": {"nested": "x"}}
    save_json_state(p, data)
    assert p.read_text(encoding="utf-8") == json.dumps(data, indent=2, default=str)
    assert not list(tmp_path.glob("*.tmp"))


def test_save_json_state_dream_format_knobs(tmp_path: Path) -> None:
    """sort_keys + trailing_newline reproduce dream.py's pre-facade
    serialization byte-for-byte (the stores stay diff-stable on disk)."""
    p = tmp_path / "dream-activation.json"
    data = {"raw/b.md": "2026-07-18", "raw/a.md": "2026-07-17"}
    save_json_state(p, data, sort_keys=True, trailing_newline=True)
    assert p.read_text(encoding="utf-8") == json.dumps(data, sort_keys=True, indent=2) + "\n"


# ── StateStore facade ────────────────────────────────────────────────


def test_statestore_load_is_cached_and_reload_refreshes(tmp_path: Path) -> None:
    p = tmp_path / "hot.json"
    p.write_text(json.dumps({"k": "v1"}), encoding="utf-8")
    store = StateStore(p)
    assert store.load() == {"k": "v1"}
    p.write_text(json.dumps({"k": "v2"}), encoding="utf-8")
    assert store.load() == {"k": "v1"}, "load() must serve the cached snapshot"
    assert store.reload() == {"k": "v2"}


def test_statestore_update_rereads_fresh_and_merges(tmp_path: Path) -> None:
    """An external write between load() and update() survives — update takes a
    FRESH read under the lock, so writers merge key-wise, never clobber."""
    p = tmp_path / "hot.json"
    p.write_text(json.dumps({"mine": 1}), encoding="utf-8")
    store = StateStore(p)
    store.load()  # populate cache
    # Another process lands a key behind the cache's back.
    p.write_text(json.dumps({"mine": 1, "theirs": 2}), encoding="utf-8")
    store.update(lambda d: d.__setitem__("mine", 99))
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert on_disk == {"mine": 99, "theirs": 2}
    assert store.load() == on_disk, "update() must refresh the cache"


def test_statestore_tolerant_corrupt_loads_default(tmp_path: Path) -> None:
    p = tmp_path / "hot.json"
    p.write_text("{not json", encoding="utf-8")
    assert StateStore(p, default={"fresh": True}).load() == {"fresh": True}


def test_statestore_strict_corrupt_raises(tmp_path: Path) -> None:
    p = tmp_path / "money.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        StateStore(p, tolerant=False).load()


def test_store_for_returns_same_instance_per_path(tmp_path: Path) -> None:
    p = tmp_path / "hot.json"
    assert state_store.store_for(p) is state_store.store_for(p)


# ── update_state: the state.json merge-under-lock seam ───────────────


@pytest.fixture
def state_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    sf = tmp_path / "state.json"
    monkeypatch.setattr(state_store, "STATE_FILE", sf, raising=True)
    return sf


def test_update_state_seeds_default_shape(state_file: Path) -> None:
    state = state_store.update_state(lambda s: None)
    assert state["ingested"] == {} and state["query_count"] == 0
    assert json.loads(state_file.read_text(encoding="utf-8"))["total_cost"] == 0.0


def test_update_state_corrupt_raises_not_resets(state_file: Path) -> None:
    """state.json is the one file whose loss costs a recompile — a corrupt
    ledger must fail loudly, never be silently replaced with defaults."""
    state_file.write_text("{torn", encoding="utf-8")
    with pytest.raises(ValueError):
        state_store.update_state(lambda s: None)
    assert state_file.read_text(encoding="utf-8") == "{torn", "file must be untouched"


def test_compile_merge_preserves_concurrent_query_counter(state_file: Path) -> None:
    """THE race this arc kills, deterministic interleaving:

    compile loads state at run start and works for minutes; a query bumps
    query_count meanwhile; compile then persists a file result. Old code
    saved compile's whole stale dict → query_count reset (last-writer-wins).
    Merge-under-lock keeps both writers' keys."""
    save_json_state(state_file, {"ingested": {}, "query_count": 0, "total_cost": 1.0})

    # compile run start: holds its (stale) view for the whole run.
    _compile_view = json.loads(state_file.read_text(encoding="utf-8"))

    # concurrent query lands its counters (query.py's mutator shape).
    def _query_bump(s: dict) -> None:
        s["query_count"] = s.get("query_count", 0) + 1
        s["total_cost"] = round(s.get("total_cost", 0.0) + 0.5, 4)

    state_store.update_state(_query_bump)

    # compile persists one compiled file via its merge (compile.py's shape).
    def _compile_merge(s: dict) -> None:
        s.setdefault("ingested", {})["raw/notes/a.md"] = "abc123"
        s["total_cost"] = round(s.get("total_cost", 0.0) + 0.25, 4)
        s["last_compile"] = "2026-07-18T20:00:00"

    state_store.update_state(_compile_merge)

    final = json.loads(state_file.read_text(encoding="utf-8"))
    assert final["query_count"] == 1, "query's counter was clobbered"
    assert final["ingested"] == {"raw/notes/a.md": "abc123"}, "compile's hash was lost"
    assert final["total_cost"] == 1.75, "cost deltas must accumulate from both writers"


def test_update_state_thread_hammer_loses_no_increment(state_file: Path) -> None:
    """N racing writers × M locked increments each → exactly N*M on disk.
    Without the flock (or with non-atomic writes) increments vanish."""
    save_json_state(state_file, {"query_count": 0})

    def _worker() -> None:
        for _ in range(5):
            state_store.update_state(
                lambda s: s.__setitem__("query_count", s.get("query_count", 0) + 1)
            )

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert json.loads(state_file.read_text(encoding="utf-8"))["query_count"] == 40


def test_compile_persist_outcome_merges_under_lock(
    state_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """compile._persist_outcome (the per-file save site) goes through
    update_state — a query counter written mid-run survives compile's save."""
    import compile as compile_mod

    save_json_state(state_file, {"ingested": {}, "query_count": 7, "total_cost": 0.0})

    state = compile_mod._persist_outcome(
        "raw/notes/x.md", "beef1234", cost_delta=0.5, stamp_compile=True
    )

    on_disk = json.loads(state_file.read_text(encoding="utf-8"))
    assert on_disk["query_count"] == 7
    assert on_disk["ingested"]["raw/notes/x.md"] == "beef1234"
    assert on_disk["total_cost"] == 0.5
    assert "last_compile" in on_disk
    assert state == on_disk


# ── ingested-ledger query API ────────────────────────────────────────


@pytest.fixture
def ledger_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """tmp vault with two raw files + state.json redirected; returns
    (vault_root, fresh_file, stale_file)."""
    raw = tmp_path / "raw" / "notes"
    raw.mkdir(parents=True)
    stale = raw / "stale.md"
    stale.write_text("old content\n", encoding="utf-8")
    fresh = raw / "fresh.md"
    fresh.write_text("new content\n", encoding="utf-8")

    sf = tmp_path / ".wiki" / "state" / "state.json"
    monkeypatch.setattr(state_store, "STATE_FILE", sf, raising=True)
    monkeypatch.setattr(state_store, "ROOT_DIR", tmp_path, raising=True)
    # list_raw_files reads utils' module globals; stub the import in
    # state_store so the ledger walks OUR vault, newest-first order preserved.
    monkeypatch.setattr(
        state_store, "list_raw_files", lambda: [fresh, stale], raising=True
    )
    return tmp_path, fresh, stale


def test_is_ingested_matches_current_hash(ledger_vault) -> None:
    vault, fresh, stale = ledger_vault
    save_json_state(
        state_store.STATE_FILE,
        {"ingested": {"raw/notes/stale.md": file_hash(stale)}},
    )
    assert state_store.is_ingested(stale) is True
    assert state_store.is_ingested(fresh) is False  # no ledger entry
    stale.write_text("changed content\n", encoding="utf-8")
    assert state_store.is_ingested(stale) is False  # hash drifted


def test_is_ingested_tolerates_legacy_dict_values(ledger_vault) -> None:
    """Pre-2026-05 state files stored {hash, compiled_at} dicts — the
    normalization lives ONLY in the ledger API (the drift that killed
    flush's skip branch: a consumer calling .get('hash') on a str)."""
    _vault, _fresh, stale = ledger_vault
    save_json_state(
        state_store.STATE_FILE,
        {"ingested": {"raw/notes/stale.md": {"hash": file_hash(stale), "compiled_at": "x"}}},
    )
    assert state_store.is_ingested(stale) is True


def test_is_ingested_outside_vault_is_false(ledger_vault, tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("x", encoding="utf-8")
    try:
        assert state_store.is_ingested(outside) is False
    finally:
        outside.unlink()


def test_pending_paths_lists_changed_and_new_in_scan_order(ledger_vault) -> None:
    vault, fresh, stale = ledger_vault
    save_json_state(
        state_store.STATE_FILE,
        {"ingested": {"raw/notes/stale.md": file_hash(stale)}},
    )
    # stale matches its ledger hash → only fresh is pending.
    assert state_store.pending_paths() == [fresh]
    # stale's content drifts → both pending, list_raw_files order preserved.
    stale.write_text("drifted\n", encoding="utf-8")
    assert state_store.pending_paths() == [fresh, stale]


def test_compile_select_files_uses_ledger(ledger_vault, monkeypatch) -> None:
    """compile.select_files' changed-set IS pending_paths — no hand-rolled
    hash comparison left in compile."""
    import argparse

    import compile as compile_mod

    vault, fresh, stale = ledger_vault
    save_json_state(
        state_store.STATE_FILE,
        {"ingested": {"raw/notes/stale.md": file_hash(stale)}},
    )
    args = argparse.Namespace(file=None, all=False)
    assert compile_mod.select_files(args) == [fresh]
