"""Offline reviewed-hand clip gate; no automatic export or live poker connectivity."""
import hashlib
import json
import math


def build_reviewed_clip_plan(record: dict, duration_seconds: float) -> dict:
    """Create a non-executing clip plan only after explicit human review."""
    if not isinstance(record, dict):
        raise ValueError("record must be a dict")
    if type(duration_seconds) not in (int, float) or not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("invalid video duration")
    hand_id = record.get("hand_id")
    if not isinstance(hand_id, str) or not hand_id.strip() or len(hand_id) > 128:
        raise ValueError("invalid hand id")
    table = record.get("table_id")
    if type(table) is not int or not 1 <= table <= 4:
        raise ValueError("table must be 1..4")
    start, end = record.get("start_pts"), record.get("end_pts")
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in (start, end)):
        raise ValueError("timestamps must be finite numbers")
    if not 0 <= start < end <= duration_seconds:
        raise ValueError("timestamps outside recording")
    sha = record.get("video_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("invalid video sha256")
    if record.get("human_reviewed") is not True or record.get("hand_boundary_confirmed") is not True:
        return {"status": "REVIEW_REQUIRED", "hand_id": hand_id, "table_id": table, "reason": "unconfirmed hand boundaries or review"}
    if record.get("explanation_verified") is not True:
        return {"status": "REVIEW_REQUIRED", "hand_id": hand_id, "table_id": table, "reason": "explanation not verified"}
    note = record.get("explanation")
    if not isinstance(note, str) or not note.strip() or len(note) > 2000:
        raise ValueError("invalid explanation")
    plan = {"status": "READY_FOR_OFFLINE_EXPORT", "hand_id": hand_id, "table_id": table,
            "start_pts": float(start), "end_pts": float(end), "video_sha256": sha,
            "explanation": note, "conditional_model_only": True,
            "not_gto": True, "requires_source_hash_check": True}
    plan["manifest_sha256"] = hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return plan
