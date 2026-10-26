"""Offline diagnostic for MP4 clips ending at the last available source frame.

Compares observed *video packet presentation spans*, not container duration.
Does not fix, pad, interpolate, or alter clips; does not prove clip provenance.
Use only on user-authorized recorded files, never live sessions.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics

from offline_ffmpeg_frame_provenance import require, run, source_hash

MAX_PROBE_BYTES = 64 * 1024 * 1024
MAX_PACKETS = 300_000


def packet_span(video):
    video = Path(video)
    require(video.suffix.lower() in (".mp4", ".webm", ".mkv", ".mov"),
            "Unsupported video extension")
    # source_hash checks regular file, size and no symlink before FFprobe opens it.
    sha = source_hash(video)
    output = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                  "-show_entries", "packet=pts_time,duration_time", "-of", "json",
                  str(video)], 180)
    require(len(output.stdout) <= MAX_PROBE_BYTES, "FFprobe output too large")
    data = json.loads(output.stdout)
    packets = data.get("packets")
    require(type(packets) is list and 1 <= len(packets) <= MAX_PACKETS,
            "Missing/too many video packets")
    parsed = []
    for p in packets:
        require(type(p) is dict, "Invalid video packet")
        try:
            pts = float(p["pts_time"])
            duration = float(p["duration_time"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Packet PTS/duration missing; end indeterminate") from exc
        require(math.isfinite(pts) and math.isfinite(duration) and duration > 0,
                "Invalid packet PTS/duration")
        parsed.append((pts, duration))
    first_pts = min(p[0] for p in parsed)
    end_pts = max(pts + duration for pts, duration in parsed)
    span = end_pts - first_pts
    require(0 < span <= 7201, "Unsupported presentation span")
    require(source_hash(video) == sha, "Video changed during FFprobe")
    return {
        "sha256": sha, "video_packet_count": len(parsed),
        "first_video_pts_seconds": first_pts,
        "last_video_end_pts_seconds": end_pts,
        "presentation_span_seconds": span,
        "median_packet_duration_seconds": statistics.median(p[1] for p in parsed),
        "last_presentation_packet_duration_seconds": max(parsed, key=lambda p: p[0] + p[1])[1],
    }


def audit(source, clip, requested_start_seconds):
    require(type(requested_start_seconds) in (int, float) and
            math.isfinite(requested_start_seconds) and requested_start_seconds >= 0,
            "Invalid requested start")
    src = packet_span(source)
    dst = packet_span(clip)
    require(src["sha256"] != dst["sha256"], "Source and clip are identical")
    require(requested_start_seconds < src["presentation_span_seconds"],
            "Requested start beyond source presentation span")
    expected = src["presentation_span_seconds"] - requested_start_seconds
    observed = dst["presentation_span_seconds"]
    difference = observed - expected
    tolerance = max(src["last_presentation_packet_duration_seconds"],
                    dst["last_presentation_packet_duration_seconds"], 0.01) + 0.005
    classification = ("shorter_than_expected" if difference < -tolerance else
                      "longer_than_expected" if difference > tolerance else
                      "within_one_frame_tolerance")
    return {
        "schema_version": 1,
        "status": "timing_diagnostic_only_not_visual_proof",
        "source": src, "clip": dst,
        "requested_start_seconds": requested_start_seconds,
        "expected_clip_video_span_seconds": expected,
        "observed_clip_video_span_seconds": observed,
        "difference_seconds": difference,
        "frame_tolerance_seconds": tolerance,
        "classification": classification,
        "last_frame_duplicated_or_missing_verified": False,
        "source_clip_visual_correspondence_verified": False,
        "limitations": [
            "Video packet presentation timestamps are not independent visual frame validation.",
            "Container duration and audio duration can differ from video presentation span.",
            "Re-encoding may shift frame boundaries; this is a diagnostic, not a fix.",
            "A comparison does not establish that the clip came from the source.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_recording")
    parser.add_argument("exported_clip")
    parser.add_argument("requested_start_seconds", type=float)
    parser.add_argument("new_report_json")
    args = parser.parse_args(argv)
    report = audit(args.source_recording, args.exported_clip,
                   args.requested_start_seconds)
    target = Path(args.new_report_json)
    require(target.parent.is_dir() and not target.parent.is_symlink() and
            not target.exists(), "Unsafe output path")
    with target.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps({"classification": report["classification"],
                      "difference_seconds": report["difference_seconds"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())