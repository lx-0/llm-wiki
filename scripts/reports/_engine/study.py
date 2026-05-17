"""Study manifest schema + state + run-directory atomic writes.

A *Study* is a manifest declaring which instruments at which versions
to score on what schedule. Studies are the parallelism unit:
fork-from another study, edit its manifest, and the two run
independently with their own state + run history.

Manifest layout:

    reports/studies/<study_id>/
        manifest.yaml      # schema below
        state.yaml         # last_run_at + run_count (engine-managed)
        runs/<UTC-iso>/    # one timestamped dir per run
            instruments/<slug>.md   # per-instrument report (S02-T04 shape)
            _summary.md             # deterministic aggregate (S04)
            _analysis.md            # analyst Pass-1 output (S05)
            charts/                 # PNGs (S04)

State location: STATE_DIR (`.wiki/state/`) holds the per-study flock
(`study-<id>.lock`) so concurrent `wiki study run <id>` invocations
don't double-score. Per-study `state.yaml` (last_run_at) lives next
to the manifest — operator-visible and version-controllable.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import yaml  # noqa: E402

import fcntl  # noqa: E402

from scripts.core.paths import STATE_DIR  # noqa: E402


# Slug rules: lowercase letters + digits + hyphen, 3..64 chars, no
# leading/trailing hyphen. Matches the convention used elsewhere in
# the engine (collector ids, instrument slugs).
_SLUG_OK_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-")


SUPPORTED_SCHEDULES: tuple[str, ...] = ("manual", "weekly", "monthly", "quarterly")

# Mapping schedule → cooldown in days. `manual` returns None (never
# auto-due). flush.py piggyback checks `is_due(now)` to decide whether
# to dispatch a scheduled study run.
SCHEDULE_COOLDOWN_DAYS: dict[str, int | None] = {
    "manual": None,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 90,
}


@dataclass(frozen=True)
class InstrumentRef:
    """One row in `manifest.instruments` — which instrument + version + source."""

    slug: str
    version: str
    source: str = "inferred"      # inferred | form | both
    alias: str | None = None      # disambiguates two refs to the same slug

    @classmethod
    def from_dict(cls, raw: dict) -> "InstrumentRef":
        if not isinstance(raw, dict):
            raise ValueError(f"InstrumentRef must be a mapping, got {type(raw).__name__}")
        if "slug" not in raw or "version" not in raw:
            raise ValueError(
                f"InstrumentRef missing slug/version: {raw!r}"
            )
        source = str(raw.get("source", "inferred"))
        if source not in ("inferred", "form", "both"):
            raise ValueError(
                f"InstrumentRef source must be inferred|form|both, got {source!r}"
            )
        return cls(
            slug=str(raw["slug"]),
            version=str(raw["version"]),
            source=source,
            alias=(str(raw["alias"]) if raw.get("alias") else None),
        )

    @property
    def report_filename(self) -> str:
        """Filename for this ref's per-instrument report inside `runs/<ts>/instruments/`."""
        return f"{self.alias or self.slug}.md"


@dataclass(frozen=True)
class StudyManifest:
    """Parsed `manifest.yaml` — the immutable spec of a study."""

    study_id: str
    title: str
    created: str       # ISO timestamp; informational
    schedule: str      # one of SUPPORTED_SCHEDULES
    instruments: tuple[InstrumentRef, ...]
    notes: str = ""

    @classmethod
    def from_dict(cls, raw: dict) -> "StudyManifest":
        if not isinstance(raw, dict):
            raise ValueError("manifest top-level must be a mapping")
        for required in ("study_id", "title", "schedule", "instruments"):
            if required not in raw:
                raise ValueError(f"manifest missing required key: {required!r}")
        study_id = str(raw["study_id"])
        _validate_slug(study_id, where="study_id")
        schedule = str(raw["schedule"])
        if schedule not in SUPPORTED_SCHEDULES:
            raise ValueError(
                f"manifest schedule must be one of {SUPPORTED_SCHEDULES}, "
                f"got {schedule!r}"
            )
        instruments_raw = raw["instruments"]
        if not isinstance(instruments_raw, list) or not instruments_raw:
            raise ValueError("manifest.instruments must be a non-empty list")
        instruments = tuple(InstrumentRef.from_dict(r) for r in instruments_raw)
        aliases = [r.alias or r.slug for r in instruments]
        if len(set(aliases)) != len(aliases):
            raise ValueError(
                "manifest.instruments has duplicate aliases (or duplicate slugs without alias) — "
                "two refs to the same instrument must use distinct `alias:` values"
            )
        return cls(
            study_id=study_id,
            title=str(raw["title"]),
            created=str(raw.get("created", "")),
            schedule=schedule,
            instruments=instruments,
            notes=str(raw.get("notes", "")),
        )

    @classmethod
    def from_path(cls, manifest_path: Path) -> "StudyManifest":
        if not manifest_path.is_file():
            raise FileNotFoundError(f"manifest not found: {manifest_path}")
        return cls.from_dict(
            yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        )

    def to_dict(self) -> dict:
        """Round-trip-friendly dict for `yaml.safe_dump`."""
        return {
            "study_id": self.study_id,
            "title": self.title,
            "created": self.created,
            "schedule": self.schedule,
            "instruments": [
                {
                    "slug": r.slug,
                    "version": r.version,
                    "source": r.source,
                    **({"alias": r.alias} if r.alias else {}),
                }
                for r in self.instruments
            ],
            "notes": self.notes,
        }


