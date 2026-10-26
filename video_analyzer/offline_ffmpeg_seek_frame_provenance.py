"""Indexed seek extraction for sparse requested frames in *recorded* videos.

An FFprobe frame-PTS scan maps absolute decoded-frame indices to timestamps;
FFmpeg then seeks to each requested timestamp, validating its actual decoded
PTS against the index. This is an alternative to the full-decode batch path.
Fast input-side seeks may miss B-frames near GOP boundaries. A PTS mismatch
triggers a correctness-first full-decode fallback. This does NOT prove speedup
on long videos or verify cards/actions.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

from offline_ffmpeg_frame_provenance import PTS_RE, require, run

MAX_INDEX_BYTES = 64 * 1024 * 1024
MAX_INDEX_FRAMES = 500_000
MAX_FULL_FRAME_BYTES = 64 * 1024 * 1024
FRAME_TOLERANCE_SECONDS = 0.001


def frame_pts_index(video: Path, duration: float) -> list[float]:
    result = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                  "-show_entries", "frame=best_effort_timestamp_time",
                  "-of", "json", str(video)], 240)
    require(len(result.stdout) <= MAX_INDEX_BYTES, "Frame index output too large")
    data = json.loads(result.stdout)
    rows = data.get("frames")
    require(type(rows) is list and 1 <= len(rows) <= MAX_INDEX_FRAMES,
            "Missing/too many decoded frames")
    pts_list = []
    previous = -math.inf
    for row in rows:
        require(type(row) is dict and "best_effort_timestamp_time" in row,
                "Frame missing PTS")
        try:
            pts = float(row["best_effort_timestamp_time"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid indexed frame PTS") from exc
        require(math.isfinite(pts) and -1 <= pts <= duration + 1 and
                pts >= previous, "Invalid/non-monotonic indexed frame PTS")
        pts_list.append(pts)
        previous = pts
    return pts_list


def seek_video_frames(video: Path, indices: list[int], work: Path, duration: float,
                      *, diagnostics: dict | None = None):
    """Return absolute frame index -> (PNG, validated PTS) with bounded seeks."""
    require(indices and indices == sorted(set(indices)) and
            all(type(i) is int and i >= 0 for i in indices), "Invalid frame indices")
    indexed_pts = frame_pts_index(video, duration)
    require(indices[-1] < len(indexed_pts), "Frame index beyond recording")
    output = {}
    if diagnostics is not None:
        diagnostics["full_decode_fallbacks"] = 0
    for order, index in enumerate(indices, start=1):
        pts_expected = indexed_pts[index]
        require(pts_expected >= 0, "Negative indexed frame PTS unsupported")
        frame = work / f"frame_{order:03d}.png"

        def decode(*, fallback: bool) -> float | None:
            # Some MPEG-4/B-frame GOPs seek to the *next* keyframe, skipping
            # the requested presentation timestamp. Detect that case and
            # conservatively decode from the beginning as a correctness fallback.
            # A fallback is not a sparse-seek performance win.
            if fallback:
                args = ["-noautorotate", "-i", str(video), "-map", "0:v:0",
                        "-an", "-sn", "-dn",
                        "-vf", f"select=gte(t\\,{max(0.0, pts_expected - 0.0001):.9f}),showinfo"]
            else:
                args = ["-ss", f"{pts_expected:.9f}", "-copyts", "-noautorotate",
                        "-i", str(video), "-map", "0:v:0", "-an", "-sn", "-dn",
                        "-vf", "showinfo"]
            result = run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info",
                          *args, "-frames:v", "1", "-fps_mode", "passthrough",
                          "-f", "image2", "-vcodec", "png", "-y", str(frame)], 120)
            lines = [line for line in result.stderr.decode("utf-8", "replace").splitlines()
                     if "Parsed_showinfo" in line and "pts_time:" in line]
            require(len(lines) == 1, "Cannot establish unique sought frame PTS")
            match = PTS_RE.search(lines[0])
            require(match is not None, "Missing sought frame PTS")
            return float(match.group(1))

        actual_pts = decode(fallback=False)
        if not math.isfinite(actual_pts) or abs(actual_pts - pts_expected) > FRAME_TOLERANCE_SECONDS:
            if diagnostics is not None:
                diagnostics["full_decode_fallbacks"] += 1
            actual_pts = decode(fallback=True)
        require(math.isfinite(actual_pts) and
                abs(actual_pts - pts_expected) <= FRAME_TOLERANCE_SECONDS,
                "Seek and full-decode fallback returned wrong frame PTS")
        require(frame.is_file() and not frame.is_symlink() and
                0 < frame.stat().st_size <= MAX_FULL_FRAME_BYTES and
                frame.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n",
                "Invalid sought frame PNG")
        output[index] = (frame, actual_pts)
    return output


def main(argv=None):
    from offline_ffmpeg_batch_frame_provenance import create
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recorded_video")
    parser.add_argument("ledger_report_json")
    parser.add_argument("frame_requests_json")
    parser.add_argument("new_output_directory")
    args = parser.parse_args(argv)
    manifest = create(args.recorded_video, args.ledger_report_json,
                      args.frame_requests_json, args.new_output_directory,
                      strategy="indexed_seek")
    print(json.dumps({"frames": len(manifest["observations"]),
                      "source_sha256": manifest["source_recording_sha256"],
                      "strategy": "indexed_seek"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
