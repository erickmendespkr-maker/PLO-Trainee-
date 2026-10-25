"""Validate and persist human review decisions for offline OCR evidence.

This module never reconstructs poker hands, promotes OCR to verified facts,
authorizes equity/EV, or chooses clips. Review decisions are only an auditable
human annotation bound to a freshly rebuilt evidence handoff.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
from pathlib import Path
import re

from offline_job_review_handoff import build_handoff
from offline_jobs import OfflineJobStore

SCHEMA_VERSION = 1
MAX_SUBMISSION_BYTES = 2_000_000
MAX_DECISIONS = 20_000
JOB_ID = re.compile(r"^[0-9a-f]{32}$")
FIELDS = frozenset({"pot", "bet", "board", "hero_cards"})
STATUSES = frozenset({"confirmed", "corrected", "rejected", "uncertain"})
SUBMISSION_KEYS = frozenset({"schema_version", "job_id", "handoff_sha256", "reviewer", "decisions"})
DECISION_KEYS = frozenset({"table_id", "nominal_timestamp_seconds", "field",
                           "candidate_index", "status", "value", "confidence", "reason"})


def _json_bytes(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def handoff_sha256(handoff):
    """Deterministic fingerprint of the full, freshly validated handoff."""
    return hashlib.sha256(_json_bytes(handoff)).hexdigest()


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON number: " + value)


def load_submission(path):
    """Read bounded UTF-8 JSON without following a final-path symlink."""
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("Submission cannot be opened safely") from exc
    with os.fdopen(fd, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Submission must be a regular file, not a symlink")
        if metadata.st_size > MAX_SUBMISSION_BYTES:
            raise ValueError("Submission exceeds size limit")
        raw = stream.read(MAX_SUBMISSION_BYTES + 1)
    if len(raw) > MAX_SUBMISSION_BYTES:
        raise ValueError("Submission exceeds size limit")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates,
                          parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid UTF-8 JSON submission") from exc


def _clean_text(value, field, max_length, min_length=1):
    if type(value) is not str or not (min_length <= len(value) <= max_length):
        raise ValueError("Invalid " + field)
    if value != value.strip() or any(ord(char) < 32 and char not in "\t\n" for char in value):
        raise ValueError("Invalid " + field)
    return value


def _stamp(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid nominal timestamp")
    return float(value)


def _confidence(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not (0 <= value <= 1):
        raise ValueError("Confidence must be a finite number between 0 and 1")
    return float(value)


def validate_submission(handoff, submission):
    """Validate a human-only annotation against audited, immutable OCR hints.

    A complete set of decisions is *not* evidence of a reconstructed hand.
    """
    if type(handoff) is not dict or handoff.get("analysis_status") != "unapproved_offline_review_handoff":
        raise ValueError("Expected an unapproved handoff")
    if handoff.get("requires_manual_review") is not True or handoff.get("ready_for_equity_or_ev") is not False:
        raise ValueError("Handoff incorrectly authorizes analysis")
    if type(submission) is not dict or set(submission) != SUBMISSION_KEYS:
        raise ValueError("Unexpected submission structure")
    if type(submission["schema_version"]) is not int or submission["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Unsupported review schema")
    job_id = submission["job_id"]
    if type(job_id) is not str or not JOB_ID.fullmatch(job_id) or job_id != handoff.get("job_id"):
        raise ValueError("Job ID mismatch")
    expected = handoff_sha256(handoff)
    if type(submission["handoff_sha256"]) is not str or submission["handoff_sha256"] != expected:
        raise ValueError("Handoff fingerprint mismatch")
    reviewer = _clean_text(submission["reviewer"], "reviewer", 80, 2)
    decisions = submission["decisions"]
    if type(decisions) is not list or len(decisions) > MAX_DECISIONS:
        raise ValueError("Invalid decisions list")

    # The only reviewable units are OCR hints bound to audited table frames.
    allowed = {}
    frames = handoff.get("frames")
    if type(frames) is not list:
        raise ValueError("Invalid handoff frames")
    for frame in frames:
        if type(frame) is not dict:
            raise ValueError("Invalid handoff frame")
        table = frame.get("table_id")
        if type(table) is not int or table not in (1, 2, 3, 4):
            raise ValueError("Invalid table")
        stamp = _stamp(frame.get("nominal_timestamp_seconds"))
        hints = frame.get("ocr_hints_unverified")
        if type(hints) is not list:
            raise ValueError("Invalid OCR hints")
        for hint in hints:
            if type(hint) is not dict or hint.get("field") not in FIELDS:
                raise ValueError("Invalid OCR hint")
            idx = hint.get("candidate_index")
            if type(idx) is not int or idx < 0:
                raise ValueError("Invalid OCR index")
            key = (table, stamp, hint["field"], idx)
            if key in allowed:
                raise ValueError("Duplicate OCR hint")
            text = hint.get("unverified_text")
            if type(text) is not str or len(text) > 200:
                raise ValueError("Invalid OCR text")
            allowed[key] = text

    seen = set()
    reviewed = []
    totals = {status: 0 for status in sorted(STATUSES)}
    for item in decisions:
        if type(item) is not dict or set(item) != DECISION_KEYS:
            raise ValueError("Unexpected decision structure")
        table, field, idx = item["table_id"], item["field"], item["candidate_index"]
        if type(table) is not int or type(idx) is not int or field not in FIELDS:
            raise ValueError("Invalid decision reference")
        key = (table, _stamp(item["nominal_timestamp_seconds"]), field, idx)
        if key not in allowed or key in seen:
            raise ValueError("Unknown or duplicate OCR candidate")
        seen.add(key)
        status = item["status"]
        if type(status) is not str or status not in STATUSES:
            raise ValueError("Invalid decision status")
        reason = _clean_text(item["reason"], "reason", 300, 3)
        value, confidence = item["value"], item["confidence"]
        if status in ("confirmed", "corrected"):
            value = _clean_text(value, "approved value", 160)
            confidence = _confidence(confidence)
            if status == "confirmed" and value != allowed[key]:
                raise ValueError("Confirmed value differs from OCR; use corrected")
            if status == "corrected" and value == allowed[key]:
                raise ValueError("Correction must differ from OCR")
        elif value is not None or confidence is not None:
            raise ValueError("Uncertain/rejected evidence cannot contain approved values")
        totals[status] += 1
        reviewed.append({"table_id": table, "nominal_timestamp_seconds": key[1],
                         "field": field, "candidate_index": idx, "status": status,
                         "value": value, "confidence": confidence, "reason": reason,
                         "original_ocr_text_unverified": allowed[key]})
    reviewed.sort(key=lambda x: (x["table_id"], x["nominal_timestamp_seconds"],
                                x["candidate_index"], x["field"]))
    remaining = len(allowed) - len(seen)
    return {"schema_version": SCHEMA_VERSION,
            "analysis_status": "human_ocr_annotations_not_verified_hands",
            "job_id": job_id, "reviewer": reviewer,
            "handoff_sha256": expected,
            "source_sha256": handoff.get("source_sha256"),
            "timestamp_semantics": "nominal_sampling_grid_not_exact_source_pts",
            "reviewed_count": len(reviewed), "unreviewed_count": remaining,
            "status_counts": totals, "decisions": reviewed,
            "ocr_review_complete": remaining == 0,
            "requires_manual_review": True,
            "hand_reconstruction_verified": False,
            "ready_for_equity_or_ev": False,
            "automatic_clip_selection_authorized": False,
            "limitations": [
                "Human annotation is not a verified hand reconstruction.",
                "Timestamps are nominal and not independently validated source PTS.",
                "OCR text and confidence are subjective; ranges and future actions remain unknown.",
                "Do not calculate equity/EV or automatically choose clips from this report."
            ]}


def review_job(store, job_id, results_root, submission):
    """Re-audit source video and frame hashes at the moment of validation."""
    if type(job_id) is not str or not JOB_ID.fullmatch(job_id):
        raise ValueError("Invalid job ID")
    handoff = build_handoff(store, job_id, results_root)
    return validate_submission(handoff, submission)


def export_review(store, job_id, results_root, submission):
    """Create one immutable JSON report; never update queue, source or handoff."""
    report = review_job(store, job_id, results_root, submission)
    folder = Path(results_root) / job_id
    output = folder / "human_ocr_review.json"
    if output.exists() or output.is_symlink():
        raise FileExistsError("Human review already exported")
    data = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    # Exclusive creation; no overwrite even when concurrent processes race.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    parser.add_argument("job_id")
    parser.add_argument("results_root")
    parser.add_argument("submission_json")
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args(argv)
    store = OfflineJobStore(args.database)
    submission = load_submission(args.submission_json)
    report = (export_review if args.export else review_job)(
        store, args.job_id, args.results_root, submission)
    print(json.dumps({"job_id": report["job_id"],
                      "reviewed_count": report["reviewed_count"],
                      "unreviewed_count": report["unreviewed_count"],
                      "ready_for_equity_or_ev": False}))


if __name__ == "__main__":
    main()
