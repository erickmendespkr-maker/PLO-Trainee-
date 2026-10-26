"""Conservative offline audit of the last decoded frames in recorded clips.

Compares short grayscale tails from an authorized recording and exported MP4.
Reports *possible* missing/duplicated terminal frames; it never proves clip
provenance, card/action recognition, or equity/EV validity. No video is edited.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess

WIDTH, HEIGHT = 160, 90
FRAME_BYTES = WIDTH * HEIGHT
TAIL_SECONDS = 2
MAX_TAIL_FRAMES = 360
MAX_VIDEO_BYTES = 12 * 1024**3
MAX_DURATION_SECONDS = 7200
MATCH_MAE = 8.0
STATIC_MAE = 1.5
MOTION_MAE = 4.0


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _run(command: list[str], timeout: int = 120) -> bytes:
    try:
        return subprocess.run(command, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              check=True, timeout=timeout).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError) as exc:
        raise ValueError(f"FFmpeg/FFprobe failed: {type(exc).__name__}") from exc


def _hash_regular(path: Path) -> str:
    require(path.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm"),
            "Unsupported video extension")
    require(path.is_file() and not path.is_symlink(), "Unsafe video path")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_VIDEO_BYTES,
                "Unsafe video size/type")
        digest = hashlib.sha256()
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
        after = os.fstat(handle.fileno())
        require((before.st_size, before.st_mtime_ns, before.st_ino) ==
                (after.st_size, after.st_mtime_ns, after.st_ino),
                "Video changed while hashing")
    return digest.hexdigest()


def _duration(path: Path) -> float:
    data = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)], 60)
    try:
        value = float(data.strip())
    except ValueError as exc:
        raise ValueError("Unknown video duration") from exc
    require(math.isfinite(value) and 0 < value <= MAX_DURATION_SECONDS,
            "Unsupported video duration")
    return value


def _tail_frames(path: Path) -> list[bytes]:
    # Input-side seek from EOF; no frame-rate conversion or frame interpolation.
    raw = _run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
                "-sseof", f"-{TAIL_SECONDS}", "-noautorotate", "-i", str(path),
                "-map", "0:v:0", "-an", "-sn", "-dn",
                "-vf", f"scale={WIDTH}:{HEIGHT}:flags=bilinear,format=gray",
                "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
               120)
    require(0 < len(raw) <= FRAME_BYTES * MAX_TAIL_FRAMES and
            len(raw) % FRAME_BYTES == 0,
            "Missing, malformed, or excessive decoded tail frames")
    return [raw[i:i + FRAME_BYTES] for i in range(0, len(raw), FRAME_BYTES)]


def frame_mae(a: bytes, b: bytes) -> float:
    require(len(a) == len(b) == FRAME_BYTES, "Unexpected thumbnail shape")
    return sum(abs(x - y) for x, y in zip(a, b)) / FRAME_BYTES


def analyze_tail_frames(source_frames: list[bytes], clip_frames: list[bytes]) -> dict:
    """Pure analysis, testable without FFmpeg. No probabilistic confidence claim."""
    require(1 <= len(source_frames) <= MAX_TAIL_FRAMES and
            1 <= len(clip_frames) <= MAX_TAIL_FRAMES, "Empty/oversized tail")
    for frame in source_frames + clip_frames:
        require(type(frame) is bytes and len(frame) == FRAME_BYTES,
                "Invalid decoded tail frame")
    src, dst = source_frames[-8:], clip_frames[-8:]
    terminal_mae = frame_mae(src[-1], dst[-1])
    src_motion = frame_mae(src[-2], src[-1]) if len(src) >= 2 else None
    clip_motion = frame_mae(dst[-2], dst[-1]) if len(dst) >= 2 else None
    pair_count = min(len(src), len(dst))
    paired_errors = [frame_mae(src[-i], dst[-i]) for i in range(1, pair_count + 1)]
    # Earlier source frames can resemble the terminal clip frame even when the
    # source has static content. Only flag missing frames if terminal motion is
    # clear AND the best match is not the source's last frame.
    candidate_errors = [frame_mae(frame, dst[-1]) for frame in src]
    closest_index = min(range(len(src)), key=lambda i: candidate_errors[i])
    closest_offset_from_end = len(src) - 1 - closest_index
    potential_missing = (len(src) >= 3 and src_motion is not None and
                         src_motion > MOTION_MAE and terminal_mae > MATCH_MAE and
                         closest_offset_from_end >= 1 and
                         candidate_errors[closest_index] <= MATCH_MAE)
    potential_duplicate = (len(src) >= 2 and len(dst) >= 2 and
                           src_motion is not None and clip_motion is not None and
                           src_motion > MOTION_MAE and clip_motion <= STATIC_MAE and
                           terminal_mae <= MATCH_MAE)
    # Static source material or ambiguous compression cannot be called clean.
    insufficient_motion = src_motion is None or src_motion <= MOTION_MAE
    if potential_duplicate and potential_missing:
        classification = "multiple_possible_terminal_anomalies"
    elif potential_duplicate:
        classification = "possible_added_terminal_duplicate"
    elif potential_missing:
        classification = "possible_missing_terminal_frames"
    elif insufficient_motion:
        classification = "indeterminate_static_or_insufficient_source_motion"
    elif terminal_mae <= MATCH_MAE and max(paired_errors[:min(3, pair_count)]) <= MATCH_MAE:
        classification = "no_anomaly_detected_in_compared_tail"
    else:
        classification = "indeterminate_terminal_difference"
    return {
        "classification": classification,
        "source_tail_frames_decoded": len(source_frames),
        "clip_tail_frames_decoded": len(clip_frames),
        "frames_compared_from_end": pair_count,
        "terminal_frame_mae_0_to_255": round(terminal_mae, 6),
        "source_terminal_motion_mae": None if src_motion is None else round(src_motion, 6),
        "clip_terminal_motion_mae": None if clip_motion is None else round(clip_motion, 6),
        "last_three_aligned_mae": [round(x, 6) for x in paired_errors[:3]],
        "closest_source_tail_frame_offset_from_end": closest_offset_from_end,
        "closest_source_tail_frame_mae": round(candidate_errors[closest_index], 6),
        "possible_added_terminal_duplicate": bool(potential_duplicate),
        "possible_missing_terminal_frames": bool(potential_missing),
        "source_terminal_motion_sufficient_for_diagnostic": not insufficient_motion,
    }


def audit(source: str | Path, clip: str | Path, requested_start_seconds: float) -> dict:
    require(type(requested_start_seconds) in (int, float) and
            math.isfinite(requested_start_seconds) and requested_start_seconds >= 0,
            "Invalid requested start")
    src_path, clip_path = Path(source), Path(clip)
    src_hash, clip_hash = _hash_regular(src_path), _hash_regular(clip_path)
    require(src_hash != clip_hash, "Source and clip are identical")
    src_duration, clip_duration = _duration(src_path), _duration(clip_path)
    require(requested_start_seconds < src_duration, "Start beyond recording")
    src_tail = _tail_frames(src_path)
    clip_tail = _tail_frames(clip_path)
    details = analyze_tail_frames(src_tail, clip_tail)
    require(_hash_regular(src_path) == src_hash and
            _hash_regular(clip_path) == clip_hash,
            "Video changed during tail audit")
    return {
        "schema_version": 1,
        "status": "terminal_sequence_diagnostic_only",
        "source_sha256": src_hash,
        "clip_sha256": clip_hash,
        "requested_start_seconds": requested_start_seconds,
        "source_container_duration_seconds": src_duration,
        "clip_container_duration_seconds": clip_duration,
        "container_duration_difference_seconds": round(
            clip_duration - (src_duration - requested_start_seconds), 6),
        "tail_window_seconds": TAIL_SECONDS,
        "thumbnail_dimensions": [WIDTH, HEIGHT],
        "heuristic_thresholds_mae": {"match": MATCH_MAE, "static": STATIC_MAE,
                                     "motion": MOTION_MAE},
        **details,
        "visual_provenance_verified": False,
        "ocr_verified": False,
        "equity_ev_authorized": False,
        "limitations": [
            "Heuristic pixel differences are not calibrated probabilities.",
            "Container duration is diagnostic; for packet-PTS timing use the existing end audit.",
            "Only the last 2 seconds are decoded; repeated/static content can be ambiguous.",
            "Lossy encoding, scaling, overlays and FPS conversion can change comparisons.",
            "A detected anomaly is not proof; a clean result does not rule out dropped/duplicated frames.",
            "No OCR, cards, actions, hand reconstruction, equity or EV is validated.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_recording")
    parser.add_argument("exported_clip")
    parser.add_argument("requested_start_seconds", type=float)
    parser.add_argument("new_report_json")
    args = parser.parse_args(argv)
    target = Path(args.new_report_json)
    require(target.parent.is_dir() and not target.parent.is_symlink() and
            not target.exists() and not target.is_symlink(), "Unsafe output path")
    report = audit(args.source_recording, args.exported_clip,
                   args.requested_start_seconds)
    with target.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"classification": report["classification"],
                      "possible_duplicate": report["possible_added_terminal_duplicate"],
                      "possible_missing": report["possible_missing_terminal_frames"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())