@dataclass
class StudyState:
    """Mutable engine-managed state per study. Lives at
    `<study_dir>/state.yaml`."""

    last_run_at: str | None = None    # ISO UTC; None = never run
    run_count: int = 0

    @classmethod
    def load(cls, state_path: Path) -> "StudyState":
        if not state_path.is_file():
            return cls()
        raw = yaml.safe_load(state_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            return cls()
        last = raw.get("last_run_at")
        return cls(
            last_run_at=(str(last) if last else None),
            run_count=int(raw.get("run_count", 0)),
        )

    def write(self, state_path: Path) -> None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            yaml.safe_dump(
                {
                    "last_run_at": self.last_run_at,
                    "run_count": self.run_count,
                },
                sort_keys=False,
                default_flow_style=False,
            ),
            encoding="utf-8",
        )

    def mark_run(self, when: datetime) -> None:
        self.last_run_at = when.astimezone(timezone.utc).isoformat()
        self.run_count += 1


@dataclass
class Study:
    """A loaded study — manifest + state + path."""

    manifest: StudyManifest
    state: StudyState
    study_dir: Path

    @classmethod
    def load(cls, study_dir: Path) -> "Study":
        manifest = StudyManifest.from_path(study_dir / "manifest.yaml")
        state = StudyState.load(study_dir / "state.yaml")
        return cls(manifest=manifest, state=state, study_dir=study_dir)

    @property
    def state_path(self) -> Path:
        return self.study_dir / "state.yaml"

    @property
    def runs_dir(self) -> Path:
        return self.study_dir / "runs"

    def is_due(self, now: datetime | None = None) -> bool:
        """True if the schedule says this study should run again now.

        - `schedule: manual` → never auto-due (always returns False).
        - Otherwise: due if `now - last_run_at >= cooldown_days`.
        - Never-run studies (last_run_at is None) on a non-manual
          schedule: always due.
        """
        cooldown = SCHEDULE_COOLDOWN_DAYS.get(self.manifest.schedule)
        if cooldown is None:
            return False
        if self.state.last_run_at is None:
            return True
        now = now or datetime.now(timezone.utc)
        try:
            last = datetime.fromisoformat(self.state.last_run_at)
        except ValueError:
            return True  # malformed state → treat as never-ran
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (now - last) >= timedelta(days=cooldown)


def _validate_slug(slug: str, *, where: str = "slug") -> None:
    if not (3 <= len(slug) <= 64):
        raise ValueError(f"{where}={slug!r} must be 3..64 chars long")
    if slug.startswith("-") or slug.endswith("-"):
        raise ValueError(f"{where}={slug!r} must not start or end with hyphen")
    bad = set(slug) - _SLUG_OK_CHARS
    if bad:
        raise ValueError(
            f"{where}={slug!r} contains invalid chars: {sorted(bad)} "
            f"(allowed: a-z, 0-9, hyphen)"
        )


# ── Run-directory atomic writes ──────────────────────────────────────


