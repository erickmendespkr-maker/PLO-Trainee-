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
    seen = set()
    for entry in audited:
        key = (entry["table_id"], entry["hand_id"])
        if key in seen:
            entry["status"] = "INSUFFICIENT_DATA"
            entry["reasons"].append("DUPLICATE_HAND_ID")
        else:
            seen.add(key)
    return {"schema_version": 1, "video_sha256": sha,
            "duration_seconds": duration_seconds, "hands": audited,
            "reviewed_count": sum(x["status"] == "REVIEWED_EVIDENCE" for x in audited),
            "status": "AUDIT_ONLY", "gto_solution": False,
            "notes": "Reviewed flags establish provenance, not OCR correctness or strategic validity."}

def manifest_json(manifest):
    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
