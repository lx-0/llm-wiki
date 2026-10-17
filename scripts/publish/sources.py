"""Original files: strict inventory, stable identities and explicit move reconciliation."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5


@dataclass(frozen=True)
class SourceFile:
    path: str
    sha256: str | None
    size: int
    directory: bool = False


@dataclass(frozen=True)
class SourceWrite:
    key: str
    file: SourceFile
    previous: dict
    article_id: str | None


@dataclass
class SourcePlan:
    move_batch: str | None = None
    inventory: list[SourceFile] = field(default_factory=list)
    roots: tuple[str, ...] = ()
    write: list[SourceWrite] = field(default_factory=list)
    archive: list[tuple[str, dict]] = field(default_factory=list)
    unchanged: int = 0


def source_path(path: str) -> str:
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or re.match(r"^[a-z]:", path, re.I)
        or re.search(r"[\x00-\x1f\x7f]|%(?:25)*(?:2e|2f|5c|00)", path, re.I)
        or any(p in ("", ".", "..") for p in path.split("/"))
    ):
        raise ValueError(f"invalid source path: {path!r}")
    return path


def inventory_sources(vault: Path, roots: tuple[str, ...]) -> list[SourceFile]:
    """No silent missing roots, hidden skips or symlink traversal; no bytes retained."""
    result: dict[str, SourceFile] = {}

    def walk_error(error: OSError) -> None:
        raise error

    for root in roots:
        source_path(root)
        base = vault / root
        if any(
            (vault / Path(*Path(root).parts[:i])).is_symlink()
            for i in range(1, len(Path(root).parts) + 1)
        ):
            raise ValueError(f"symlink publish root: {root}")
        if not base.is_dir():
            raise ValueError(f"missing publish root: {root}; retractions disabled")
        for parent, directories, files in os.walk(base, followlinks=False, onerror=walk_error):
            directory = Path(parent)
            for name in directories + files:
                if (directory / name).is_symlink():
                    raise ValueError(
                        f"symlink in publish root: {(directory / name).relative_to(vault)}"
                    )
            if not directories and not files:
                rel = source_path(directory.relative_to(vault).as_posix())
                result[rel] = SourceFile(rel, None, 0, True)
            for name in files:
                path = directory / name
                rel = source_path(path.relative_to(vault).as_posix())
                if not path.is_file():
                    raise ValueError(f"unsupported source file: {rel}")
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                result[rel] = SourceFile(rel, digest, path.stat().st_size)
    return [result[p] for p in sorted(result)]


def source_plan(
    files: list[SourceFile],
    manifest: dict,
    articles: dict[str, str],
    moves: dict[str, str] | None = None,
    changed_articles: set[str] | None = None,
    *,
    roots: tuple[str, ...] | None = None,
) -> SourcePlan:
    moves = moves or {}
    changed_articles = changed_articles or set()
    existing = manifest.get("sources", {})
    by_path = {moves.get(e["path"], e["path"]): (key, e) for key, e in existing.items()}
    article_by_path = {rel: slug for slug, rel in articles.items()}
    plan = SourcePlan(
        move_batch=move_batch_id(moves) if moves else None,
        inventory=files,
        roots=roots or tuple(sorted({f.path.split("/", 1)[0] for f in files})),
    )
    seen: set[str] = set()
    for file in files:
        previous_key, previous = by_path.get(file.path, (None, {}))
        article = article_by_path.get(file.path)
        key = previous_key or (
            f"article-{article}" if article else str(uuid5(NAMESPACE_URL, file.path))
        )
        seen.add(key)
        if (
            previous.get("sha256") == file.sha256
            and previous.get("path") == file.path
            and article not in changed_articles
            and previous.get("directory", False) == file.directory
            and not previous.get("archived", False)
        ):
            plan.unchanged += 1
        else:
            plan.write.append(SourceWrite(key, file, previous, article))
    plan.archive = [
        (key, entry)
        for key, entry in existing.items()
        if key not in seen and not entry.get("archived")
    ]
    return plan


def validate_moves(files: list[SourceFile], manifest: dict, moves: dict[str, str]) -> None:
    live = {f.path for f in files}
    previous = {e["path"] for e in manifest.get("sources", {}).values()} | {
        e["path"] for e in manifest.get("articles", {}).values()
    }
    if len(set(moves.values())) != len(moves):
        raise ValueError("multiple moves target the same path")
    for old, new in moves.items():
        source_path(old)
        source_path(new)
        if (
            old == new
            or (old in live and old not in moves.values())
            or new not in live
            or (old not in previous and new not in previous)
        ):
            raise ValueError(f"unresolved move: {old} -> {new}")
        if old in previous and new in previous and new not in moves:
            raise ValueError(f"occupied move target: {new}")


def move_batch_id(moves: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(moves, sort_keys=True).encode()).hexdigest()


def effective_moves(manifest: dict, moves: dict[str, str]) -> dict[str, str]:
    if move_batch_id(moves) in manifest.get("move_batches", {}):
        return {}
    previous = {e["path"] for e in manifest.get("sources", {}).values()} | {
        e["path"] for e in manifest.get("articles", {}).values()
    }
    expanded = {}
    for old, new in moves.items():
        children = [p for p in previous if p.startswith(old.rstrip("/") + "/")]
        if children:
            expanded.update({p: new.rstrip("/") + p[len(old.rstrip("/")) :] for p in children})
        else:
            expanded[old] = new
    return expanded
