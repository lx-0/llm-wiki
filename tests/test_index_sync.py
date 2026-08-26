"""Deterministic index sync (M031-S02).

Root cause of the index drift (561 missing / 362 duplicate rows on lxw):
index maintenance was an LLM prompt step ("add or update the table row")
while the same prompt FORBIDS reading index.md in full — the agent can never
upsert, so it appends or forgets. The fix moves the bookkeeping to a
deterministic post-compile pass; the prompt step is removed.
"""
from __future__ import annotations

from pathlib import Path

from core.index_sync import sync_index

HEADER = (
    "# Knowledge Base Index\n"
    "\n"
    "> **Naming note:** prose above the table must survive byte-for-byte.\n"
    "\n"
    "| Article | Summary | Compiled From | Updated |\n"
    "|---------|---------|---------------|---------|\n"
)


def _vault(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    k = vault / "knowledge"
    for rel, body in {
        "concepts/foo.md": "---\nsources:\n  - raw/a.md\n---\n\n# Foo\n\nFoo erklärt alles.\n",
        "concepts/bar.md": "# Bar\n\nBar | with pipe.\nSecond line.\n",
        "people/alex.md": "# Alex\n\nOperator.\n",
    }.items():
        p = k / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return vault, k


def _write_index(k: Path, rows: str) -> Path:
    p = k / "index.md"
    p.write_text(HEADER + rows, encoding="utf-8")
    return p


def test_dedupes_keeps_last_drops_dangling_backfills_missing(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    idx = _write_index(
        k,
        "| [[concepts/foo]] | OLD summary. | raw/a.md | 2026-05-01 |\n"
        "| [[does-not-exist]] | junk row | x | 2026-05-01 |\n"
        "| [[concepts/foo]] | NEW summary. | raw/a.md | 2026-08-01 |\n"
        "| [[people/alex]] | Der Operator. | daily/x.md | 2026-06-01 |\n",
    )
    stats = sync_index(k, vault, today="2026-08-26")
    text = idx.read_text(encoding="utf-8")

    assert text.startswith(HEADER)  # prose + header survive byte-for-byte
    assert text.count("[[concepts/foo]]") == 1
    assert "NEW summary." in text and "OLD summary." not in text  # last wins
    assert "does-not-exist" not in text  # dangling dropped
    assert "| [[people/alex]] | Der Operator. |" in text  # kept verbatim
    # concepts/bar.md was missing → appended with first-paragraph summary,
    # pipe escaped, joined lines, today's date, frontmatter-less source dash
    assert "| [[concepts/bar]] | Bar \\| with pipe. Second line. | — | 2026-08-26 |" in text
    assert stats == {
        "rows_before": 4, "kept": 2, "deduped": 1,
        "dropped_dangling": 1, "appended": 1, "changed": True,
    }


def test_backfill_uses_frontmatter_source(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    _write_index(k, "| [[concepts/bar]] | b | — | 2026-08-01 |\n"
                    "| [[people/alex]] | a | — | 2026-08-01 |\n")
    sync_index(k, vault, today="2026-08-26")
    text = (k / "index.md").read_text(encoding="utf-8")
    assert "| [[concepts/foo]] | Foo erklärt alles. | raw/a.md | 2026-08-26 |" in text


def test_idempotent_second_run_writes_nothing(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    _write_index(k, "| [[concepts/foo]] | s | raw/a.md | 2026-08-01 |\n")
    sync_index(k, vault, today="2026-08-26")
    mtime = (k / "index.md").stat().st_mtime_ns
    stats = sync_index(k, vault, today="2026-08-26")
    assert stats["changed"] is False
    assert (k / "index.md").stat().st_mtime_ns == mtime


def test_row_for_deleted_article_is_dropped(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    _write_index(
        k,
        "| [[concepts/foo]] | s | raw/a.md | 2026-08-01 |\n"
        "| [[concepts/gone]] | war mal | raw/b.md | 2026-08-01 |\n"
        "| [[concepts/bar]] | b | — | 2026-08-01 |\n"
        "| [[people/alex]] | a | — | 2026-08-01 |\n",
    )
    stats = sync_index(k, vault, today="2026-08-26")
    assert "concepts/gone" not in (k / "index.md").read_text(encoding="utf-8")
    assert stats["dropped_dangling"] == 1


def test_escaped_pipe_alias_rows_survive(tmp_path: Path) -> None:
    vault, k = _vault(tmp_path)
    _write_index(
        k,
        "| [[concepts/foo\\|Foo!]] | s | raw/a.md | 2026-08-01 |\n"
        "| [[concepts/bar]] | b | — | 2026-08-01 |\n"
        "| [[people/alex]] | a | — | 2026-08-01 |\n",
    )
    sync_index(k, vault, today="2026-08-26")
    assert "| [[concepts/foo\\|Foo!]] | s |" in (k / "index.md").read_text(encoding="utf-8")
