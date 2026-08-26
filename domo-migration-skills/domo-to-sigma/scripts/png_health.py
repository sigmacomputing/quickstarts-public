#!/usr/bin/env python3
"""Deterministic health check for PNG dashboard exports.

The detector is intentionally conservative.  It rejects decoded PNGs that are
solid, all-white, or contain only a tiny amount of visible ink; it is not an
image-quality or dashboard-completeness scorer.
"""

import argparse
import json
import os
import sys

REMEDIATION = (
    "png_health.py requires Pillow and numpy. "
    "Install with: pip install pillow numpy"
)

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover - exercised through the CLI
    np = None
    Image = None


# Pixels must differ visibly from the modal background color to count as ink.
INK_DELTA = 12
# Below both limits, the export contains too little content to be useful.
TINY_INK_RATIO = 0.0005
TINY_INK_PIXELS = 256


def _empty_result(path, reason):
    return {
        "path": os.fspath(path),
        "width": None,
        "height": None,
        "background": None,
        "ink_ratio": None,
        "entropy": None,
        "status": "ERROR",
        "reasons": [reason],
    }


def _flatten_rgb(image):
    """Return an RGB image with transparency composited onto white."""
    if image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba = image.convert("RGBA")
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(white, rgba).convert("RGB")
    return image.convert("RGB")


def _modal_color(rgb):
    """Return the exact modal RGB color with deterministic tie-breaking."""
    pixels = rgb.reshape((-1, 3))
    packed = (
        (pixels[:, 0].astype(np.uint32) << 16)
        | (pixels[:, 1].astype(np.uint32) << 8)
        | pixels[:, 2].astype(np.uint32)
    )
    values, counts = np.unique(packed, return_counts=True)
    value = int(values[np.flatnonzero(counts == counts.max())[0]])
    return np.asarray(
        [(value >> 16) & 255, (value >> 8) & 255, value & 255],
        dtype=np.int16,
    )


def _grayscale_entropy(rgb):
    """Return Shannon entropy in bits from a deterministic luma histogram."""
    gray = (
        299 * rgb[:, :, 0].astype(np.uint32)
        + 587 * rgb[:, :, 1].astype(np.uint32)
        + 114 * rgb[:, :, 2].astype(np.uint32)
        + 500
    ) // 1000
    counts = np.bincount(gray.ravel(), minlength=256)
    probabilities = counts[counts > 0].astype(np.float64) / gray.size
    return max(0.0, float(-(probabilities * np.log2(probabilities)).sum()))


def analyze_image(path):
    """Analyze one PNG and return a JSON-serializable health object.

    Decode/dependency problems are represented as ``status == "ERROR"`` rather
    than raised, making this function convenient for callers that need to
    preserve diagnostics in a larger verdict.
    """
    path = os.fspath(path)
    if Image is None or np is None:
        return _empty_result(path, REMEDIATION)

    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                return _empty_result(path, "image is not a PNG")
            image.load()
            width, height = image.size
            rgb_image = _flatten_rgb(image)
        rgb = np.asarray(rgb_image, dtype=np.uint8)
    except (OSError, ValueError) as exc:
        return _empty_result(path, "could not read PNG: %s" % exc)

    background = _modal_color(rgb)
    delta = np.max(
        np.abs(rgb.astype(np.int16) - background.reshape((1, 1, 3))),
        axis=2,
    )
    ink_pixels = int(np.count_nonzero(delta > INK_DELTA))
    pixel_count = width * height
    ink_ratio = ink_pixels / float(pixel_count)
    entropy = _grayscale_entropy(rgb)

    reasons = []
    if ink_pixels == 0:
        if bool(np.all(background >= 250)):
            reasons.append("image is all white")
        else:
            reasons.append("image is a solid color")
    elif ink_ratio < TINY_INK_RATIO and ink_pixels < TINY_INK_PIXELS:
        reasons.append(
            "image contains only tiny ink (%d pixels, %.6f of image)"
            % (ink_pixels, ink_ratio)
        )

    return {
        "path": path,
        "width": width,
        "height": height,
        "background": [int(channel) for channel in background],
        "ink_ratio": round(ink_ratio, 6),
        "entropy": round(entropy, 4),
        "status": "FAIL" if reasons else "PASS",
        "reasons": reasons,
    }


# Short aliases for callers that prefer a generic function name.
analyze = analyze_image
check_png = analyze_image


def _write_json(result, output_path=None):
    payload = json.dumps(result, indent=2) + "\n"
    if output_path:
        out_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(out_dir, exist_ok=True)
        with open(output_path, "w") as output:
            output.write(payload)
    else:
        sys.stdout.write(payload)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Detect blank or effectively blank PNG exports."
    )
    parser.add_argument("path", nargs="?", help="PNG image path")
    parser.add_argument("--image", help="PNG image path (alternative to positional)")
    parser.add_argument("--json-out", help="optional output JSON path")
    args = parser.parse_args(argv)

    if bool(args.path) == bool(args.image):
        parser.error("provide exactly one of positional PATH or --image PATH")

    result = analyze_image(args.path or args.image)
    _write_json(result, args.json_out)
    if result["status"] == "PASS":
        return 0
    if result["status"] == "FAIL":
        return 1
    if result["reasons"] == [REMEDIATION]:
        sys.stderr.write(REMEDIATION + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
