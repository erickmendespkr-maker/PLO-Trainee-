"""Bind manual correction proposals to an immutable offline hand-history draft.

A correction overlay is NOT an amended hand history, verified OCR, verified
source PTS, or permission to compute equity/EV or select clips. The original
Cycle 107 draft remains untouched; an independent reviewer must resolve each
proposal before any downstream analysis.
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

MAX_INPUT = 4 * 1024 * 1024
MAX_CORRECTIONS = 1000
MAX_SECONDS = 86400
SHA = re.compile(r"[0-9a-f]{64}\Z")
JOB = re.compile(r"[0-9a-f]{32}\Z")
FIELDS = frozenset({"hero_cards", "board_by_street", "actions", "pot_before_decision",
                    "call_amount", "effective_stack", "source_pts_start_seconds",
                    "source_pts_end_seconds", "opponent_range_notes", "notes",
                    "confidence_subjective"})


def check(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        check(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def read_json(path):
    p = Path(path)
    check(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_INPUT,
          "Unsafe or oversized JSON")
    raw = p.read_bytes()
    check(0 < len(raw) <= MAX_INPUT, "Oversized JSON")
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                         parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid UTF-8 JSON") from exc
    check(type(obj) is dict, "Expected JSON object")
    return obj, raw


def finite_number(v):
    return type(v) in (int, float) and math.isfinite(v)


def validate_draft(draft):
    check(type(draft.get("schema_version")) is int and draft.get("schema_version") == 1 and
          draft.get("analysis_status") == "human_entered_hand_history_drafts_no_math" and
          type(draft.get("job_id")) is str and JOB.fullmatch(draft["job_id"]) and
          type(draft.get("source_sha256")) is str and SHA.fullmatch(draft["source_sha256"]),
          "Unexpected hand-history draft")
    for gate in ("hand_start_or_end_pts_verified", "hand_reconstruction_verified",
                 "ready_for_equity_or_ev", "automatic_clip_selection_authorized"):
        check(draft.get(gate) is False, "Upstream draft asserts verification")
    rows = draft.get("hands")
    check(type(rows) is list and len(rows) <= 2000, "Invalid hand rows")
    lookup = {}
    for row in rows:
        check(type(row) is dict and type(row.get("table_id")) is int and
              1 <= row["table_id"] <= 4 and
              type(row.get("hand_label_human_assigned")) is str and
              0 < len(row["hand_label_human_assigned"]) <= 64 and
              type(row.get("human_entry")) is dict and
              row.get("hand_reconstruction_verified") is False and
              row.get("ready_for_equity_or_ev") is False and
              row.get("automatic_clip_selection_authorized") is False,
              "Invalid or authoritative draft row")
        key = (row["table_id"], row["hand_label_human_assigned"])
        check(key not in lookup and row["human_entry"].get("table_id") == key[0] and
              row["human_entry"].get("hand_label_human_assigned") == key[1],
              "Duplicate or mismatched hand identity")
        lookup[key] = row["human_entry"]
    return lookup


def validate_value(field, value):
    """Bound proposals; intentionally do not treat values as OCR truth."""
    check(len(canonical(value)) <= 16000, "Correction value too large")
    if field in ("pot_before_decision", "call_amount", "effective_stack"):
        check(value is None or (finite_number(value) and 0 <= value <= 1e9),
              "Invalid chip amount")
    elif field in ("source_pts_start_seconds", "source_pts_end_seconds"):
        check(value is None or (finite_number(value) and 0 <= value <= MAX_SECONDS),
              "Invalid timestamp proposal")
    elif field == "confidence_subjective":
        check(finite_number(value) and 0 <= value <= 1, "Invalid subjective confidence")
    elif field in ("notes", "opponent_range_notes"):
        check(type(value) is str and len(value) <= 2000, "Invalid notes")
    elif field == "hero_cards":
        check(value is None or (type(value) is list and len(value) in (5, 6) and
              all(type(card) is str and re.fullmatch(r"[2-9TJQKA][cdhs]", card)
                  for card in value) and len(set(value)) == len(value)), "Invalid cards")
    elif field == "board_by_street":
        check(type(value) is dict and set(value) == {"flop", "turn", "river"},
              "Invalid board")
        cards = value["flop"] or []
        check((value["flop"] is None or (type(value["flop"]) is list and len(cards) == 3)) and
              all(type(c) is str and re.fullmatch(r"[2-9TJQKA][cdhs]", c) for c in cards),
              "Invalid flop")
        for street in ("turn", "river"):
            card = value[street]
            check(card is None or (type(card) is str and re.fullmatch(r"[2-9TJQKA][cdhs]", card)),
                  "Invalid board card")
        check(value["turn"] is None or value["flop"] is not None, "Turn without flop")
        check(value["river"] is None or value["turn"] is not None, "River without turn")
        all_cards = cards + [value[s] for s in ("turn", "river") if value[s] is not None]
        check(len(all_cards) == len(set(all_cards)), "Duplicate board card")
    elif field == "actions":
        check(type(value) is list and len(value) <= 200, "Invalid action list")
        for item in value:
            check(type(item) is dict and set(item) ==
                  {"street", "actor", "action", "amount", "source_pts_seconds"} and
                  item["street"] in ("preflop", "flop", "turn", "river") and
                  item["action"] in ("fold", "check", "call", "bet", "raise") and
                  type(item["actor"]) is str and
                  (item["actor"] in ("hero", "unknown") or
                   re.fullmatch(r"villain_[1-9][0-9]?", item["actor"])) and
                  (item["amount"] is None or (finite_number(item["amount"]) and
                   0 <= item["amount"] <= 1e9)) and
                  finite_number(item["source_pts_seconds"]) and
                  0 <= item["source_pts_seconds"] <= MAX_SECONDS,
                  "Invalid action proposal")
    else:
        raise ValueError("Field not editable")


def build_overlay(draft, submission):
    lookup = validate_draft(draft)
    check(set(submission) == {"schema_version", "job_id", "source_draft_sha256",
                              "reviewer_label", "corrections"} and
          type(submission["schema_version"]) is int and submission["schema_version"] == 1 and
          submission["job_id"] == draft["job_id"] and
          submission["source_draft_sha256"] == digest(draft),
          "Submission is not bound to this draft")
    label = submission["reviewer_label"]
    check(type(label) is str and 1 <= len(label) <= 80 and
          all(ord(c) >= 32 for c in label), "Invalid reviewer label")
    entries = submission["corrections"]
    check(type(entries) is list and 1 <= len(entries) <= MAX_CORRECTIONS,
          "Invalid correction count")
    seen, out = set(), []
    for entry in entries:
        check(type(entry) is dict and set(entry) ==
              {"table_id", "hand_label_human_assigned", "field", "expected_value_sha256",
               "proposed_value", "reason", "confidence_subjective"},
              "Invalid correction schema")
        key = (entry["table_id"], entry["hand_label_human_assigned"])
        field = entry["field"]
        check(key in lookup and type(field) is str and field in FIELDS and
              (key, field) not in seen and field in lookup[key],
              "Unknown or duplicate hand/field correction")
        seen.add((key, field))
        old = lookup[key][field]
        check(type(entry["expected_value_sha256"]) is str and
              entry["expected_value_sha256"] == digest(old), "Stale correction value")
        new = entry["proposed_value"]
        validate_value(field, new)
        if field == "hero_cards" and new is not None:
            variant = lookup[key].get("variant")
            check(variant in ("PLO5", "PLO6") and
                  len(new) == (5 if variant == "PLO5" else 6),
                  "Proposed cards inconsistent with PLO variant")
        check(canonical(old) != canonical(new), "No-op correction")
        check(type(entry["reason"]) is str and 1 <= len(entry["reason"].strip()) <= 500 and
              all(ord(c) >= 32 or c == "\n" for c in entry["reason"]),
              "Invalid correction reason")
        confidence = entry["confidence_subjective"]
        check(finite_number(confidence) and 0 <= confidence <= 1,
              "Invalid correction confidence")
        out.append({**entry, "original_value": old, "review_state": "pending_independent_review"})
    out.sort(key=lambda e: (e["table_id"], e["hand_label_human_assigned"], e["field"]))
    return {"schema_version": 1, "status": "manual_correction_proposals_not_video_verified",
            "job_id": draft["job_id"], "source_recording_sha256": draft["source_sha256"],
            "source_draft_sha256": digest(draft), "reviewer_label": label,
            "corrections": out, "counts": {"pending": len(out), "accepted": 0},
            "hand_reconstruction_verified": False, "source_pts_verified": False,
            "ready_for_equity_or_ev": False, "automatic_clip_selection_authorized": False,
            "limitations": ["Proposals do not mutate the source draft or prove OCR/video accuracy.",
                            "Proposed timestamps and actions are human claims, not verified PTS.",
                            "Cross-field consistency and independent review remain necessary.",
                            "Do not recompute equity/EV or select clips from unaccepted proposals."]}


def export_overlay(draft_path, submission_path, output_path):
    a, b, output = map(Path, (draft_path, submission_path, output_path))
    check(len({p.resolve() for p in (a, b, output)}) == 3 and
          output.suffix.lower() == ".json" and output.parent.is_dir() and
          not output.parent.is_symlink() and not output.exists(), "Unsafe output path")
    draft, raw_a = read_json(a)
    submission, raw_b = read_json(b)
    result = build_overlay(draft, submission)
    payload = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False).encode() + b"\n"
    check(len(payload) <= MAX_INPUT, "Oversized output")
    check(a.read_bytes() == raw_a and b.read_bytes() == raw_b, "Input changed during review")
    fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            check(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Unsafe output")
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("draft_json")
    p.add_argument("manual_corrections_json")
    p.add_argument("new_overlay_json")
    args = p.parse_args(argv)
    report = export_overlay(args.draft_json, args.manual_corrections_json, args.new_overlay_json)
    print(json.dumps(report["counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
