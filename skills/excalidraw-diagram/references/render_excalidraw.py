"""Render Excalidraw JSON to PNG using Playwright + headless Chromium.

Usage:
    cd skills/excalidraw-diagram/references
    uv run python render_excalidraw.py <path-to-file.excalidraw> [--output path.png] [--scale 2] [--width 1920]

First-time setup:
    cd skills/excalidraw-diagram/references
    uv sync
    uv run playwright install chromium
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def validate_excalidraw(data: dict) -> list[str]:
    """Validate Excalidraw JSON structure. Returns list of errors (empty = valid)."""
    errors: list[str] = []

    if data.get("type") != "excalidraw":
        errors.append(f"Expected type 'excalidraw', got '{data.get('type')}'")

    if "elements" not in data:
        errors.append("Missing 'elements' array")
    elif not isinstance(data["elements"], list):
        errors.append("'elements' must be an array")
    elif len(data["elements"]) == 0:
        errors.append("'elements' array is empty — nothing to render")

    return errors


def compute_bounding_box(elements: list[dict]) -> tuple[float, float, float, float]:
    """Compute bounding box (min_x, min_y, max_x, max_y) across all elements."""
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for el in elements:
        if el.get("isDeleted"):
            continue
        x = el.get("x", 0)
        y = el.get("y", 0)
        w = el.get("width", 0)
        h = el.get("height", 0)

        # For arrows/lines, points array defines the shape relative to x,y
        if el.get("type") in ("arrow", "line") and "points" in el:
            for px, py in el["points"]:
                min_x = min(min_x, x + px)
                min_y = min(min_y, y + py)
                max_x = max(max_x, x + px)
                max_y = max(max_y, y + py)
        else:
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + abs(w))
            max_y = max(max_y, y + abs(h))

    if min_x == float("inf"):
        return (0, 0, 800, 600)

    return (min_x, min_y, max_x, max_y)


def render(
    excalidraw_path: Path,
    output_path: Path | None = None,
    scale: int = 2,
    max_width: int = 1920,
    module_timeout_ms: int = 90_000,
    render_timeout_ms: int = 60_000,
) -> Path:
    """Render an .excalidraw file to PNG. Returns the output PNG path.

    Timeouts (in milliseconds) are tunable for large diagrams that exceed the
    defaults. ``module_timeout_ms`` covers the Excalidraw ES-module load from
    esm.sh; ``render_timeout_ms`` covers the actual draw-to-SVG once the
    diagram JSON is injected.
    """
    # Import playwright here so validation errors show before import errors
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed.", file=sys.stderr)
        print("Run: cd skills/excalidraw-diagram/references && uv sync && uv run playwright install chromium", file=sys.stderr)
        sys.exit(1)

    # Read and validate
    raw = excalidraw_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {excalidraw_path}: {e}", file=sys.stderr)
        sys.exit(1)

    errors = validate_excalidraw(data)
    if errors:
        print(f"ERROR: Invalid Excalidraw file:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    # Compute viewport size from element bounding box
    elements = [e for e in data["elements"] if not e.get("isDeleted")]
    min_x, min_y, max_x, max_y = compute_bounding_box(elements)
    padding = 80
    diagram_w = max_x - min_x + padding * 2
    diagram_h = max_y - min_y + padding * 2

    # Cap viewport width, let height be natural
    vp_width = min(int(diagram_w), max_width)
    vp_height = max(int(diagram_h), 600)

    # Output path
    if output_path is None:
        output_path = excalidraw_path.with_suffix(".png")

    # Template path (same directory as this script)
    template_path = Path(__file__).parent / "render_template.html"
    if not template_path.exists():
        print(f"ERROR: Template not found at {template_path}", file=sys.stderr)
        sys.exit(1)

    template_url = template_path.as_uri()

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            if "Executable doesn't exist" in str(e) or "browserType.launch" in str(e):
                print("ERROR: Chromium not installed for Playwright.", file=sys.stderr)
                print("Run: cd skills/excalidraw-diagram/references && uv run playwright install chromium", file=sys.stderr)
                sys.exit(1)
            raise

        page = browser.new_page(
            viewport={"width": vp_width, "height": vp_height},
            device_scale_factor=scale,
        )

        # Load the template
        page.goto(template_url)

        # Wait for the ES module to load (imports from esm.sh)
        page.wait_for_function("window.__moduleReady === true", timeout=module_timeout_ms)

        # Inject the diagram data and render
        json_str = json.dumps(data)
        result = page.evaluate(f"window.renderDiagram({json_str})")

        if not result or not result.get("success"):
            error_msg = result.get("error", "Unknown render error") if result else "renderDiagram returned null"
            print(f"ERROR: Render failed: {error_msg}", file=sys.stderr)
            browser.close()
            sys.exit(1)

        # Wait for render completion signal
        page.wait_for_function("window.__renderComplete === true", timeout=render_timeout_ms)

        # Screenshot the SVG element
        svg_el = page.query_selector("#root svg")
        if svg_el is None:
            print("ERROR: No SVG element found after render.", file=sys.stderr)
            browser.close()
            sys.exit(1)

        svg_el.screenshot(path=str(output_path))
        browser.close()

    return output_path


def crop_png(png_path: Path, crop_spec: str) -> Path:
    """Crop a region from a rendered PNG.

    crop_spec format: "x,y,w,h" in Excalidraw coordinates.

    The mapping from Excalidraw coords to pixel coords is computed by comparing
    the actual PNG dimensions against the element bounding box. This handles
    whatever internal scaling Excalidraw's SVG export applies.

    Returns path to the cropped PNG (saved as *-crop.png).
    """
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None  # disable decompression bomb check

    parts = [int(p.strip()) for p in crop_spec.split(",")]
    if len(parts) != 4:
        print(f"ERROR: --crop requires 'x,y,w,h' format, got: {crop_spec}", file=sys.stderr)
        sys.exit(1)

    cx, cy, cw, ch = parts

    # Read the excalidraw to get bounding box
    excalidraw_path = png_path.with_suffix(".excalidraw")
    if not excalidraw_path.exists():
        print(f"ERROR: Need .excalidraw file next to PNG for coordinate mapping", file=sys.stderr)
        sys.exit(1)

    data = json.loads(excalidraw_path.read_text(encoding="utf-8"))
    elements = [e for e in data["elements"] if not e.get("isDeleted")]
    min_x, min_y, max_x, max_y = compute_bounding_box(elements)
    padding = 80

    # Excalidraw coordinate space (with padding)
    exc_w = max_x - min_x + padding * 2
    exc_h = max_y - min_y + padding * 2

    # Actual PNG pixel dimensions
    img = Image.open(png_path)
    png_w, png_h = img.size

    # Compute scale factors (PNG pixels per Excalidraw unit)
    sx = png_w / exc_w
    sy = png_h / exc_h

    # Convert Excalidraw coords to pixel coords
    px = int((cx - min_x + padding) * sx)
    py = int((cy - min_y + padding) * sy)
    pw = int(cw * sx)
    ph = int(ch * sy)

    # Clamp to image bounds
    px = max(0, min(px, png_w))
    py = max(0, min(py, png_h))
    pw = min(pw, png_w - px)
    ph = min(ph, png_h - py)

    cropped = img.crop((px, py, px + pw, py + ph))

    crop_path = png_path.with_stem(png_path.stem + "-crop")
    cropped.save(crop_path)

    print(f"Crop: excalidraw({cx},{cy},{cw},{ch}) → pixel({px},{py},{pw},{ph})", file=sys.stderr)
    return crop_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Excalidraw JSON to PNG")
    parser.add_argument("input", type=Path, help="Path to .excalidraw JSON file")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output PNG path (default: same name with .png)")
    parser.add_argument("--scale", "-s", type=int, default=2, help="Device scale factor (default: 2)")
    parser.add_argument("--width", "-w", type=int, default=1920, help="Max viewport width (default: 1920)")
    parser.add_argument("--crop", "-c", type=str, default=None,
                        help="Crop region in Excalidraw coords: 'x,y,width,height'. "
                             "Renders full diagram first, then extracts the region. "
                             "Output saved as *-crop.png next to the full render.")
    parser.add_argument("--module-timeout", type=int, default=90_000,
                        help="Module-load timeout in ms (default: 90000). Bump for slow networks.")
    parser.add_argument("--render-timeout", type=int, default=60_000,
                        help="Render-completion timeout in ms (default: 60000). "
                             "Bump for very large diagrams (~150+ elements).")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    png_path = render(
        args.input, args.output, args.scale, args.width,
        module_timeout_ms=args.module_timeout,
        render_timeout_ms=args.render_timeout,
    )
    print(str(png_path))

    if args.crop:
        crop_path = crop_png(png_path, args.crop)
        print(str(crop_path))


if __name__ == "__main__":
    main()
