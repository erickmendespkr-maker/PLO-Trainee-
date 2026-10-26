"""Offline end-frame thumbnail comparison for prerecorded PLO5/PLO6 clips.

Compares the *last decoded* video frame in each recording, not container
metadata or an assumed nominal-FPS index. A small grayscale thumbnail is
used deliberately: the result is a diagnostic, not a provenance proof.
Does not change source, clip, or any hand/equity/EV records.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import tempfile

from offline_ffmpeg_clip_end_audit import audit
from offline_ffmpeg_frame_provenance import require, run, source_hash

THUMB_WIDTH = 256
THUMB_HEIGHT = 144
MAX_PNG_BYTES = 2 * 1024 * 1024


def _last_frame_thumbnail(video: Path, temporary_directory: Path, label: str) -> bytes:
    """Decode a bounded tail and preserve its final frame as a grayscale PNG."""
    png = temporary_directory / f"{label}.png"
    # -sseof is an *input* seek; for videos shorter than 5s FFmpeg starts at 0.
    # -update 1 overwrites only our private temporary file on each decoded frame.
    run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
         "-sseof", "-5", "-noautorotate", "-i", str(video),
         "-map", "0:v:0", "-an", "-sn", "-dn",
         "-vf", f"scale={THUMB_WIDTH}:{THUMB_HEIGHT}:flags=bilinear,format=gray",
         "-fps_mode", "passthrough", "-update", "1", "-f", "image2",
         "-vcodec", "png", str(png)], 120)
    require(png.is_file() and not png.is_symlink() and
            0 < png.stat().st_size <= MAX_PNG_BYTES, "Missing/oversized terminal PNG")
    require(png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", "Invalid terminal PNG")
    decoded = run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
                   "-i", str(png), "-frames:v", "1", "-f", "rawvideo",
                   "-pix_fmt", "gray", "-"], 30).stdout
    require(len(decoded) == THUMB_WIDTH * THUMB_HEIGHT,
            "Invalid terminal thumbnail dimensions")
    return decoded


def compare(source, clip, requested_start_seconds):
    """Return timing and terminal-thumbnail diagnostics, with explicit limits."""
    # Timing checks also validate input paths, regular-file hashes and start.
    timing = audit(source, clip, requested_start_seconds)
    source_path, clip_path = Path(source), Path(clip)
    with tempfile.TemporaryDirectory(prefix="plo_last_frame_") as temp:
        work = Path(temp)
        a = _last_frame_thumbnail(source_path, work, "source")
        b = _last_frame_thumbnail(clip_path, work, "clip")
    # Do not silently accept concurrent replacement after decoding.
    require(source_hash(source_path) == timing["source"]["sha256"] and
            source_hash(clip_path) == timing["clip"]["sha256"],
            "Video changed during visual comparison")
    mae = sum(abs(x - y) for x, y in zip(a, b)) / len(a)
    require(math.isfinite(mae), "Invalid thumbnail error")
    # Thresholds are *heuristics*, not calibrated recognition probabilities.
    visual = ("near_identical_thumbnail" if mae <= 1 else
              "similar_thumbnail" if mae <= 8 else "different_thumbnail")
    return {
        "schema_version": 1,
        "status": "terminal_frame_diagnostic_not_video_provenance",
        "timing_classification": timing["classification"],
        "timing_difference_seconds": timing["difference_seconds"],
        "thumbnail_classification": visual,
        "mean_absolute_gray_error_0_to_255": round(mae, 6),
        "thumbnail_dimensions": [THUMB_WIDTH, THUMB_HEIGHT],
        "source_sha256": timing["source"]["sha256"],
        "clip_sha256": timing["clip"]["sha256"],
        "last_decoded_frame_compared": True,
        "visual_provenance_verified": False,
        "last_frame_duplicated_or_missing_verified": False,
        "ocr_verified": False,
        "equity_ev_authorized": False,
        "limitations": [
            "The last decoded frames are compared as 256x144 grayscale thumbnails.",
            "Re-encoding, overlays, resizing and color conversion affect pixel differences.",
            "Similar thumbnails do not prove source/clip provenance or identical frames.",
            "Only terminal frames are compared; preceding frames and duplication are not checked.",
            "Video packet timing is diagnostic and may differ from container duration.",
            "No OCR, card/action verification, equity or EV authorization is performed.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_recording")
    parser.add_argument("exported_clip")
    parser.add_argument("requested_start_seconds", type=float)
    parser.add_argument("new_report_json")
    args = parser.parse_args(argv)
    report_path = Path(args.new_report_json)
    require(report_path.parent.is_dir() and not report_path.parent.is_symlink() and
            not report_path.exists(), "Unsafe output path")
    report = compare(args.source_recording, args.exported_clip,
                     args.requested_start_seconds)
    with report_path.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps({"timing": report["timing_classification"],
                      "thumbnail": report["thumbnail_classification"],
                      "mae": report["mean_absolute_gray_error_0_to_255"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
