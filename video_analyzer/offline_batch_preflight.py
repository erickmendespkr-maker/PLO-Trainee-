"""Fail-closed, non-exporting preflight for offline PLO review clip plans."""
import math
from pathlib import Path

def finite(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite numeric")
    return float(value)

def preflight_batch(plan, video_duration, *, max_clips=200, max_total_seconds=1800):
    """Validate proposed clips; recheck media/destinations before actual FFmpeg export."""
    duration = finite(video_duration, "video_duration")
    budget = finite(max_total_seconds, "max_total_seconds")
    if duration <= 0 or budget <= 0:
        raise ValueError("durations must be positive")
    if type(max_clips) is not int or max_clips < 1:
        raise ValueError("invalid max_clips")
    if not isinstance(plan, list) or len(plan) > max_clips:
        raise ValueError("invalid plan size")
    seen, total, checked = set(), 0.0, []
    for item in plan:
        if not isinstance(item, dict) or item.get("status") != "PLANNED_ONLY" or item.get("human_review_required") is not True:
            raise ValueError("only provisional review plans accepted")
        record = item.get("record")
        if not isinstance(record, dict):
            raise ValueError("missing record")
        table = record.get("table_id")
        if type(table) is not int or not 1 <= table <= 4:
            raise ValueError("invalid table")
        if any(record.get(flag) is not False for flag in ("table_verified", "hand_verified", "hero_cards_verified", "board_verified", "action_verified", "amounts_verified")):
            raise ValueError("unexpected verified evidence")
        start = finite(record.get("start_pts"), "start_pts")
        end = finite(record.get("end_pts"), "end_pts")
        if start < 0 or end <= start or end > duration + 1e-7:
            raise ValueError("interval outside source")
        destination = item.get("destination")
        if not isinstance(destination, str) or not destination.strip():
            raise ValueError("invalid destination")
        target = Path(destination)
        if target.suffix.lower() != ".mp4" or str(target) in seen:
            raise ValueError("invalid or duplicate destination")
        if target.exists() or target.with_suffix(".json").exists():
            raise FileExistsError(str(target))
        seen.add(str(target))
        total += end - start
        if total > budget + 1e-7:
            raise ValueError("clip duration budget exceeded")
        checked.append({"destination": str(target), "table_id": table, "start_pts": start,
                        "end_pts": end, "status": "PREFLIGHT_ONLY", "human_review_required": True})
    return {"clips": checked, "total_seconds": total, "status": "NOT_EXPORTED",
            "human_review_required": True}
