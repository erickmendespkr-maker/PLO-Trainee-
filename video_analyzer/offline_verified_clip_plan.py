"""Build conservative MP4 clip plans from human-confirmed intervals only."""
import hashlib
import math

def plan_clips(report, duration, crops, before=2.0, after=2.0):
    if report.get("analysis_verified") is not False:
        raise ValueError("analysis verification must remain false")
    sha = report.get("source_video_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha.lower()):
        raise ValueError("invalid source hash")
    for value in (duration, before, after):
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("invalid time")
    if duration == 0:
        raise ValueError("empty video")
    clips = []
    seen = set()
    for hand in report.get("intervals", []):
        if hand.get("boundary_status") != "HUMAN_CONFIRMED":
            raise ValueError("unverified hand boundary")
        table = hand.get("table_id")
        box = crops.get(str(table))
        if type(table) is not int or table not in range(1, 5) or not isinstance(box, (list, tuple)) or len(box) != 4 or any(type(v) is not int or v < 0 for v in box) or min(box[2:]) == 0:
            raise ValueError("invalid table crop")
        start, end = hand.get("start_pts_seconds"), hand.get("end_pts_seconds")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)) or not 0 <= start < end <= duration:
            raise ValueError("invalid interval")
        key = (table, start, end)
        if key in seen:
            raise ValueError("duplicate interval")
        seen.add(key)
        digest = hashlib.sha256(f"{sha}:{table}:{start:.6f}:{end:.6f}".encode()).hexdigest()[:20]
        clips.append({"hand_id": digest, "table_id": table,
            "clip_start_seconds": round(max(0, start-before), 6),
            "clip_end_seconds": round(min(duration, end+after), 6),
            "crop_xywh": list(box),
            "filename": f"table_{table}_hand_{digest}_REVIEW.mp4",
            "boundaries_verified": True, "strategy_verified": False,
            "analysis_label": "INSUFFICIENT_DATA"})
    return {"schema_version": 1, "source_video_sha256": sha,
        "clip_plans": clips, "unresolved_boundaries": report.get("unresolved_boundaries", []),
        "analysis_verified": False}
