"""Deterministic provenance audit for recorded PLO hands; not a strategic verdict."""
import hashlib
import json
import math
from pathlib import Path

def _number(value):
    return type(value) in (int, float) and math.isfinite(value)

def validate_hand_evidence(hand, *, video_sha256, duration_seconds):
    if not isinstance(video_sha256, str) or len(video_sha256) != 64 or any(c not in "0123456789abcdef" for c in video_sha256):
        raise ValueError("video_sha256 must be lowercase SHA-256 hex")
    if not _number(duration_seconds) or duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive and finite")
    if not isinstance(hand, dict):
        raise ValueError("hand must be a dictionary")
    reasons = []
    hand_id = hand.get("hand_id")
    if not isinstance(hand_id, str) or not hand_id.strip():
        reasons.append("HAND_ID_MISSING")
    table = hand.get("table_id")
    if type(table) is not int or table not in (1, 2, 3, 4):
        reasons.append("TABLE_ID_INVALID")
    start, end = hand.get("start_pts"), hand.get("end_pts")
    if not _number(start) or not _number(end) or not (0 <= start < end <= duration_seconds):
        reasons.append("PTS_OUT_OF_BOUNDS")
    fields = ("hole_cards_verified", "board_verified", "action_verified", "pot_verified", "call_cost_verified", "reviewed_by_human")
    reasons.extend("UNVERIFIED_" + field.upper() for field in fields if hand.get(field) is not True)
    if hand.get("video_sha256") != video_sha256:
        reasons.append("VIDEO_SHA_MISMATCH")
    return {"hand_id": hand_id if isinstance(hand_id, str) else None,
            "table_id": table if type(table) is int else None,
            "start_pts": start if _number(start) else None,
            "end_pts": end if _number(end) else None,
            "status": "REVIEWED_EVIDENCE" if not reasons else "INSUFFICIENT_DATA",
            "reasons": reasons, "strategic_verdict": "NOT_ESTABLISHED"}

def build_manifest(video_path, hands, *, duration_seconds, expected_sha256=None):
    """Stream SHA-256 of local footage; audit hands without inferring hidden information."""
    if not isinstance(hands, list):
        raise ValueError("hands must be a list")
    digest = hashlib.sha256()
    with Path(video_path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    sha = digest.hexdigest()
    if expected_sha256 is not None and expected_sha256 != sha:
        raise ValueError("video SHA-256 mismatch")
    audited = [validate_hand_evidence(hand, video_sha256=sha, duration_seconds=duration_seconds) for hand in hands]
    # Reject every occurrence of an ambiguous (table, hand) identifier.
    # Otherwise the first duplicate would remain incorrectly approved.
    counts = {}
    for entry in audited:
        key = (entry["table_id"], entry["hand_id"].strip() if isinstance(entry["hand_id"], str) and entry["hand_id"].strip() else None)
        counts[key] = counts.get(key, 0) + 1
    for entry in audited:
        key = (entry["table_id"], entry["hand_id"].strip() if isinstance(entry["hand_id"], str) and entry["hand_id"].strip() else None)
        if counts[key] > 1:
            entry["status"] = "INSUFFICIENT_DATA"
            entry["reasons"].append("DUPLICATE_HAND_ID")
    # Two reviewed hands cannot occupy overlapping intervals on the same table.
    # A collision is an ambiguity, not evidence of a strategic mistake.
    for i, left in enumerate(audited):
        if left["table_id"] not in (1, 2, 3, 4):
            continue
        if (left["start_pts"] is None or left["end_pts"] is None
                or not 0 <= left["start_pts"] < left["end_pts"] <= duration_seconds):
            continue
        for right in audited[i + 1:]:
            if right["table_id"] != left["table_id"]:
                continue
            if (right["start_pts"] is None or right["end_pts"] is None
                    or not 0 <= right["start_pts"] < right["end_pts"] <= duration_seconds):
                continue
            if left["start_pts"] < right["end_pts"] and right["start_pts"] < left["end_pts"]:
                for entry in (left, right):
                    entry["status"] = "INSUFFICIENT_DATA"
                    if "OVERLAPPING_HAND_INTERVAL" not in entry["reasons"]:
                        entry["reasons"].append("OVERLAPPING_HAND_INTERVAL")
    return {"schema_version": 1, "video_sha256": sha,
            "duration_seconds": duration_seconds, "hands": audited,
            "reviewed_count": sum(x["status"] == "REVIEWED_EVIDENCE" for x in audited),
            "status": "AUDIT_ONLY", "gto_solution": False,
            "notes": "Reviewed flags establish provenance, not OCR correctness or strategic validity."}

def manifest_json(manifest):
    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
