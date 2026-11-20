"""Conservative review status gate for offline PLO video intervals.

No strategy verdict is derived from OCR proposals.
"""
import math


def review_gate(interval):
    """Return a machine-readable decision; never silently approve an OCR proposal."""
    if not isinstance(interval, dict):
        return {"allowed": False, "reason": "INVALID_RECORD"}
    required = ("video_sha256", "table_id", "start_s", "end_s", "hand_id")
    if any(key not in interval for key in required):
        return {"allowed": False, "reason": "MISSING_EVIDENCE"}
    sha = interval["video_sha256"]
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        return {"allowed": False, "reason": "INVALID_VIDEO_HASH"}
    table = interval["table_id"]
    if type(table) is not int or table not in (1, 2, 3, 4):
        return {"allowed": False, "reason": "INVALID_TABLE"}
    a, b = interval["start_s"], interval["end_s"]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (a, b)) or not 0 <= a < b:
        return {"allowed": False, "reason": "INVALID_TIMESTAMPS"}
    if not isinstance(interval["hand_id"], str) or not interval["hand_id"].strip():
        return {"allowed": False, "reason": "INVALID_HAND_ID"}
    if interval.get("status") != "reviewed" or not isinstance(interval.get("reviewer"), str) or not interval["reviewer"].strip():
        return {"allowed": False, "reason": "REVIEW_REQUIRED"}
    if interval.get("source") == "synthetic":
        return {"allowed": False, "reason": "SYNTHETIC_NOT_REAL_EVIDENCE"}
    return {"allowed": True, "reason": "HUMAN_REVIEWED_INTERVAL_ONLY"}
