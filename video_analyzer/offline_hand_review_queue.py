"""Generate conservative visual-change intervals from unreviewed frame timelines.

These are human-review candidates, NOT confirmed hands or actions.
"""
import json
import math
from pathlib import Path

def propose_review_intervals(timeline, *, min_gap_seconds=0.05, max_gap_seconds=120.0):
    if not isinstance(timeline, dict) or timeline.get("status") != "UNREVIEWED_TIMELINE":
        raise ValueError("unreviewed timeline required")
    for key in ("absolute_source_pts_verified", "hand_boundaries_verified", "ocr_verified", "equity_ev_verified"):
        if timeline.get(key) is not False:
            raise ValueError("verification claim prohibited")
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
           for v in (min_gap_seconds, max_gap_seconds)) or min_gap_seconds > max_gap_seconds:
        raise ValueError("invalid gap")
    events = timeline.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("events required")
    tables, seen = {}, set()
    for e in events:
        if not isinstance(e, dict) or e.get("review_status") != "UNREVIEWED":
            raise ValueError("unreviewed event required")
        tid, idx, pts, digest = (e.get(k) for k in ("table_id", "frame_index", "crop_pts_seconds", "rgb_sha256"))
        if type(tid) is not int or tid not in range(1, 5) or type(idx) is not int or idx < 0:
            raise ValueError("invalid frame identity")
        if type(pts) not in (int, float) or not math.isfinite(pts) or pts < 0:
            raise ValueError("invalid PTS")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid digest")
        if (tid, idx) in seen:
            raise ValueError("duplicate frame")
        seen.add((tid, idx))
        if "nominal_source_seconds" in e:
            nominal = e["nominal_source_seconds"]
            if e.get("nominal_source_seconds_verified") is not False or type(nominal) not in (int, float) or not math.isfinite(nominal) or nominal < pts:
                raise ValueError("nominal source PTS not verified")
        tables.setdefault(tid, []).append(e)
    proposals = []
    for tid, samples in sorted(tables.items()):
        samples.sort(key=lambda e: e["frame_index"])
        for a, b in zip(samples, samples[1:]):
            delta = b["crop_pts_seconds"] - a["crop_pts_seconds"]
            if b["frame_index"] <= a["frame_index"] or delta <= 0:
                raise ValueError("nonmonotonic frames")
            if min_gap_seconds <= delta <= max_gap_seconds and a["rgb_sha256"] != b["rgb_sha256"]:
                proposals.append({"table_id": tid, "start_crop_pts_seconds": a["crop_pts_seconds"],
                    "end_crop_pts_seconds": b["crop_pts_seconds"], "start_frame_index": a["frame_index"],
                    "end_frame_index": b["frame_index"], "start_rgb_sha256": a["rgb_sha256"],
                    "end_rgb_sha256": b["rgb_sha256"], "reason": "PIXEL_CHANGE_BETWEEN_SAMPLES",
                    "review_status": "HUMAN_REVIEW_REQUIRED", "hand_confirmed": False,
                    "action_confirmed": False, "equity_ev_verified": False})
    proposals.sort(key=lambda p: (p["start_crop_pts_seconds"], p["table_id"]))
    return {"status": "UNREVIEWED_VISUAL_CHANGE_INTERVALS", "proposals": proposals,
            "hand_boundaries_verified": False, "ocr_verified": False, "equity_ev_verified": False}

def write_review_queue(source_path, destination_path, **kwargs):
    src, dst = Path(source_path), Path(destination_path)
    if src.is_symlink() or not src.is_file() or dst.is_symlink() or src.resolve() == dst.resolve():
        raise ValueError("unsafe path")
    result = propose_review_intervals(json.loads(src.read_text(encoding="utf-8")), **kwargs)
    with dst.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2, ensure_ascii=False)
    return result
