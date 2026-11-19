"""Offline FFprobe preflight for human-reviewed video clips; no poker inference."""
import json
import math
import subprocess

def probe_video(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    duration = float(data["format"]["duration"])
    video = next((s for s in data.get("streams", [])
                  if s.get("codec_type") == "video"), None)
    if video is None or not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid video")
    width, height = int(video["width"]), int(video["height"])
    if width <= 0 or height <= 0:
        raise ValueError("invalid dimensions")
    return {"duration_seconds": duration, "width": width, "height": height}

def validate_reviewed_interval(metadata, start, end, crop=None, reviewed=False):
    if reviewed is not True:
        raise ValueError("human review required")
    if type(start) not in (int, float) or type(end) not in (int, float):
        raise ValueError("invalid timestamps")
    if not math.isfinite(start) or not math.isfinite(end):
        raise ValueError("nonfinite timestamps")
    if start < 0 or end <= start or end > metadata["duration_seconds"] + 0.02:
        raise ValueError("interval outside video")
    if crop is not None:
        if (not isinstance(crop, (tuple, list)) or len(crop) != 4
                or any(type(v) is not int for v in crop)):
            raise ValueError("invalid crop")
        x, y, w, h = crop
        if (min(x, y) < 0 or min(w, h) <= 0 or
                x + w > metadata["width"] or y + h > metadata["height"]):
            raise ValueError("crop outside frame")
    return {"start_seconds": start, "end_seconds": end,
            "crop": list(crop) if crop is not None else None,
            "human_reviewed_interval": True,
            "hand_reconstruction_verified": False,
            "equity_ev_verified": False,
            "outcome_verified": False}
