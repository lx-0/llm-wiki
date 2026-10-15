"""Email / workflow optimisation suggestions: the compile-time producer (`producer.py`),
the review-and-execute CLI (`cli.py`), the IMAP and mail-filter backends (`backends/`)."""

from __future__ import annotations

from pathlib import Path

_SUGGESTION_TYPE = "type: optimization-suggestion"


def suggestion_files(directory: Path) -> list[Path]:
    """Every suggestion file in ``directory``, sorted by name.

    A suggestion is a fenced YAML document. The prompt asks for ``.yaml``, and the agent
    has also written ``.yml`` and ``.md`` — seven live ``.md`` suggestions with pending
    actions that no reader saw (2026-10-15). A ``.md`` counts only when it is a
    suggestion: the vault's generic extension also fits a stray note, which the CLI's
    strict parse would choke on."""
    if not directory.is_dir():
        return []
    files: list[Path] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        if path.suffix in (".yaml", ".yml"):
            files.append(path)
        elif path.suffix == ".md":
            head = path.read_text(encoding="utf-8", errors="replace")[:500]
            if _SUGGESTION_TYPE in head:
                files.append(path)
    return files
