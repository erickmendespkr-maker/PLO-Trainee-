"""Audit MP4 container and decoding without claiming source timeline or hand correctness."""
import json
import math
import subprocess
from pathlib import Path
from offline_clip_evidence_manifest import clip_sha256


def audit_clip(manifest, clip_path, ffprobe="ffprobe", ffmpeg="ffmpeg", tolerance_seconds=0.35):
    if not isinstance(manifest, dict) or manifest.get("status") != "PENDING_INDEPENDENT_AUDIT" or manifest.get("approved_for_publication") is not False:
        raise ValueError("pending unapproved manifest required")
    clip = manifest.get("clip")
    if not isinstance(clip, dict):
        raise ValueError("clip metadata missing")
    path = Path(clip_path)
    if clip_sha256(path) != clip.get("sha256"):
        raise ValueError("clip hash mismatch")
    start, end = clip.get("start_seconds"), clip.get("end_seconds")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)) or not 0 <= start < end:
        raise ValueError("invalid source interval")
    if type(tolerance_seconds) not in (int, float) or not math.isfinite(tolerance_seconds) or not 0 <= tolerance_seconds <= 1:
        raise ValueError("invalid tolerance")
    try:
        probe = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration:stream=index,codec_type,width,height", "-of", "json", str(path)], capture_output=True, text=True, timeout=30, check=True)
        info = json.loads(probe.stdout)
        duration = float(info["format"]["duration"])
    except (subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("ffprobe failed or returned invalid metadata") from exc
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == "video" and type(s.get("width")) is int and type(s.get("height")) is int and s["width"] > 0 and s["height"] > 0]
    if not math.isfinite(duration) or duration <= 0 or not streams:
        raise ValueError("missing valid video stream or duration")
    if abs(duration - (end - start)) > tolerance_seconds:
        raise ValueError("duration differs from requested source interval")
    try:
        subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"], capture_output=True, timeout=120, check=True)
    except subprocess.SubprocessError as exc:
        raise ValueError("video decode failed") from exc
    return {"status": "CONTAINER_AND_DECODE_VERIFIED_ONLY", "approved_for_publication": False,
            "sha256": clip["sha256"], "duration_seconds": duration,
            "video_width": streams[0]["width"], "video_height": streams[0]["height"],
            "source_timeline_verified": False, "visual_hand_verified": False,
            "ev_verified": False, "required_next_checks": ["source_pts_alignment", "independent_ledger_authentication", "visual_hand_review", "ev_evidence_gate"]}
