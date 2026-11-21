"""Conservative validation of human-reviewed offline video evidence.

Never infers hidden cards or authorizes strategic EV from OCR alone.
"""
import math
import re

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
FIELDS = {"pot", "stack", "bet", "action", "hero_cards", "board", "street"}


def validate_annotations(document):
    if not isinstance(document, dict):
        raise ValueError("document must be an object")
    sha = document.get("video_sha256")
    if not isinstance(sha, str) or not SHA256.fullmatch(sha):
        raise ValueError("invalid video_sha256")
    duration = document.get("duration_seconds")
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid duration_seconds")
    observations = document.get("observations")
    if not isinstance(observations, list):
        raise ValueError("observations must be a list")
    seen = set()
    for i, obs in enumerate(observations):
        if not isinstance(obs, dict):
            raise ValueError(f"observation {i}: expected object")
        table = obs.get("table_id")
        hand = obs.get("hand_id")
        ts = obs.get("timestamp_seconds")
        field = obs.get("field")
        confidence = obs.get("confidence")
        frame = obs.get("frame_sha256")
        if type(table) is not int or not 1 <= table <= 4:
            raise ValueError(f"observation {i}: table_id")
        if not isinstance(hand, str) or not hand.strip() or len(hand) > 128:
            raise ValueError(f"observation {i}: hand_id")
        if type(ts) not in (int, float) or not math.isfinite(ts) or not 0 <= ts <= duration:
            raise ValueError(f"observation {i}: timestamp")
        if field not in FIELDS:
            raise ValueError(f"observation {i}: field")
        if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError(f"observation {i}: confidence")
        if not isinstance(frame, str) or not SHA256.fullmatch(frame):
            raise ValueError(f"observation {i}: frame_sha256")
        if type(obs.get("reviewed_by_human")) is not bool:
            raise ValueError(f"observation {i}: reviewed_by_human")
        for key in ("raw_text", "corrected_value"):
            value = obs.get(key)
            if value is not None and (not isinstance(value, str) or len(value) > 4096):
                raise ValueError(f"observation {i}: {key}")
        if obs["reviewed_by_human"] and not (isinstance(obs.get("corrected_value"), str) and obs["corrected_value"].strip()):
            raise ValueError(f"observation {i}: missing correction")
        identity = (table, hand, ts, field, frame)
        if identity in seen:
            raise ValueError(f"observation {i}: duplicate evidence")
        seen.add(identity)
    return {
        "video_sha256": sha,
        "duration_seconds": duration,
        "observations": observations,
        "reviewed_count": sum(o["reviewed_by_human"] for o in observations),
        "unreviewed_count": sum(not o["reviewed_by_human"] for o in observations),
        "ev_authorized": False,
    }
