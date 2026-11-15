"""Deterministic offline visual review queue; never ranks poker EV."""
import json
import math
from pathlib import Path

class QueueValidationError(ValueError):
    pass

def build_review_queue(records, *, max_tables=4):
    """Rank provisional video intervals for review, not strategic merit."""
    if type(max_tables) is not int or not 1 <= max_tables <= 4:
        raise QueueValidationError("invalid max_tables")
    if not isinstance(records, list):
        raise QueueValidationError("records must be a list")
    output, seen = [], set()
    for i, record in enumerate(records):
        if not isinstance(record, dict):
            raise QueueValidationError(f"invalid record {i}")
        table = record.get("table_id")
        start, end = record.get("start_pts"), record.get("end_pts")
        if type(table) is not int or not 1 <= table <= max_tables:
            raise QueueValidationError(f"invalid table {i}")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)) or not 0 <= start < end or end-start > 3600:
            raise QueueValidationError(f"invalid interval {i}")
        identifier = record.get("candidate_id")
        if not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 128 or identifier in seen:
            raise QueueValidationError(f"invalid or duplicate candidate_id {i}")
        seen.add(identifier)
        confidence = record.get("visual_confidence")
        if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise QueueValidationError(f"invalid visual_confidence {i}")
        needs_review = record.get("needs_human_review", True)
        if type(needs_review) is not bool:
            raise QueueValidationError(f"invalid review flag {i}")
        priority = round((1-confidence)*100+(25 if needs_review else 0), 4)
        output.append({"candidate_id": identifier, "table_id": table,
                       "start_pts": start, "end_pts": end,
                       "visual_confidence": confidence,
                       "needs_human_review": needs_review,
                       "review_priority": priority,
                       "hand_boundary_verified": False,
                       "strategic_conclusion": None,
                       "priority_is_ev": False})
    return sorted(output, key=lambda item: (-item["review_priority"], item["start_pts"], item["table_id"], item["candidate_id"]))

def save_review_queue(records, destination):
    """Create an audit JSON without overwriting existing artifacts."""
    queue = build_review_queue(records)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump({"schema_version": 1, "type": "provisional_visual_review_queue",
                   "items": queue, "gto_solution": False}, stream, indent=2)
        stream.write("\n")
    return queue
