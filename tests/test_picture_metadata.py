"""Tests for scripts/collectors/_picture_metadata.py — EXIF + Android-
screenshot-filename metadata extraction.

EXIF parsing is exercised against a synthesised JPEG built in-test (no
fixture binary) so the suite stays portable and the assertion surface
is whatever we put in. Filename parsing is pure-Python regex.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def _import():
    from collectors import _picture_metadata as m
    return m


# ── Android-filename parser ────────────────────────────────────────


def test_filename_parses_android_screenshot(tmp_path):
    m = _import()
    p = tmp_path / "Screenshot_20240905_171758_O'Reilly.jpg"
    p.write_bytes(b"")
    out = m._parse_android_filename(p)
    assert out["captured_at"] == datetime(2024, 9, 5, 17, 17, 58)
    assert out["app_context"] == "O'Reilly"


def test_filename_parses_multiword_app(tmp_path):
    m = _import()
    p = tmp_path / "Screenshot_20240811_091131_ReVanced Extended.jpg"
    p.write_bytes(b"")
    out = m._parse_android_filename(p)
    assert out["app_context"] == "ReVanced Extended"


def test_filename_handles_png(tmp_path):
    m = _import()
    p = tmp_path / "Screenshot_20250211_120000_Browser.png"
    p.write_bytes(b"")
    out = m._parse_android_filename(p)
    assert out["captured_at"] == datetime(2025, 2, 11, 12, 0, 0)


def test_filename_returns_empty_on_other_patterns(tmp_path):
    m = _import()
    for name in ("IMG_1234.jpg", "DSC00042.JPG", "Random.png", "Screenshot_garbage.jpg"):
        p = tmp_path / name
        p.write_bytes(b"")
        assert m._parse_android_filename(p) == {}


def test_filename_returns_empty_on_invalid_date(tmp_path):
    m = _import()
    p = tmp_path / "Screenshot_20259999_999999_Bogus.jpg"
    p.write_bytes(b"")
    assert m._parse_android_filename(p) == {}


# ── GPS rational → decimal ────────────────────────────────────────


def test_gps_dms_to_decimal_north_east():
    m = _import()
    val = m._dms_rational_to_decimal((51, 30, 26.0), "N")
    assert val is not None
    assert 51.50 < val < 51.51


def test_gps_dms_to_decimal_south_negates():
    m = _import()
    val = m._dms_rational_to_decimal((33, 51, 35.0), "S")
    assert val is not None
    assert val < 0


def test_gps_dms_to_decimal_invalid_returns_none():
    m = _import()
    assert m._dms_rational_to_decimal(("a", "b", "c"), "N") is None
    assert m._dms_rational_to_decimal(None, "N") is None


# ── Full EXIF parse against synthesised JPEG ──────────────────────


def _make_jpeg_with_exif(path: Path, exif_dict: dict) -> None:
    """Write a tiny JPEG carrying the given EXIF dict.

    Uses Pillow's `Image.Exif` API rather than piexif so we don't
    pull a new dep. `exif_dict` keys are Pillow EXIF tag IDs from
    `PIL.ExifTags.TAGS` (the reverse mapping).
    """
    from PIL import Image, ExifTags

    img = Image.new("RGB", (16, 16), color=(128, 128, 128))
    exif = img.getexif()
    name_to_id = {v: k for k, v in ExifTags.TAGS.items()}
    for name, val in exif_dict.items():
        tag_id = name_to_id.get(name)
        if tag_id is None:
            continue
        exif[tag_id] = val
    img.save(path, format="JPEG", exif=exif)


def test_exif_parse_minimal_android_style(tmp_path):
    """Software-only EXIF block (Android-screenshot shape) lands in `device`."""
    m = _import()
    p = tmp_path / "fake.jpg"
    _make_jpeg_with_exif(p, {"Software": "Android UP1A.231005.007.X200XXS3DXD5"})
    out = m._parse_exif(p)
    assert "device" in out
    assert "android" in out["device"]["software"].lower()


def test_exif_parse_datetime_original(tmp_path):
    m = _import()
    p = tmp_path / "fake.jpg"
    _make_jpeg_with_exif(p, {"DateTimeOriginal": "2024:09:05 17:17:58"})
    out = m._parse_exif(p)
    assert out["captured_at"] == datetime(2024, 9, 5, 17, 17, 58)


def test_exif_parse_make_and_model(tmp_path):
    m = _import()
    p = tmp_path / "fake.jpg"
    _make_jpeg_with_exif(p, {"Make": "Apple", "Model": "iPhone 15 Pro"})
    out = m._parse_exif(p)
    assert out["device"]["make"] == "Apple"
    assert out["device"]["model"] == "iPhone 15 Pro"


def test_exif_parse_empty_on_no_exif(tmp_path):
    """A bare JPEG with no EXIF block returns {}, never raises."""
    m = _import()
    from PIL import Image

    p = tmp_path / "blank.jpg"
    Image.new("RGB", (8, 8)).save(p, format="JPEG")
    out = m._parse_exif(p)
    assert out == {} or "captured_at" not in out  # tolerant of platform Pillow defaults


def test_exif_parse_returns_empty_on_unreadable(tmp_path):
    m = _import()
    p = tmp_path / "garbage.jpg"
    p.write_bytes(b"this is not a jpeg")
    assert m._parse_exif(p) == {}


# ── extract_metadata: merge order ─────────────────────────────────


def test_extract_merges_exif_and_filename(tmp_path):
    """When both sources have captured_at, EXIF wins."""
    m = _import()
    p = tmp_path / "Screenshot_20240101_120000_App.jpg"
    _make_jpeg_with_exif(p, {"DateTimeOriginal": "2024:09:05 17:17:58"})
    out = m.extract_metadata(p)
    assert out["captured_at"] == datetime(2024, 9, 5, 17, 17, 58)
    assert out["app_context"] == "App"


def test_extract_filename_only_when_no_exif_date(tmp_path):
    """Without EXIF DateTimeOriginal, filename wins."""
    m = _import()
    p = tmp_path / "Screenshot_20240811_091131_ReVanced Extended.jpg"
    _make_jpeg_with_exif(p, {"Software": "Android"})
    out = m.extract_metadata(p)
    assert out["captured_at"] == datetime(2024, 8, 11, 9, 11, 31)
    assert out["app_context"] == "ReVanced Extended"


def test_extract_returns_empty_when_nothing_extractable(tmp_path):
    """Plain camera JPEG with no EXIF + no matching filename → {} or near-empty."""
    m = _import()
    from PIL import Image

    p = tmp_path / "IMG_1234.jpg"
    Image.new("RGB", (8, 8)).save(p, format="JPEG")
    out = m.extract_metadata(p)
    # Pillow may inject Orientation by default — accept that, but no
    # meaningful captured_at / app_context / device.
    assert "app_context" not in out
    assert "captured_at" not in out
