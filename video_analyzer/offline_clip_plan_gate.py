"""Offline-only MP4 clip plan validation. Does not execute FFmpeg."""
import math
from pathlib import Path

def plan_clip(video_sha256, table_id, hand_id, start_seconds, end_seconds,
              duration_seconds, review_status, output_name):
    if not isinstance(video_sha256, str) or len(video_sha256) != 64 or any(c not in "0123456789abcdef" for c in video_sha256):
        raise ValueError("invalid video SHA-256")
    if type(table_id) is not int or not 1 <= table_id <= 4:
        raise ValueError("invalid table")
    if not isinstance(hand_id, str) or not hand_id.strip():
        raise ValueError("invalid hand ID")
    times = (start_seconds, end_seconds, duration_seconds)
    if any(type(t) not in (int, float) or not math.isfinite(t) for t in times):
        raise ValueError("invalid timestamps")
    if not 0 <= start_seconds < end_seconds <= duration_seconds:
        raise ValueError("clip outside source duration")
    if review_status not in ("confirmed", "insufficient_data"):
        raise ValueError("unknown review status")
    if (not isinstance(output_name, str) or len(output_name) > 128 or
            not output_name.endswith(".mp4") or output_name in (".mp4", "..mp4") or
            Path(output_name).name != output_name or "/" in output_name or
            "\\" in output_name or any(ord(c) < 32 for c in output_name)):
        raise ValueError("unsafe output name")
    return {
        "source_sha256": video_sha256,
        "table_id": table_id,
        "hand_id": hand_id,
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "duration_seconds": end_seconds - start_seconds,
        "output_name": output_name,
        "review_status": review_status,
        "strategic_verdict_allowed": False,
        "annotation": "CONDITIONAL MODEL ONLY" if review_status == "confirmed" else "INSUFFICIENT_DATA",
    }
