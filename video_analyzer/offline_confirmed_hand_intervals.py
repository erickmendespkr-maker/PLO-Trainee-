"""Build audited intervals from human-reviewed boundaries (offline only)."""
import hashlib
import json
import math
from pathlib import Path

def build_intervals(queue, duration_seconds=None):
    if queue.get("schema_version") != 1 or not isinstance(queue.get("items"), list):
        raise ValueError("invalid queue")
    sha = queue.get("source_video_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha.lower()):
        raise ValueError("invalid source hash")
    if duration_seconds is not None and (type(duration_seconds) not in (int,float) or not math.isfinite(duration_seconds) or duration_seconds <= 0):
        raise ValueError("invalid duration")
    events = {i: [] for i in range(1,5)}
    seen = set()
    for item in queue["items"]:
        table, pts = item.get("table_id"), item.get("candidate_pts_seconds")
        if type(table) is not int or table not in events or type(pts) not in (int,float) or not math.isfinite(pts) or pts < 0:
            raise ValueError("invalid event")
        if duration_seconds is not None and pts > duration_seconds:
            raise ValueError("event beyond video")
        key = (table,pts)
        if key in seen:
            raise ValueError("duplicate event")
        seen.add(key)
        if item.get("review_status") != "HUMAN_REVIEWED":
            continue
        decision = item.get("reviewer_decision",{}).get("decision")
        if decision in ("CONFIRMED_HAND_START","CONFIRMED_HAND_END"):
            if item.get("hand_boundary_verified") is not True:
                raise ValueError("unverified boundary")
            events[table].append((pts,decision))
    intervals, unresolved = [], []
    for table, table_events in events.items():
        opened = None
        for pts, decision in sorted(table_events):
            if decision == "CONFIRMED_HAND_START":
                if opened is not None:
                    unresolved.append({"table_id":table,"pts_seconds":opened,"reason":"START_WITHOUT_END"})
                opened = pts
            elif opened is None:
                unresolved.append({"table_id":table,"pts_seconds":pts,"reason":"END_WITHOUT_START"})
            elif pts <= opened:
                raise ValueError("non-positive interval")
            else:
                key = f"{sha}:{table}:{opened:.6f}:{pts:.6f}"
                intervals.append({"hand_id":hashlib.sha256(key.encode()).hexdigest()[:20],
                    "table_id":table,"start_pts_seconds":opened,"end_pts_seconds":pts,
                    "duration_seconds":round(pts-opened,6),"boundary_status":"HUMAN_CONFIRMED",
                    "cards_status":"UNVERIFIED","actions_status":"UNVERIFIED",
                    "equity_status":"NOT_CALCULATED","ev_status":"NOT_CALCULATED"})
                opened = None
        if opened is not None:
            unresolved.append({"table_id":table,"pts_seconds":opened,"reason":"START_WITHOUT_END"})
    intervals.sort(key=lambda x:(x["start_pts_seconds"],x["table_id"]))
    return {"schema_version":1,"source_video_sha256":sha,"intervals":intervals,
            "unresolved_boundaries":unresolved,"analysis_verified":False}

def build_files(queue_path,output_path,duration_seconds=None):
    result = build_intervals(json.loads(Path(queue_path).read_text(encoding="utf-8")),duration_seconds)
    Path(output_path).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    return result
