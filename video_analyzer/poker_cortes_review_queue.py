"""Conservative review queue for imported Poker Cortes OCR reports.

All candidates remain unverified: this module never confirms loss or authorizes EV.
"""
import hashlib
import json
import math


def build_review_queue(candidates, *, min_loss_bb=30.0, max_tables=4):
    if isinstance(min_loss_bb, bool) or not isinstance(min_loss_bb, (int, float)) or not math.isfinite(min_loss_bb) or min_loss_bb < 0:
        raise ValueError("invalid min_loss_bb")
    if type(max_tables) is not int or not 1 <= max_tables <= 4:
        raise ValueError("invalid max_tables")
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")
    seen = set()
    result = []
    for c in candidates:
        if not isinstance(c, dict):
            raise ValueError("candidate must be an object")
        sha = c.get("video_sha256")
        table = c.get("table_id")
        start, end = c.get("start_seconds"), c.get("end_seconds")
        if not isinstance(sha, str) or len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha):
            raise ValueError("invalid video hash")
        if type(table) is not int or not 1 <= table <= max_tables:
            raise ValueError("invalid table")
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in (start, end)) or not 0 <= start < end:
            raise ValueError("invalid interval")
        if c.get("review_status") != "UNVERIFIED" or c.get("verified_by_human") is not False or c.get("confirmed_loss_bb") is not None or c.get("strategic_analysis_authorized") is not False:
            raise ValueError("candidate unexpectedly promoted")
        loss = c.get("ocr_reported_loss_bb")
        if loss is not None and (isinstance(loss, bool) or not isinstance(loss, (int, float)) or not math.isfinite(loss) or loss < 0):
            raise ValueError("invalid reported loss")
        key = (sha, table, float(start), float(end))
        if key in seen:
            raise ValueError("duplicate candidate interval")
        seen.add(key)
        rebuy = str(c.get("source_rebuy_seen", "")).strip().casefold() in ("sim", "yes", "true", "1")
        pot = str(c.get("source_pot_confirmed", "")).strip().casefold() in ("sim", "yes", "true", "1")
        flags = []
        if loss is None:
            flags.append("LOSS_UNREADABLE")
        elif loss >= min_loss_bb:
            flags.append("REPORTED_ABOVE_THRESHOLD_NOT_CONFIRMED")
        if rebuy:
            flags.append("REBUY_REQUIRES_SEPARATE_ACCOUNTING")
        if not pot:
            flags.append("POT_NOT_INDEPENDENTLY_CONFIRMED")
        identity = json.dumps(key, separators=(",", ":"), ensure_ascii=True)
        result.append({
            "candidate_id": hashlib.sha256(identity.encode()).hexdigest(),
            "video_sha256": sha, "table_id": table,
            "start_seconds": start, "end_seconds": end,
            "reported_loss_bb": loss, "flags": flags,
            "review_priority": "HIGH" if loss is not None and loss >= min_loss_bb else "NORMAL",
            "source_csv_sha256": c.get("source_csv_sha256"),
            "source_row": c.get("source_row"),
            "human_review_required": True, "confirmed_loss_bb": None,
            "math_analysis_authorized": False, "clip_loss_label_authorized": False,
        })
    result.sort(key=lambda x: (x["review_priority"] != "HIGH", -(x["reported_loss_bb"] or 0), x["start_seconds"], x["table_id"]))
    return {"schema_version": 1, "kind": "poker_cortes_unverified_review_queue",
            "threshold_bb": float(min_loss_bb), "total": len(result), "items": result}
