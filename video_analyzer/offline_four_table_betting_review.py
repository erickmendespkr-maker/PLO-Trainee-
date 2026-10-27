"""Offline, fail-closed manual betting-action review for PLO5/PLO6 recordings.

This module does NOT reconstruct unobserved actions, infer ranges, or enable
Monte Carlo/EV. It binds a human review to an immutable action-audit report.

Usage:
  python offline_four_table_betting_review.py template AUDIT.json NEW_TEMPLATE.json
  python offline_four_table_betting_review.py review AUDIT.json REVIEW.json NEW_RESULT.json
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

MAX_BYTES = 4 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
ACTOR = re.compile(r"(?:hero|seat_[1-9])\Z")
AMOUNT = re.compile(r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,2})?\Z")
STREET_ORDER = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}
ACTION_SET = {"fold", "check", "call", "bet", "raise", "all-in"}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha256(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "Invalid or symlinked file")
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def unique(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, "Duplicate JSON key")
        result[k] = v
    return result


def read_json(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= MAX_BYTES,
            "Invalid, symlinked or oversized input")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def amount(value):
    require(type(value) is str and AMOUNT.fullmatch(value), "Invalid chip amount")
    try:
        result = Decimal(value)
    except InvalidOperation as e:
        raise ValueError("Invalid chip amount") from e
    require(result.is_finite(), "Non-finite chip amount")
    return result


def audit_schema(audit):
    require(type(audit) is dict and set(audit) == {
        "schema_version", "analysis_status", "source_hand_candidates_sha256",
        "recording_sha256", "recording_hash_checked_in_this_run", "hands",
        "complete_hand_reconstructed", "ready_for_equity_or_ev",
        "automatic_clip_selection_authorized", "warning"}, "Invalid audit schema")
    require(type(audit["schema_version"]) is int and audit["schema_version"] == 1 and
            audit["analysis_status"] == "offline_action_street_candidates_only" and
            audit["complete_hand_reconstructed"] is False and
            audit["ready_for_equity_or_ev"] is False and
            audit["automatic_clip_selection_authorized"] is False and
            type(audit["recording_hash_checked_in_this_run"]) is bool and
            type(audit["warning"]) is str, "Audit is not a candidate-only report")
    for key in ("source_hand_candidates_sha256", "recording_sha256"):
        require(type(audit[key]) is str and HEX.fullmatch(audit[key]), "Invalid audit hash")
    require(type(audit["hands"]) is list and 1 <= len(audit["hands"]) <= 64,
            "Invalid hand count")
    seen_hands, seen_actions = set(), set()
    for hand in audit["hands"]:
        require(type(hand) is dict and set(hand) == {
            "hand_id", "table_id", "declared_game_type", "board_snapshots",
            "observed_action_labels", "observed_amounts", "review_flags",
            "action_history_complete", "opponent_ranges_known", "ready_for_equity_or_ev",
            "status"}, "Invalid audited hand schema")
        require(type(hand["hand_id"]) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", hand["hand_id"])
                and hand["hand_id"] not in seen_hands, "Duplicate/invalid hand ID")
        seen_hands.add(hand["hand_id"])
        require(type(hand["table_id"]) is int and 1 <= hand["table_id"] <= 4 and
                hand["declared_game_type"] in ("PLO5", "PLO6") and
                hand["action_history_complete"] is False and
                hand["opponent_ranges_known"] is False and
                hand["ready_for_equity_or_ev"] is False and
                hand["status"] == "street_candidates_only_requires_human_action_reconstruction",
                "Invalid hand status")
        for name in ("board_snapshots", "observed_action_labels", "observed_amounts", "review_flags"):
            require(type(hand[name]) is list, "Invalid audited hand arrays")
        last = (-1.0, -1)
        for a in hand["observed_action_labels"]:
            require(type(a) is dict and set(a) == {
                "source_observation_index", "pts_seconds", "action_label", "street_candidate",
                "actor", "amount", "action_sequence_confirmed"}, "Invalid audit action")
            idx, pts = a["source_observation_index"], a["pts_seconds"]
            require(type(idx) is int and 0 <= idx < 32 and idx not in seen_actions and
                    type(pts) in (int, float) and math.isfinite(pts) and pts >= 0 and
                    (pts, idx) >= last and type(a["action_label"]) is str and a["action_label"] in ACTION_SET and
                    a["street_candidate"] in (None, "flop_candidate", "turn_candidate", "river_candidate") and
                    a["actor"] is None and a["amount"] is None and
                    a["action_sequence_confirmed"] is False, "Invalid audit action provenance")
            last = (pts, idx)
            seen_actions.add(idx)
    return audit


def safe_output(output, inputs):
    output = Path(output)
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink() and
            all(output.resolve() != Path(i).resolve() for i in inputs),
            "Output must be new and separate")
    return output


def write_new(output, data):
    with tempfile.TemporaryDirectory(prefix="plo_betting_review_", dir=output.parent) as tmp:
        stage = Path(tmp) / "report.json"
        stage.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        os.link(stage, output)


def make_template(audit_path, output_path):
    source = Path(audit_path)
    output = safe_output(output_path, (source,))
    before = sha256(source)
    audit = audit_schema(read_json(source))
    hands = []
    for h in audit["hands"]:
        hands.append({"hand_id": h["hand_id"], "table_id": h["table_id"],
                      "units": "chips", "reviewer_notes": "",
                      "complete_action_sequence_claimed": False,
                      "actions": [{"source_observation_index": a["source_observation_index"],
                                   "actor": None, "street": None, "amount_contributed": None,
                                   "reviewer_note": "", "human_confirmed": False}
                                  for a in h["observed_action_labels"]]})
    result = {"schema_version": 1, "source_action_audit_sha256": before,
              "reviewer_confirmed_offline": False, "hands": hands}
    require(sha256(source) == before, "Audit changed while generating template")
    write_new(output, result)
    return result


def review(audit_path, review_path, output_path, *, recording_path=None):
    source, manual = Path(audit_path), Path(review_path)
    output = safe_output(output_path, (source, manual))
    before_a, before_m = sha256(source), sha256(manual)
    audit = audit_schema(read_json(source))
    review_data = read_json(manual)
    require(type(review_data) is dict and set(review_data) == {
        "schema_version", "source_action_audit_sha256", "reviewer_confirmed_offline", "hands"},
        "Invalid review manifest schema")
    require(type(review_data["schema_version"]) is int and review_data["schema_version"] == 1 and
            review_data["source_action_audit_sha256"] == before_a and
            review_data["reviewer_confirmed_offline"] is True and
            type(review_data["hands"]) is list and
            len(review_data["hands"]) == len(audit["hands"]), "Review not bound to audit")
    if recording_path is not None:
        recording = Path(recording_path)
        require(recording.is_file() and not recording.is_symlink() and
                sha256(recording) == audit["recording_sha256"], "Recording hash mismatch")
    results = []
    for original, reviewed in zip(audit["hands"], review_data["hands"]):
        require(type(reviewed) is dict and set(reviewed) == {
            "hand_id", "table_id", "units", "reviewer_notes",
            "complete_action_sequence_claimed", "actions"}, "Invalid reviewed hand")
        require(reviewed["hand_id"] == original["hand_id"] and
                type(reviewed["table_id"]) is int and reviewed["table_id"] == original["table_id"] and
                reviewed["units"] == "chips" and
                type(reviewed["reviewer_notes"]) is str and
                len(reviewed["reviewer_notes"]) <= 1000 and
                reviewed["complete_action_sequence_claimed"] is False and
                type(reviewed["actions"]) is list and
                len(reviewed["actions"]) == len(original["observed_action_labels"]),
                "Review does not match original hand")
        street_prev = -1
        actions, totals, flags = [], {s: Decimal(0) for s in STREET_ORDER}, []
        for raw, item in zip(original["observed_action_labels"], reviewed["actions"]):
            require(type(item) is dict and set(item) == {
                "source_observation_index", "actor", "street", "amount_contributed",
                "reviewer_note", "human_confirmed"}, "Invalid reviewed action")
            require(type(item["source_observation_index"]) is int and
                    item["source_observation_index"] == raw["source_observation_index"] and
                    type(item["actor"]) is str and ACTOR.fullmatch(item["actor"]) and
                    type(item["street"]) is str and item["street"] in STREET_ORDER and
                    STREET_ORDER[item["street"]] >= street_prev and
                    type(item["reviewer_note"]) is str and
                    1 <= len(item["reviewer_note"].strip()) <= 500 and
                    item["human_confirmed"] is True,
                    "Unconfirmed, reordered or invalid action review")
            street_prev = STREET_ORDER[item["street"]]
            if raw["action_label"] in ("check", "fold"):
                require(item["amount_contributed"] is None, "Fold/check cannot contribute chips")
                contribution = None
            else:
                contribution = amount(item["amount_contributed"])
                require(contribution > 0, "Bet/call/raise/all-in must contribute positive chips")
                totals[item["street"]] += contribution
            expected = raw["street_candidate"]
            if expected is not None:
                require(item["street"] == expected.removesuffix("_candidate"),
                        "Reviewed street conflicts with visually reviewed board")
            else:
                flags.append({"code": "street_supported_only_by_human_review",
                              "source_observation_index": raw["source_observation_index"]})
            actions.append({"source_observation_index": raw["source_observation_index"],
                            "pts_seconds": raw["pts_seconds"],
                            "action_label_as_observed": raw["action_label"],
                            "actor_human_assigned": item["actor"],
                            "street_human_assigned": item["street"],
                            "amount_contributed_human_assigned": str(contribution) if contribution is not None else None,
                            "reviewer_note": item["reviewer_note"],
                            "visually_supported_street_candidate": expected,
                            "human_confirmed_in_manifest": True})
        if original["review_flags"]:
            flags.append({"code": "upstream_visual_review_flags_remain",
                          "count": len(original["review_flags"])})
        results.append({"hand_id": original["hand_id"], "table_id": original["table_id"],
                        "declared_game_type": original["declared_game_type"],
                        "actions": actions,
                        "observed_action_count": len(actions),
                        "human_assigned_contributions_by_street": {k: str(v) for k, v in totals.items()},
                        "review_flags": flags,
                        "action_history_complete": False, "pot_accounting_reconciled": False,
                        "opponent_ranges_known": False, "ready_for_equity_or_ev": False})
    require(sha256(source) == before_a and sha256(manual) == before_m,
            "Input changed during review")
    if recording_path is not None:
        require(sha256(recording_path) == audit["recording_sha256"],
                "Recording changed during review")
    result = {"schema_version": 1,
              "analysis_status": "human_assigned_observed_actions_not_full_history",
              "source_action_audit_sha256": before_a,
              "source_human_review_sha256": before_m,
              "recording_sha256": audit["recording_sha256"],
              "recording_hash_checked_in_this_run": recording_path is not None,
              "hands": results,
              "complete_hand_reconstructed": False,
              "ready_for_equity_or_ev": False,
              "automatic_clip_selection_authorized": False,
              "warning": "Human assignment is not independent visual verification. Missing actions, blinds, side pots and ranges prevent pot reconciliation and EV."}
    write_new(output, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    t = sub.add_parser("template")
    t.add_argument("audit")
    t.add_argument("new_template")
    r = sub.add_parser("review")
    r.add_argument("audit")
    r.add_argument("manifest")
    r.add_argument("new_result")
    r.add_argument("--recording")
    args = parser.parse_args(argv)
    result = (make_template(args.audit, args.new_template) if args.command == "template"
              else review(args.audit, args.manifest, args.new_result, recording_path=args.recording))
    print(json.dumps({"status": result.get("analysis_status", "unconfirmed_review_template"),
                      "hands": len(result["hands"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
