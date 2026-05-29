"""Picture-metadata extraction: EXIF + filename-pattern parsing.

Two orthogonal sources of deterministic metadata about a picture file:

1. **EXIF** (via Pillow's `Image.getexif()`) — camera/phone-photo metadata
   embedded in JPEG/PNG by the capture device: DateTimeOriginal, GPS
   coordinates, Make/Model, Software, and shot parameters (FNumber,
   ExposureTime, ISO, FocalLength). Android *screenshots* typically
   carry only `Software` (Android version with device-code hint) and
   no GPS — that's the device's normal behaviour for screenshots.
   iPhone JPEGs and dedicated-camera JPEGs carry the full set.

2. **Filename pattern** — Android tablets / phones name screenshots
   `Screenshot_YYYYMMDD_HHMMSS_<AppContext>.jpg`. The capture timestamp
   is encoded in the name (more accurate than the file's mtime, which
   is the post-sync time after Drive / bridge) and the `<AppContext>`
   is what the user was viewing — usable knowledge signal on its own.

The returned dict is intentionally flat-keys with nested sub-dicts so
the sidecar writer can render frontmatter without further parsing.
Empty / missing fields are omitted rather than rendered as `null`.

HEIC is **not** handled here (Pillow needs `pillow-heif` plugin and
that's not in the engine's dependencies). HEIC sources fall through
gracefully with empty EXIF; capture time falls back to mtime.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


# Android screenshot naming convention. Captures three groups:
#   1. YYYYMMDD (8 digits)
#   2. HHMMSS   (6 digits)
#   3. App context — everything up to the file extension, may contain
#      spaces, apostrophes, ampersands, parens.
_ANDROID_SCREENSHOT_RE = re.compile(
    r"^Screenshot_(\d{8})_(\d{6})_(.+?)\.(jpe?g|png)$",
    re.IGNORECASE,
)


def _parse_android_filename(src: Path) -> dict:
    """Return {captured_at: datetime, app_context: str} if the filename
    matches the Android-screenshot pattern, else {}."""
    match = _ANDROID_SCREENSHOT_RE.match(src.name)
    if not match:
        return {}
    date_str, time_str, app_ctx, _ext = match.groups()
    try:
        captured_at = datetime.strptime(
            f"{date_str}{time_str}", "%Y%m%d%H%M%S"
        )
    except ValueError:
        return {}
    return {
        "captured_at": captured_at,
        "app_context": app_ctx.strip(),
    }


def _dms_rational_to_decimal(dms, ref) -> float | None:
    """Convert EXIF GPS DMS rational triple + ref ('N'/'S'/'E'/'W') to
    decimal degrees. Returns None on malformed input rather than raising
    — partial/corrupt GPS blocks are common."""
    try:
        deg, minutes, seconds = (float(x) for x in dms)
    except (TypeError, ValueError):
        return None
    decimal = deg + minutes / 60.0 + seconds / 3600.0
    if isinstance(ref, str) and ref.upper() in ("S", "W"):
        decimal = -decimal
    return round(decimal, 6)


def _parse_exif(src: Path) -> dict:
    """Return a dict of {captured_at, device, location, shot} from EXIF.

    Best-effort: missing/unreadable EXIF returns {}. Sub-dicts are only
    included when at least one of their keys was extracted, so the
    sidecar writer can emit only what's actually there.
    """
    try:
        # Local import — Pillow is a transitive dep, not declared, so we
        # don't want module-level imports to break the engine if it ever
        # gets stripped (collectors must stay graceful).
        from PIL import ExifTags, Image, UnidentifiedImageError
    except ImportError:
        log.debug("Pillow not available — skipping EXIF for %s", src.name)
        return {}

    try:
        img = Image.open(src)
    except (UnidentifiedImageError, OSError) as exc:
        log.debug("Cannot open %s: %s", src.name, exc)
        return {}

    try:
        exif = img.getexif()
    except Exception:  # noqa: BLE001  — PIL surfaces various odd errors
        log.debug("EXIF read failed for %s", src.name)
        return {}

    if not exif:
        return {}

    out: dict = {}

    # Lookup helpers.
    def tag(name: str):
        for tag_id, value in exif.items():
            if ExifTags.TAGS.get(tag_id) == name:
                return value
        return None

    # captured_at — EXIF stores as "YYYY:MM:DD HH:MM:SS" in DateTimeOriginal
    # (preferred) or DateTime (fallback). Returned as a real datetime.
    for date_key in ("DateTimeOriginal", "DateTime"):
        raw = tag(date_key)
        if isinstance(raw, str) and raw.strip():
            try:
                out["captured_at"] = datetime.strptime(
                    raw.strip(), "%Y:%m:%d %H:%M:%S"
                )
                break
            except ValueError:
                continue

    device: dict = {}
    for key in ("Make", "Model", "Software"):
        val = tag(key)
        if isinstance(val, str) and val.strip():
            device[key.lower()] = val.strip()
    if device:
        out["device"] = device

    # GPS sub-IFD via the standard pointer.
    try:
        gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
    except Exception:  # noqa: BLE001
        gps_ifd = None
    if gps_ifd:
        gps_named: dict = {}
        for k, v in gps_ifd.items():
            name = ExifTags.GPSTAGS.get(k, str(k))
            gps_named[name] = v
        lat = _dms_rational_to_decimal(
            gps_named.get("GPSLatitude"), gps_named.get("GPSLatitudeRef")
        )
        lon = _dms_rational_to_decimal(
            gps_named.get("GPSLongitude"), gps_named.get("GPSLongitudeRef")
        )
        location: dict = {}
        if lat is not None:
            location["lat"] = lat
        if lon is not None:
            location["lon"] = lon
        alt_raw = gps_named.get("GPSAltitude")
        if alt_raw is not None:
            try:
                alt = round(float(alt_raw), 1)
                if gps_named.get("GPSAltitudeRef") in (1, b"\x01"):
                    alt = -alt
                location["alt"] = alt
            except (TypeError, ValueError):
                pass
        if location:
            out["location"] = location

    # Shot parameters — camera/phone photos only; screenshots have none.
    shot: dict = {}
    fnumber = tag("FNumber")
    if fnumber is not None:
        try:
            shot["aperture"] = round(float(fnumber), 1)
        except (TypeError, ValueError):
            pass
    exposure = tag("ExposureTime")
    if exposure is not None:
        try:
            ev = float(exposure)
        except (TypeError, ValueError):
            ev = None
        if ev:
            # Express short exposures as 1/N for human-readability —
            # photographers and camera apps universally do.
            if ev < 1:
                denom = round(1.0 / ev)
                shot["exposure"] = f"1/{denom}"
            else:
                shot["exposure"] = f"{ev:g}"
    iso = tag("ISOSpeedRatings") or tag("PhotographicSensitivity")
    if iso is not None:
        try:
            # Some camera apps serialise ISO as a list; pick the first.
            if isinstance(iso, (list, tuple)):
                iso = iso[0]
            shot["iso"] = int(iso)
        except (TypeError, ValueError):
            pass
    focal = tag("FocalLength")
    if focal is not None:
        try:
            shot["focal_length_mm"] = round(float(focal), 1)
        except (TypeError, ValueError):
            pass
    if shot:
        out["shot"] = shot

    return out


def extract_metadata(src: Path) -> dict:
    """Combine EXIF + filename-pattern metadata for one picture file.

    Priority for `captured_at` when both sources have it:
      1. EXIF DateTimeOriginal (camera/phone authoritative)
      2. Filename pattern (Android screenshot encoding)
      3. _(left absent — caller falls back to file mtime)_

    Returns a dict with any subset of:
      captured_at: datetime
      device:      {make?, model?, software?}
      location:    {lat?, lon?, alt?}
      shot:        {aperture?, exposure?, iso?, focal_length_mm?}
      app_context: str   (Android-screenshot filename only)

    Empty dict means: no deterministic metadata available; collector
    falls back to mtime + bare vision output.
    """
    exif_meta = _parse_exif(src)
    name_meta = _parse_android_filename(src)

    # Merge with EXIF winning on captured_at.
    merged: dict = {}
    merged.update(name_meta)
    merged.update(exif_meta)
    # If EXIF didn't have captured_at but filename did, the filename
    # value already landed via name_meta first; nothing more to do.
    if "app_context" in name_meta:
        merged["app_context"] = name_meta["app_context"]
    return merged
