"""Conservative draft clip windows from reviewed timeline ledgers; no media export."""
import math


def draft_clip_windows(ledger, *, duration_s, padding_s=3.0):
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (duration_s, padding_s)):
        raise ValueError("duration and padding must be finite numbers")
    if duration_s <= 0 or padding_s < 0:
        raise ValueError("duration must be positive and padding nonnegative")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("hands"), list):
        raise ValueError("ledger must contain hands")
    drafts = []
    for index, hand in enumerate(ledger["hands"]):
        if not isinstance(hand, dict):
            drafts.append({"hand_index": index, "status": "REVIEW_REQUIRED", "reason": "INVALID_HAND"})
            continue
        start, end = hand.get("start_s"), hand.get("end_s")
        valid = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (start, end))
        if not valid or start < 0 or end <= start or end > duration_s:
            drafts.append({"hand_index": index, "status": "REVIEW_REQUIRED", "reason": "INVALID_INTERVAL"})
            continue
        issues = list(hand.get("timeline_issue_codes") or [])
        drafts.append({"hand_index": index, "table_id": hand.get("table_id"),
                       "start_s": max(0.0, start - padding_s),
                       "end_s": min(duration_s, end + padding_s),
                       "status": "DRAFT_REVIEW_ONLY", "hand_boundaries_verified": False,
                       "strategic_analysis_verified": False,
                       "reason": "TIMELINE_ISSUES" if issues else "REQUIRES_VISUAL_REVIEW",
                       "timeline_issue_codes": issues})
    return {"schema_version": 1, "source_video_sha256": ledger.get("source_video_sha256"),
            "video_duration_s": duration_s, "clips": drafts, "exported": False,
            "video_visual_accuracy_verified": False}
