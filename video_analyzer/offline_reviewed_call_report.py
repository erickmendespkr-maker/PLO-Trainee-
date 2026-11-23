"""Offline evidence gate for conditional call-EV reports; never a GTO verdict."""
import math
from .offline_call_range_sensitivity import evaluate_call_scenarios

_REQUIRED = ("video_sha256", "hand_id", "table_id", "start_pts", "end_pts",
             "hole_cards_verified", "board_verified", "action_verified",
             "pot_verified", "call_cost_verified", "reviewed_by_human")


def build_reviewed_call_report(evidence, pot_before_call, call_cost, scenarios):
    """Withhold EV until all required video evidence is human-reviewed."""
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be a dictionary")
    missing = [key for key in _REQUIRED if key not in evidence]
    if missing:
        return {"status": "INSUFFICIENT_DATA", "missing_fields": missing,
                "strategic_verdict": "NOT_ESTABLISHED", "analysis": None}
    sha = evidence["video_sha256"]
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("video_sha256 must be lowercase SHA-256 hex")
    if not isinstance(evidence["hand_id"], str) or not evidence["hand_id"].strip():
        raise ValueError("hand_id required")
    table = evidence["table_id"]
    if isinstance(table, bool) or not isinstance(table, int) or table not in range(1, 5):
        raise ValueError("table_id must be 1-4")
    start, end = evidence["start_pts"], evidence["end_pts"]
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in (start, end)) or not 0 <= start < end:
        raise ValueError("invalid PTS interval")
    flags = _REQUIRED[5:]
    if any(evidence[k] is not True for k in flags):
        return {"status": "INSUFFICIENT_DATA",
                "missing_fields": [k for k in flags if evidence[k] is not True],
                "strategic_verdict": "NOT_ESTABLISHED", "analysis": None,
                "hand_id": evidence["hand_id"], "table_id": table}
    analysis = evaluate_call_scenarios(pot_before_call, call_cost, scenarios)
    return {"status": "CONDITIONAL_MODEL_ONLY", "hand_id": evidence["hand_id"],
            "table_id": table, "video_sha256": sha, "pts": [float(start), float(end)],
            "analysis": analysis, "strategic_verdict": "NOT_ESTABLISHED",
            "range_source": "USER_SUPPLIED_HYPOTHESES", "gto_solution": False}
