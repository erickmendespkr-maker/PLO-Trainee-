"""Create an immutable *candidate* hand view from independently accepted edits.

Offline/asynchronous only. Never changes original drafts, overlays or reviews.
Acceptance is human agreement, NOT video/OCR/PTS verification, betting legality,
math readiness or authorization for automatic clip selection.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import stat

from offline_hand_correction_overlay import (
    MAX_INPUT, FIELDS, canonical, check, digest, read_json, validate_draft,
    validate_value,
)
from offline_hand_independent_review import build_review, check_cross_fields


REQUIRED_ENTRY = FIELDS | frozenset({"variant", "table_id", "hand_label_human_assigned"})
ATTESTATION_FIELDS = frozenset({"source_pts_checked_by_human", "reviewer_attestation"})


def validate_candidate_entry(entry, table_id, label):
    """Structural checks on the merged view; never attest video truth."""
    check(type(entry) is dict and set(entry) in (REQUIRED_ENTRY, REQUIRED_ENTRY | ATTESTATION_FIELDS),
          "Unexpected candidate hand fields")
    check(type(entry["table_id"]) is int and entry["table_id"] == table_id and
          type(entry["hand_label_human_assigned"]) is str and
          entry["hand_label_human_assigned"] == label and
          type(entry["variant"]) is str and entry["variant"] in ("PLO5", "PLO6"),
          "Invalid hand identity or variant")
    for field in FIELDS:
        validate_value(field, entry[field])
    hero = entry["hero_cards"]
    check(hero is None or len(hero) == (5 if entry["variant"] == "PLO5" else 6),
          "Wrong PLO card count")
    board = entry["board_by_street"]
    all_cards = (hero or []) + (board["flop"] or []) + [board[s] for s in ("turn", "river")
                                                     if board[s] is not None]
    check(len(all_cards) == len(set(all_cards)), "Duplicate visible cards")
    start, end = entry["source_pts_start_seconds"], entry["source_pts_end_seconds"]
    check((start is None and end is None) or
          (start is not None and end is not None and start < end),
          "Incomplete or reversed hand interval")
    if ATTESTATION_FIELDS <= set(entry):
        for flag in ATTESTATION_FIELDS:
            check(type(entry[flag]) is bool, "Invalid human attestation")
        check(not entry["source_pts_checked_by_human"] or start is not None,
              "PTS attestation without interval")
    last_street, last_pts = -1, -1.0
    street_rank = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}
    for action in entry["actions"]:
        street = action["street"]
        pts = action["source_pts_seconds"]
        check(street_rank[street] >= last_street and pts >= last_pts,
              "Nonchronological action")
        check(start is None or start <= pts <= end, "Action outside hand interval")
        amount = action["amount"]
        kind = action["action"]
        check(amount is not None and
              ((kind in ("fold", "check") and amount == 0) or
               (kind in ("call", "bet", "raise") and amount > 0)),
              "Invalid action amount")
        check(street == "preflop" or board["flop"] is not None,
              "Postflop action without visible flop")
        check(street not in ("turn", "river") or board["turn"] is not None,
              "Turn/river action without visible turn")
        check(street != "river" or board["river"] is not None,
              "River action without visible river")
        last_street, last_pts = street_rank[street], pts
    call, stack = entry["call_amount"], entry["effective_stack"]
    check(call is None or stack is None or call <= stack,
          "Call exceeds effective stack")


def build_snapshot(draft, overlay, review):
    """Reconstruct and authenticate the review chain, then derive a new view."""
    lookup = validate_draft(draft)
    check(type(review) is dict and type(review.get("decisions")) is list,
          "Invalid independent review")
    # Re-run the same validations that created the review. The exact canonical
    # comparison prevents altered counts, labels, gates or decision explanations.
    rebuilt = build_review(draft, overlay, {
        "schema_version": 1, "job_id": review.get("job_id"),
        "source_draft_sha256": review.get("source_draft_sha256"),
        "overlay_sha256": review.get("overlay_sha256"),
        "reviewer_label": review.get("reviewer_label"),
        "decisions": review["decisions"],
    })
    check(canonical(rebuilt) == canonical(review), "Tampered independent review")
    by_digest = {digest(row): row for row in overlay["corrections"]}
    accepted = []
    rejected = []
    for decision in review["decisions"]:
        row = by_digest[decision["correction_sha256"]]
        item = {"correction_sha256": decision["correction_sha256"],
                "table_id": row["table_id"],
                "hand_label_human_assigned": row["hand_label_human_assigned"],
                "field": row["field"], "review_reason": decision["reason"]}
        if decision["decision"] == "accept":
            accepted.append((row, item))
        else:
            rejected.append(item)
    check_cross_fields(draft, [row for row, _ in accepted])
    applied = {}
    for row, item in accepted:
        key = (row["table_id"], row["hand_label_human_assigned"])
        applied.setdefault(key, []).append((row, item))
    hands = []
    for original in draft["hands"]:
        key = (original["table_id"], original["hand_label_human_assigned"])
        entry = deepcopy(lookup[key])
        provenance = []
        for correction, item in sorted(applied.get(key, []), key=lambda pair: pair[0]["field"]):
            field = correction["field"]
            check(digest(entry[field]) == correction["expected_value_sha256"],
                  "Correction no longer matches original field")
            entry[field] = deepcopy(correction["proposed_value"])
            provenance.append({**item,
                "original_value_sha256": correction["expected_value_sha256"],
                "candidate_value_sha256": digest(entry[field]),
                "proposer_confidence_subjective": correction["confidence_subjective"],
                "proposer_reason": correction["reason"]})
        validate_candidate_entry(entry, *key)
        hands.append({"table_id": key[0], "hand_label_human_assigned": key[1],
                      "human_entry_candidate": entry,
                      "original_human_entry_sha256": digest(lookup[key]),
                      "candidate_human_entry_sha256": digest(entry),
                      "applied_corrections": provenance,
                      "human_attestation_fields_present": ATTESTATION_FIELDS <= set(entry),
                      "status": "human_reviewed_candidate_not_video_verified",
                      "hand_reconstruction_verified": False,
                      "source_pts_verified": False,
                      "ready_for_equity_or_ev": False,
                      "automatic_clip_selection_authorized": False})
    rejected.sort(key=lambda item: (item["table_id"], item["hand_label_human_assigned"],
                                    item["field"]))
    return {
        "schema_version": 1,
        "status": "derived_human_reviewed_snapshot_not_video_verified",
        "job_id": draft["job_id"],
        "source_recording_sha256": draft["source_sha256"],
        "source_draft_sha256": digest(draft),
        "source_overlay_sha256": digest(overlay),
        "source_review_sha256": digest(review),
        "hands": hands, "rejected_corrections": rejected,
        "counts": {"hands": len(hands), "accepted_applied": len(accepted),
                   "rejected_unapplied": len(rejected), "math_ready": 0},
        "source_pts_verified": False,
        "hand_reconstruction_verified": False,
        "ready_for_equity_or_ev": False,
        "automatic_clip_selection_authorized": False,
        "limitations": [
            "This is a derived candidate view; original files remain immutable.",
            "Second-review acceptance does not prove OCR, video or source PTS accuracy.",
            "Structural validation is not a complete betting-rule audit.",
            "Legacy drafts may lack human attestation fields; no attestations are inferred.",
            "No equity, EV, strategic verdict or automatic clip selection is authorized.",
        ],
    }


def export_snapshot(draft_path, overlay_path, review_path, output_path):
    paths = [Path(p) for p in (draft_path, overlay_path, review_path, output_path)]
    output = paths[-1]
    check(len({p.resolve() for p in paths}) == 4 and output.suffix.lower() == ".json" and
          output.parent.is_dir() and not output.parent.is_symlink() and
          not output.exists(), "Unsafe output path")
    sources = [read_json(p) for p in paths[:-1]]
    result = build_snapshot(*(pair[0] for pair in sources))
    payload = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False).encode() + b"\n"
    check(len(payload) <= MAX_INPUT, "Oversized output")
    check(all(path.read_bytes() == raw for path, (_, raw) in zip(paths, sources)),
          "Input changed during snapshot generation")
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
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("draft_json", "overlay_json", "independent_review_json", "new_snapshot_json"):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    result = export_snapshot(args.draft_json, args.overlay_json,
                             args.independent_review_json, args.new_snapshot_json)
    print(json.dumps(result["counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