def utc_now_iso() -> str:
    """`2026-05-17T15-30-04` — colons replaced with hyphens for filesystem
    safety on case-insensitive filesystems (macOS APFS, Windows)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


class RunDirectory:
    """Atomic-write helper for one run's output dir.

    Pattern: write all files into a tmp sibling dir under `runs/`,
    then `os.rename()` the whole dir into its final timestamped name
    in a single filesystem operation. If the writer crashes mid-run,
    the tmp dir is left behind (operator can `rm`-cleanup) but no
    half-baked `runs/<ts>/` poisons the timeline.
    """

    def __init__(self, runs_dir: Path, timestamp: str):
        self.runs_dir = runs_dir
        self.timestamp = timestamp
        self.final_dir = runs_dir / timestamp
        # Tmp dir lives ALONGSIDE the final to keep them on the same
        # filesystem (rename across mount points fails).
        self.tmp_dir = runs_dir / f".{timestamp}.tmp"

    def __enter__(self) -> "RunDirectory":
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        if self.tmp_dir.exists():
            # Stale tmp from a prior crashed run — operator visible.
            shutil.rmtree(self.tmp_dir)
        self.tmp_dir.mkdir()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            # Failure: leave tmp_dir for forensics, do NOT rename.
            return
        # Success: atomic rename.
        if self.final_dir.exists():
            raise FileExistsError(
                f"target run dir already exists: {self.final_dir}"
            )
        self.tmp_dir.rename(self.final_dir)

    @property
    def instruments_dir(self) -> Path:
        d = self.tmp_dir / "instruments"
        d.mkdir(exist_ok=True)
        return d

    @property
    def charts_dir(self) -> Path:
        d = self.tmp_dir / "charts"
        d.mkdir(exist_ok=True)
        return d

    def write(self, rel_path: str, content: str) -> Path:
        """Write content to <tmp_dir>/<rel_path>; auto-creates parents."""
        target = self.tmp_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target


# ── Per-study process-level mutex ────────────────────────────────────


def _study_lock_path(study_id: str) -> Path:
    """Path to the flock file for a study. Co-located with the
    compile.lock under STATE_DIR for consistency.
    """
    _validate_slug(study_id, where="study_id")
    return STATE_DIR / f"study-{study_id}.lock"


def acquire_study_lock(study_id: str) -> io.IOBase | None:
    """Try to take an exclusive non-blocking flock on the study-lock.

    Returns the file handle on success — caller MUST keep the
    reference alive for the duration of the run. The kernel releases
    the flock on process exit or on `handle.close()`. Cross-study
    runs do not block each other (per-study lock, not global).
    Returns `None` if another process holds the lock — caller should
    skip with a "another run in progress" message.

    Mirrors compile.py's _acquire_exclusive_lock pattern.
    """
    lock_path = _study_lock_path(study_id)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fd.close()
        return None
    return fd


# ── Study discovery ──────────────────────────────────────────────────


def list_studies(studies_root: Path) -> list[Study]:
    """Return all studies under `studies_root`, sorted by study_id."""
    if not studies_root.is_dir():
        return []
    out: list[Study] = []
    for entry in sorted(studies_root.iterdir()):
        if not entry.is_dir():
            continue
        manifest = entry / "manifest.yaml"
        if not manifest.is_file():
            continue
        try:
            out.append(Study.load(entry))
        except (ValueError, FileNotFoundError, yaml.YAMLError):
            # Malformed manifest (schema OR YAML parse) — skip
            # silently here; surfaces per-study only when operator
            # tries to `wiki study run <id>` directly.
            continue
    return out


def fork_study(
    source_study: Study, new_study_id: str, studies_root: Path
) -> Path:
    """Clone `source_study`'s manifest into a new study dir.

    Creates `studies_root/<new_study_id>/manifest.yaml` with the
    source's instruments/schedule/notes but a fresh `created` stamp
    and an empty state (no runs inherited).
    """
    _validate_slug(new_study_id, where="new_study_id")
    new_dir = studies_root / new_study_id
    if new_dir.exists():
        raise FileExistsError(f"target study already exists: {new_dir}")
    new_dir.mkdir(parents=True)

    new_manifest = StudyManifest(
        study_id=new_study_id,
        title=source_study.manifest.title + " (fork)",
        created=datetime.now(timezone.utc).isoformat(),
        schedule=source_study.manifest.schedule,
        instruments=source_study.manifest.instruments,
        notes=f"Forked from `{source_study.manifest.study_id}` on "
              f"{datetime.now(timezone.utc).date().isoformat()}. "
              f"Edit instruments / schedule / title as needed.",
    )
    (new_dir / "manifest.yaml").write_text(
        yaml.safe_dump(
            new_manifest.to_dict(),
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return new_dir
