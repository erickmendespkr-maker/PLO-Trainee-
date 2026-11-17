"""Conservative FFprobe audit of rendered offline candidate clips."""
import json
import math
import subprocess

def probe_video(path, timeout=30):
    if not isinstance(path, str) or not path.strip():
        raise ValueError("video path required")
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,width,height", "-of", "json", path],
        capture_output=True, text=True, check=True, timeout=timeout)
    return json.loads(result.stdout)

def audit_render(clip, probe, tolerance_seconds=0.25):
    """Container checks only; not proof of correct footage or source PTS."""
    if not isinstance(clip, dict) or not isinstance(probe, dict):
        raise ValueError("clip and probe must be mappings")
    if clip.get("review_status") != "pending_human_review" or clip.get("strategic_analysis_status") != "insufficient_verified_evidence":
        raise ValueError("candidate-only audit")
    start, end = clip.get("start_seconds"), clip.get("end_seconds")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end, tolerance_seconds)):
        raise ValueError("invalid interval")
    if start < 0 or end <= start or tolerance_seconds < 0 or tolerance_seconds > 2:
        raise ValueError("invalid interval or tolerance")
    streams = probe.get("streams")
    if not isinstance(streams, list) or not any(isinstance(s, dict) and s.get("codec_type") == "video" and type(s.get("width")) is int and s["width"] > 0 and type(s.get("height")) is int and s["height"] > 0 for s in streams):
        raise ValueError("missing video stream")
    try:
        duration = float(probe["format"]["duration"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("missing duration") from exc
    if not math.isfinite(duration) or duration <= 0 or abs(duration-(end-start)) > tolerance_seconds:
        raise ValueError("rendered duration invalid")
    return {"clip_id": clip.get("clip_id"), "expected_seconds": end-start,
            "actual_seconds": duration, "duration_delta_seconds": duration-(end-start),
            "video_stream_present": True, "review_status": "pending_human_review",
            "strategic_analysis_status": "insufficient_verified_evidence",
            "content_verified": False, "pts_verified": False}
