"""Audit an offline MP4 clip and its sidecar; never assert poker correctness."""
import hashlib
import json
import math
from pathlib import Path


def _hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_clip_manifest(clip, manifest=None, source=None):
    clip = Path(clip)
    manifest = Path(manifest) if manifest is not None else clip.with_suffix(".json")
    errors = []
    if not clip.is_file() or not clip.stat().st_size:
        errors.append("clip_missing_or_empty")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return {"valid": False, "problems": errors + ["manifest_unreadable"],
                "source_checked": False, "human_review_verified": False}
    if not isinstance(data, dict):
        data = {}
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        errors.append("invalid_schema")
    for key in ("clip_sha256", "source_sha256"):
        value = data.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            errors.append("invalid_" + key)
    if clip.is_file() and clip.stat().st_size and "invalid_clip_sha256" not in errors:
        if _hash(clip) != data["clip_sha256"]:
            errors.append("clip_hash_mismatch")
    if source is not None:
        src = Path(source)
        if not src.is_file() or not src.stat().st_size:
            errors.append("source_missing_or_empty")
        elif "invalid_source_sha256" not in errors and _hash(src) != data["source_sha256"]:
            errors.append("source_hash_mismatch")
    interval = data.get("requested_interval_seconds")
    duration = data.get("source_duration_seconds")
    valid_interval = (isinstance(interval, list) and len(interval) == 2
                      and all(type(v) in (int, float) and math.isfinite(v) for v in interval)
                      and type(duration) in (int, float) and math.isfinite(duration)
                      and 0 <= interval[0] < interval[1] <= duration + 0.001)
    if not valid_interval:
        errors.append("invalid_interval")
    gate = data.get("evidence_gate")
    valid_gate = (isinstance(gate, dict)
                  and gate.get("status") in ("REVIEW_REQUIRED", "INSUFFICIENT_MODEL", "APPROVED_CONDITIONAL")
                  and type(gate.get("table_id")) is int and gate["table_id"] in range(1, 5)
                  and gate["table_id"] == data.get("table_id")
                  and valid_interval and gate.get("start_pts") == interval[0]
                  and gate.get("end_pts") == interval[1]
                  and gate.get("can_label_error") is False
                  and gate.get("can_attach_conditional_ev") is (gate.get("status") == "APPROVED_CONDITIONAL"))
    if not valid_gate:
        errors.append("inconsistent_evidence_gate")
    if (data.get("gto_solution") is not False or data.get("ev_is_conditional") is not True
            or data.get("human_review_of_export") is not False):
        errors.append("unsupported_claims")
    return {"valid": not errors, "problems": errors, "source_checked": source is not None,
            "integrity_only": True, "human_review_verified": False}
