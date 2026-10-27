"""Conservative OFFLINE handoff from a human-review queue to declared-range Monte Carlo.

This validates *claims* and binds review metadata to a queue entry; it cannot
verify video, OCR, ranges, corrected cards, or strategic correctness. The output
is only an input candidate for offline_reviewed_range_equity_bridge.py.
No live poker clients, auto clip selection, or automatic decisions are used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

MAX_BYTES = 2 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{64}\Z")
CLEAN_TAIL = "no_anomaly_detected_in_compared_tail"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact(value, fields, label):
    require(type(value) is dict and set(value) == fields, f"Invalid {label} schema")


def label(value, name, limit=120):
    require(type(value) is str and 0 < len(value) <= limit and
            not any(ord(ch) < 32 for ch in value), f"Invalid {name}")
    return value


def digest(value, name):
    require(type(value) is str and SHA.fullmatch(value) is not None, f"Invalid {name}")
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      allow_nan=False, separators=(",", ":")).encode("utf-8")


def analyze(payload):
    exact(payload, {"schema_version", "queue", "hand_ref", "manual_review", "bridge_input"}, "handoff")
    require(type(payload["schema_version"]) is int and payload["schema_version"] == 1,
            "Unsupported handoff version")
    queue = payload["queue"]
    require(type(queue) is dict and queue.get("schema_version") == 1 and
            queue.get("status") == "offline_human_review_priority_not_strategy_or_video_verification" and
            queue.get("all_hands_require_manual_review") is True and
            queue.get("video_evidence_verified") is False and
            queue.get("ocr_accuracy_verified") is False and
            queue.get("equity_ev_authorized") is False and
            queue.get("automatic_clip_selection_authorized") is False and
            type(queue.get("hands")) is list and 1 <= len(queue["hands"]) <= 200 and
            type(queue.get("hand_count")) is int and queue["hand_count"] == len(queue["hands"]),
            "Unsupported or overclaiming review queue")
    source = digest(queue.get("source_recording_sha256_claim_unverified"), "queue source SHA claim")
    ref = payload["hand_ref"]
    exact(ref, {"table_id", "hand_label", "ledger_canonical_sha256"}, "hand reference")
    require(type(ref["table_id"]) is int and 1 <= ref["table_id"] <= 4,
            "Invalid table")
    label(ref["hand_label"], "hand label", 64)
    digest(ref["ledger_canonical_sha256"], "ledger SHA")
    matches = [h for h in queue["hands"] if type(h) is dict and
               h.get("table_id") == ref["table_id"] and
               h.get("hand_label") == ref["hand_label"]]
    require(len(matches) == 1, "Hand identity absent or ambiguous")
    hand = matches[0]
    require(hand.get("ledger_canonical_sha256") == ref["ledger_canonical_sha256"] and
            hand.get("source_recording_sha256_claim_unverified") == source and
            hand.get("variant") in ("PLO5", "PLO6") and
            hand.get("manual_review_required") is True and
            hand.get("video_evidence_verified") is False and
            hand.get("ocr_accuracy_verified") is False and
            hand.get("equity_ev_authorized") is False and
            hand.get("automatic_clip_selection_authorized") is False and
            type(hand.get("events")) is list and
            type(hand.get("event_count")) is int and
            hand["event_count"] == len(hand["events"]) <= 500 and
            type(hand.get("hand_review_flags")) is list and
            type(hand.get("unlinked_event_count")) is int,
            "Hand provenance mismatch or unsupported verification claims")
    for i, event in enumerate(hand["events"]):
        require(type(event) is dict and type(event.get("event_index")) is int and
                event["event_index"] == i and type(event.get("review_reasons")) is list,
                "Invalid queue event indices")
    review = payload["manual_review"]
    exact(review, {"source_kind", "reviewer_label", "event_resolutions", "hand_flags_resolution",
                   "temporal_resolution", "review_notes", "annotations_attested"}, "manual review")
    require(review["source_kind"] in ("synthetic_fixture", "human_annotation_claim"),
            "Invalid review source")
    label(review["reviewer_label"], "reviewer label", 80)
    require(type(review["annotations_attested"]) is bool,
            "Invalid annotation attestation")
    require(type(review["event_resolutions"]) is list and
            len(review["event_resolutions"]) == len(hand["events"]),
            "All queue events must be individually reviewed")
    unresolved_events = []
    for i, resolution in enumerate(review["event_resolutions"]):
        exact(resolution, {"event_index", "outcome", "note"}, "event resolution")
        require(type(resolution["event_index"]) is int and resolution["event_index"] == i and
                resolution["outcome"] in ("confirmed", "corrected", "unresolved") and
                type(resolution["note"]) is str and len(resolution["note"]) <= 500 and
                not any(ord(ch) < 32 for ch in resolution["note"]),
                "Invalid event resolution")
        if resolution["outcome"] == "corrected":
            label(resolution["note"], "correction note", 500)
        if resolution["outcome"] == "unresolved":
            unresolved_events.append(i)
    require(review["hand_flags_resolution"] in ("not_applicable", "resolved", "unresolved") and
            review["temporal_resolution"] in ("not_applicable", "resolved", "unresolved"),
            "Invalid diagnostic resolution")
    require(type(review["review_notes"]) is str and len(review["review_notes"]) <= 2000 and
            not any(ord(ch) < 32 for ch in review["review_notes"]),
            "Invalid review notes")
    has_hand_flags = bool(hand["hand_review_flags"])
    has_tail_warning = hand.get("temporal_audit_classification") not in (None, CLEAN_TAIL)
    require((review["hand_flags_resolution"] != "not_applicable") == has_hand_flags and
            (review["temporal_resolution"] != "not_applicable") == has_tail_warning,
            "Diagnostic review does not match queue flags")
    if review["hand_flags_resolution"] == "resolved" or review["temporal_resolution"] == "resolved":
        label(review["review_notes"], "diagnostic resolution notes", 2000)
    bridge = payload["bridge_input"]
    exact(bridge, {"schema_version", "reviewed_hand", "review_gate", "weighted_range", "monte_carlo"},
          "bridge input")
    require(type(bridge["schema_version"]) is int and bridge["schema_version"] == 1,
            "Invalid bridge version")
    reviewed_hand = bridge["reviewed_hand"]
    require(type(reviewed_hand) is dict and
            reviewed_hand.get("variant") == hand["variant"] and
            type(reviewed_hand.get("table_id")) is int and
            reviewed_hand["table_id"] == ref["table_id"] and
            reviewed_hand.get("hand_label") == ref["hand_label"] and
            reviewed_hand.get("source_recording_sha256_claim") == source and
            reviewed_hand.get("equity_estimate") is None and
            type(reviewed_hand.get("unresolved_fields")) is list,
            "Reviewed hand does not match selected queue hand")
    gate = bridge["review_gate"]
    exact(gate, {"status", "reviewer_label"}, "bridge review gate")
    require(gate["reviewer_label"] == review["reviewer_label"] and
            ((review["source_kind"] == "synthetic_fixture" and
              gate["status"] == "synthetic_fixture" and
              reviewed_hand.get("annotation_source") == "synthetic") or
             (review["source_kind"] == "human_annotation_claim" and
              gate["status"] == "human_confirmed_claim" and
              reviewed_hand.get("annotation_source") == "human_annotation")),
            "Bridge review gate/source mismatch")
    require(type(bridge["weighted_range"]) is list and 1 <= len(bridge["weighted_range"]) <= 1000 and
            type(bridge["monte_carlo"]) is dict,
            "Range and Monte Carlo parameters required")
    decision = reviewed_hand.get("decision")
    require(type(decision) is dict, "Decision details missing")
    reasons = []
    if not review["annotations_attested"]:
        reasons.append("annotations_not_attested")
    if unresolved_events:
        reasons.append("unresolved_event_reviews")
    if review["hand_flags_resolution"] == "unresolved":
        reasons.append("unresolved_hand_flags")
    if review["temporal_resolution"] == "unresolved":
        reasons.append("unresolved_temporal_diagnostics")
    if reviewed_hand["unresolved_fields"]:
        reasons.append("unresolved_math_annotations")
    if decision.get("action") != "call":
        reasons.append("only_call_vs_fold_supported")
    if decision.get("no_future_betting") is not True:
        reasons.append("future_betting_not_modeled")
    if decision.get("no_side_pots") is not True:
        reasons.append("side_pots_not_modeled")
    opponent = reviewed_hand.get("opponent_range")
    if type(opponent) is not dict or opponent.get("opponents") != 1:
        reasons.append("only_heads_up_supported")
    reasons = sorted(set(reasons))
    return {
        "schema_version": 1,
        "status": "blocked_for_manual_review" if reasons else "handoff_candidate_requires_bridge_validation",
        "table_id": ref["table_id"], "hand_label": ref["hand_label"],
        "variant": hand["variant"],
        "queue_canonical_sha256": hashlib.sha256(canonical(queue)).hexdigest(),
        "review_canonical_sha256": hashlib.sha256(canonical(review)).hexdigest(),
        "ledger_canonical_sha256_claim": ref["ledger_canonical_sha256"],
        "source_recording_sha256_claim_unverified": source,
        "blocked_reasons": reasons,
        "events_reviewed_claim": len(review["event_resolutions"]) - len(unresolved_events),
        "events_total": len(hand["events"]),
        "bridge_input_candidate": bridge if not reasons else None,
        "monte_carlo_executed": False,
        "video_evidence_verified": False,
        "ocr_accuracy_verified": False,
        "opponent_range_verified": False,
        "strategic_error_proven": False,
        "automatic_clip_selection_authorized": False,
        "limitations": [
            "Human review and source SHA are declarations, not verified against video bytes.",
            "Queue event resolutions do not prove corrected card/action transcription.",
            "The downstream bridge must independently validate ranges and card collisions.",
            "No equity, EV, strategic verdict, or automatic clip selection is produced here.",
        ],
    }


def unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, "Duplicate JSON key")
        out[key] = value
    return out


def reject_constant(value):
    raise ValueError(f"Nonfinite JSON constant: {value}")


def read_json(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "Unsafe input file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_BYTES,
                "Invalid input size/type")
        raw = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
        require(0 < len(raw) <= MAX_BYTES and
                (before.st_size, before.st_mtime_ns, before.st_ino) ==
                (after.st_size, after.st_mtime_ns, after.st_ino),
                "Input changed during read")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                      parse_constant=reject_constant)
    return data, hashlib.sha256(raw).hexdigest()


def export(input_path, report_path, candidate_path):
    src, report, candidate = map(Path, (input_path, report_path, candidate_path))
    require(report != candidate and src not in (report, candidate) and
            report.parent.resolve() == src.parent.resolve() and
            candidate.parent.resolve() == src.parent.resolve() and
            not src.parent.is_symlink() and
            report.suffix.lower() == candidate.suffix.lower() == ".json" and
            all(not p.exists() and not p.is_symlink() for p in (report, candidate)),
            "Outputs must be new JSON files beside input")
    data, input_sha = read_json(src)
    result = analyze(data)
    candidate_data = result.pop("bridge_input_candidate")
    result["input_sha256"] = input_sha
    report_bytes = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False).encode() + b"\n"
    candidate_bytes = (json.dumps(candidate_data, indent=2, ensure_ascii=False,
                                  allow_nan=False).encode() + b"\n") if candidate_data else None
    require(len(report_bytes) <= MAX_BYTES and
            (candidate_bytes is None or len(candidate_bytes) <= MAX_BYTES) and
            read_json(src)[1] == input_sha, "Input changed or output too large")
    written = []
    try:
        for path, content in ((report, report_bytes), (candidate, candidate_bytes)):
            if content is None:
                continue
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0), 0o600)
            written.append(path)
            with os.fdopen(fd, "wb") as stream:
                require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Unsafe output type")
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json")
    parser.add_argument("new_report_json")
    parser.add_argument("new_bridge_candidate_json")
    args = parser.parse_args(argv)
    result = export(args.input_json, args.new_report_json, args.new_bridge_candidate_json)
    print(json.dumps({"status": result["status"], "blocked_reasons": result["blocked_reasons"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
