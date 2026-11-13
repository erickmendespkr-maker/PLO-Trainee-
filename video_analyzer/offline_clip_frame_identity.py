"""Exact decoded RGB frame identity check for short offline proof-of-concept videos.

Not a semantic hand validator; lossy transcodes may differ.
"""
import hashlib
import json
import subprocess
from pathlib import Path


def _run(args):
    return subprocess.run(args, check=True, capture_output=True, timeout=90).stdout


def _frames(path, limit):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular video file required")
    data = json.loads(_run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height", "-of", "json", str(path)]))
    streams = data.get("streams", [])
    if len(streams) != 1:
        raise ValueError("one video stream required")
    w, h = streams[0]["width"], streams[0]["height"]
    if not (1 <= w <= 640 and 1 <= h <= 480):
        raise ValueError("dimensions outside synthetic proof-of-concept limit")
    raw = _run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0",
                "-frames:v", str(limit + 1), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    frame_bytes = w * h * 3
    if not raw or len(raw) % frame_bytes or len(raw) // frame_bytes > limit:
        raise ValueError("invalid or excessive frames")
    return (w, h), [hashlib.sha256(raw[i:i + frame_bytes]).hexdigest()
                    for i in range(0, len(raw), frame_bytes)]


def audit_exact_frames(source_path, clip_path, *, source_first_frame, max_frames=60):
    """Compare contiguous decoded frames; never approve a poker hand automatically."""
    if type(source_first_frame) is not int or not 0 <= source_first_frame <= 300:
        raise ValueError("invalid source index")
    if type(max_frames) is not int or not 1 <= max_frames <= 60:
        raise ValueError("invalid frame limit")
    source_dims, source = _frames(source_path, source_first_frame + max_frames)
    clip_dims, clip = _frames(clip_path, max_frames)
    if source_dims != clip_dims:
        raise ValueError("resolution mismatch")
    selected = source[source_first_frame:source_first_frame + len(clip)]
    if len(selected) != len(clip):
        raise ValueError("source interval too short")
    mismatch = sum(a != b for a, b in zip(selected, clip))
    return {"status": "EXACT_DECODED_FRAMES_MATCH" if not mismatch else "FRAME_CONTENT_MISMATCH",
            "source_first_frame": source_first_frame, "clip_frames": len(clip),
            "mismatch_count": mismatch, "matching_frames": len(clip) - mismatch,
            "visual_hand_verified": False, "ev_verified": False,
            "approved_for_publication": False,
            "limitations": ["exact_pixels_only", "no_semantic_hand_validation",
                            "lossy_transcodes_may_differ", "short_synthetic_inputs_only"]}
