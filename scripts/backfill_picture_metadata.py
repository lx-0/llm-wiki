"""One-shot backfill for picture-archive sidecars: add EXIF + filename
metadata to sidecars written before 2026-05-29.

Walks `raw/inbox-mobile/pictures/*.md`, locates each sidecar's matching
original image (same stem with .jpg / .jpeg / .png / .heic), runs the
same `collectors._picture_metadata.extract_metadata()` the live
collector now calls on ingest, and merges the new keys into the
sidecar's frontmatter — *without* touching existing keys.

Idempotent per-key: the merge writes only frontmatter keys that aren't
already present. Existing keys (operator-edited or filled by an earlier
backfill pass) are preserved verbatim. A re-run after a missing
dependency (e.g. Pillow) gets installed picks up the previously-skipped
EXIF fields without disturbing the keys filename parsing already
provided.

Body (everything after the closing `---` of frontmatter) is preserved
byte-for-byte. The frontmatter YAML is re-serialised via yaml.safe_dump
(deterministic key ordering) — these sidecars are engine-generated, no
operator comments to preserve.

Usage:
    wiki backfill picture-metadata           # apply
    wiki backfill picture-metadata --dry-run # show what would change
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collectors._picture_metadata import extract_metadata  # noqa: E402
from core.paths import RAW_DIR  # noqa: E402

log = logging.getLogger("backfill-picture-metadata")

ACCEPTED_SUFFIXES = (".jpg", ".jpeg", ".png", ".heic")
PICTURES_ARCHIVE = RAW_DIR / "inbox-mobile" / "pictures"

def _split_frontmatter(text: str) -> tuple[dict | None, str]:
    """Return (parsed FM dict, body). (None, text) if no FM block found."""
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return None, text
    fm_text = text[4:end]
    body = text[end + 5 :]
    try:
        parsed = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return None, text
    if not isinstance(parsed, dict):
        return None, text
    return parsed, body


def _find_original(sidecar: Path) -> Path | None:
    """Locate the picture file matching a sidecar `<stem>.md` in the same
    directory. Returns None if no candidate file with an accepted suffix
    exists alongside."""
    for suffix in ACCEPTED_SUFFIXES:
        candidate = sidecar.with_suffix(suffix)
        if candidate.exists():
            return candidate
        # try upper-case JPG too (camera apps)
        candidate = sidecar.with_suffix(suffix.upper())
        if candidate.exists():
            return candidate
    return None


def _serialise_metadata_for_yaml(meta: dict) -> dict:
    """Convert non-YAML-native values (datetime) in picture-metadata to
    strings PyYAML can round-trip. Leaves nested sub-dicts intact."""
    out: dict = {}
    for key, value in meta.items():
        if isinstance(value, datetime):
            out[key] = value.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            out[key] = value
    return out


def _backfill_one(sidecar: Path, *, dry_run: bool) -> str:
    """Return a status string: 'skipped:<reason>' | 'updated:<n>keys' |
    'nochange'."""
    text = sidecar.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(text)
    if fm is None:
        return "skipped:no_frontmatter"

    original = _find_original(sidecar)
    if original is None:
        return "skipped:original_missing"

    extracted = extract_metadata(original)
    if not extracted:
        return "nochange"

    serialised = _serialise_metadata_for_yaml(extracted)

    # Merge: never clobber an existing key. Backfill only adds.
    added: list[str] = []
    for key, value in serialised.items():
        if key in fm:
            continue
        fm[key] = value
        added.append(key)

    if not added:
        return "nochange"

    if dry_run:
        return f"dry-run:{','.join(added)}"

    new_fm_text = yaml.safe_dump(
        fm, default_flow_style=False, sort_keys=False, allow_unicode=True
    )
    sidecar.write_text(f"---\n{new_fm_text}---\n{body}", encoding="utf-8")
    return f"updated:{','.join(added)}"


def main() -> int:
    parser = argparse.ArgumentParser(prog="wiki backfill picture-metadata")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="show what would change without writing",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if not PICTURES_ARCHIVE.exists():
        log.error("pictures archive not found: %s", PICTURES_ARCHIVE)
        return 1

    sidecars = sorted(PICTURES_ARCHIVE.glob("*.md"))
    if not sidecars:
        log.info("no sidecars under %s", PICTURES_ARCHIVE)
        return 0

    counts: dict[str, int] = {}
    for sc in sidecars:
        status = _backfill_one(sc, dry_run=args.dry_run)
        bucket = status.split(":", 1)[0]
        counts[bucket] = counts.get(bucket, 0) + 1
        if bucket in ("updated", "dry-run"):
            log.info("%s — %s", sc.name, status)
        elif bucket == "skipped" and status != "skipped:already_backfilled":
            log.warning("%s — %s", sc.name, status)

    log.info("─" * 60)
    log.info("Summary across %d sidecar(s):", len(sidecars))
    for bucket, n in sorted(counts.items()):
        log.info("  %s: %d", bucket, n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
