"""Offline independent review of Cycle 118 correction proposals.

Accepted means a second human agreed to a *proposal*, not that a hand,
OCR, timestamps, equity, EV, or a clip is verified. Never mutates the draft.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from offline_hand_correction_overlay import (
    MAX_INPUT, build_overlay, canonical, check, digest, read_json, validate_draft,
)


def reviewer_label(value):
    check(type(value) is str and 1 <= len(value.strip()) <= 80 and
          all(ord(c) >= 32 for c in value), "Invalid reviewer label")
    return value.strip()


def verified_overlay(draft, overlay):
    """Recreate the overlay from the original draft to detect any tampering."""
    check(type(overlay) is dict and type(overlay.get("corrections")) is list,
          "Invalid overlay")
    reconstructed = build_overlay(draft, {
        "schema_version": 1, "job_id": overlay.get("job_id"),
        "source_draft_sha256": overlay.get("source_draft_sha256"),
        "reviewer_label": overlay.get("reviewer_label"),
        "corrections": [{key: value for key, value in row.items()
                         if key not in ("original_value", "review_state")}
                        for row in overlay["corrections"] if type(row) is dict],
    })
    check(canonical(reconstructed) == canonical(overlay), "Altered correction overlay")
    return reconstructed


def check_cross_fields(draft, accepted):
    """Only check known relationships, never infer missing cards/actions."""
    lookup = validate_draft(draft)
    combined = {key: dict(value) for key, value in lookup.items()}
    for row in accepted:
        key = (row["table_id"], row["hand_label_human_assigned"])
        combined[key][row["field"]] = row["proposed_value"]
    for entry in combined.values():
        hero = entry.get("hero_cards") or []
        board = entry.get("board_by_street") or {}
        community = (board.get("flop") or []) + [board.get(s) for s in ("turn", "river")
                                                 if board.get(s) is not None]
        check(len(hero + community) == len(set(hero + community)),
              "Conflicting hero and community cards")
        start, end = entry.get("source_pts_start_seconds"), entry.get("source_pts_end_seconds")
        check(start is None or end is None or start < end,
              "Invalid hand time interval")
        previous = None
        order = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}
        previous_street = -1
        for action in entry.get("actions") or []:
            pts = action["source_pts_seconds"]
            check(previous is None or pts >= previous, "Nonchronological actions")
            check(order[action["street"]] >= previous_street, "Street order reversed")
            check(start is None or pts >= start, "Action before hand start")
            check(end is None or pts <= end, "Action after hand end")
            previous, previous_street = pts, order[action["street"]]
        call, stack = entry.get("call_amount"), entry.get("effective_stack")
        check(call is None or stack is None or call <= stack,
              "Call exceeds effective stack")


def build_review(draft, overlay, decision_submission):
    verified_overlay(draft, overlay)
    check(type(decision_submission) is dict and set(decision_submission) == {
        "schema_version", "job_id", "source_draft_sha256", "overlay_sha256",
        "reviewer_label", "decisions"}, "Invalid review submission")
    check(type(decision_submission["schema_version"]) is int and
          decision_submission["schema_version"] == 1 and
          decision_submission["job_id"] == draft["job_id"] and
          decision_submission["source_draft_sha256"] == digest(draft) and
          decision_submission["overlay_sha256"] == digest(overlay),
          "Review is not bound to original inputs")
    first = reviewer_label(overlay["reviewer_label"])
    second = reviewer_label(decision_submission["reviewer_label"])
    check(first.casefold() != second.casefold(), "Independent reviewer required")
    rows = overlay["corrections"]
    decisions = decision_submission["decisions"]
    check(type(decisions) is list and len(decisions) == len(rows),
          "Every proposal requires one decision")
    by_id = {digest(row): row for row in rows}
    check(len(by_id) == len(rows), "Duplicate proposal identity")
    seen, resolved, accepted = set(), [], []
    for item in decisions:
        check(type(item) is dict and set(item) == {
            "correction_sha256", "decision", "reason"}, "Invalid decision fields")
        key = item["correction_sha256"]
        check(type(key) is str and key in by_id and key not in seen,
              "Unknown or repeated correction decision")
        seen.add(key)
        check(type(item["decision"]) is str and item["decision"] in
              ("accept", "reject"), "Invalid decision")
        reason = item["reason"]
        check(type(reason) is str and 1 <= len(reason.strip()) <= 500 and
              all(ord(c) >= 32 or c == "\n" for c in reason),
              "Invalid review reason")
        proposal = by_id[key]
        resolved.append({"correction_sha256": key, "decision": item["decision"],
                         "reason": reason})
        if item["decision"] == "accept":
            accepted.append(proposal)
    check(len(seen) == len(rows), "Missing review decision")
    check_cross_fields(draft, accepted)
    resolved.sort(key=lambda r: r["correction_sha256"])
    return {
        "schema_version": 1, "status": "independent_human_review_not_video_verified",
        "job_id": draft["job_id"], "source_recording_sha256": draft["source_sha256"],
        "source_draft_sha256": digest(draft), "overlay_sha256": digest(overlay),
        "proposer_label": first, "reviewer_label": second,
        "decisions": resolved,
        "counts": {"accepted": len(accepted), "rejected": len(rows) - len(accepted)},
        "hand_reconstruction_verified": False, "source_pts_verified": False,
        "ready_for_equity_or_ev": False, "automatic_clip_selection_authorized": False,
        "limitations": [
            "Human acceptance is not verification against source video or OCR.",
            "No correction is applied to the immutable original hand history.",
            "Cross-field checks cannot prove complete or correct hand reconstruction.",
            "Equity, EV and automatic clip selection remain blocked.",
        ],
    }


def export_review(draft_path, overlay_path, decisions_path, output_path):
    paths = [Path(p) for p in (draft_path, overlay_path, decisions_path, output_path)]
    output = paths[-1]
    check(len({p.resolve() for p in paths}) == 4 and output.suffix.lower() == ".json" and
          output.parent.is_dir() and not output.parent.is_symlink() and
          not output.exists(), "Unsafe output path")
    inputs = [read_json(p) for p in paths[:-1]]
    report = build_review(*(pair[0] for pair in inputs))
    payload = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode() + b"\n"
    check(len(payload) <= MAX_INPUT, "Oversized review output")
    check(all(path.read_bytes() == raw for path, (_, raw) in zip(paths, inputs)),
          "Review input changed during processing")
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
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("draft_json", "overlay_json", "decisions_json", "new_review_json"):
        parser.add_argument(arg)
    args = parser.parse_args(argv)
    print(json.dumps(export_review(args.draft_json, args.overlay_json,
                                   args.decisions_json, args.new_review_json)["counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
