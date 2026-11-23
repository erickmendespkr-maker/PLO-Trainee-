"""Conservative timeline-aware review ledger; no strategic assertions.

Combines existing evidence and temporal checks without modifying input history.
"""
import copy

try:
    from .offline_review_history import build_review_history
    from .offline_review_timeline import audit_review_timeline
except ImportError:
    from offline_review_history import build_review_history
    from offline_review_timeline import audit_review_timeline


def build_timeline_review(video_sha256, hands, *, duration_s, minimum_confidence=0.90):
    """Return a review ledger where timeline warnings block conditional analysis.

    Timeline plausibility alone does not verify hand boundaries. Original gate
    results are retained under evidence_gate_allowed for auditability.
    """
    history = build_review_history(
        video_sha256, hands, minimum_confidence=minimum_confidence
    )
    audit = audit_review_timeline(history, duration_s=duration_s)
    result = copy.deepcopy(history)
    affected = set()
    for issue in audit["issues"]:
        affected.add(issue["hand_index"])
        if issue["code"] == "SAME_TABLE_OVERLAP":
            affected.add(issue["other_hand_index"])
    by_hand = {}
    for issue in audit["issues"]:
        by_hand.setdefault(issue["hand_index"], []).append(issue["code"])
        if issue["code"] == "SAME_TABLE_OVERLAP":
            by_hand.setdefault(issue["other_hand_index"], []).append(issue["code"])
    for index, hand in enumerate(result["hands"]):
        original = hand["conditional_analysis_allowed"]
        hand["evidence_gate_allowed"] = original
        hand["timeline_issue_codes"] = sorted(set(by_hand.get(index, [])))
        if index in affected:
            hand["conditional_analysis_allowed"] = False
            hand["status"] = "REVIEW_REQUIRED"
        hand["hand_boundaries_verified"] = False
    result["timeline_audit"] = audit
    result["summary"]["ready_for_conditional_analysis"] = sum(
        bool(h["conditional_analysis_allowed"]) for h in result["hands"]
    )
    result["summary"]["insufficient_data"] = sum(
        not h["conditional_analysis_allowed"] for h in result["hands"]
    )
    result["summary"]["timeline_review_required"] = len(affected)
    return result
