"""Conservative offline street/action audit of human-reviewed PLO5/PLO6 hand candidates.

Usage: python offline_four_table_action_timeline_audit.py HAND_CANDIDATES_JSON NEW_AUDIT_JSON [--recording VIDEO]

Never infers actor, action order beyond timestamps, opponent ranges, hidden cards,
complete hands, or equity/EV. A street is only a *candidate* derived from a
visually reviewed board snapshot. This is not an authorization for mathematics.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import tempfile

HEX = re.compile(r"[0-9a-f]{64}\Z")
CARD = re.compile(r"[2-9TJQKA][cdhs]\Z")
AMOUNT = re.compile(r"(?:0|[1-9]\d{0,8})(?:\.\d{1,2})?\Z")
HAND_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
ACTIONS = {"fold", "check", "call", "bet", "raise", "all-in"}
FIELDS = {"hero_cards", "board", "pot", "bet", "stack", "action"}
STREETS = {3: "flop_candidate", 4: "turn_candidate", 5: "river_candidate"}
MAX_BYTES = 4 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def read(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_BYTES,
            "Invalid, symlinked, or oversized input")
    return json.loads(p.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def cards(value, expected=None):
    tokens = value.split(" ")
    require((expected is None or len(tokens) == expected) and
            1 <= len(tokens) <= 6 and all(CARD.fullmatch(t) for t in tokens) and
            len(set(tokens)) == len(tokens), "Invalid or repeated cards")
    return tokens


def observation(item, hand, used):
    keys = {"reviewed_candidate_index", "pts_seconds", "field", "value",
            "source_crop_sha256", "source_crop_path", "review_decision"}
    require(type(item) is dict and set(item) == keys, "Unexpected observation fields")
    idx, pts, field, value = (item[k] for k in
                              ("reviewed_candidate_index", "pts_seconds", "field", "value"))
    require(type(idx) is int and 0 <= idx < 32 and idx not in used,
            "Duplicate or invalid source observation index")
    used.add(idx)
    require(type(pts) in (int, float) and math.isfinite(pts) and
            hand["start_pts_seconds"] <= pts <= hand["end_pts_seconds"],
            "Observation timestamp outside hand")
    require(type(field) is str and field in FIELDS and type(value) is str and
            0 < len(value) <= 128 and item["review_decision"] in ("confirm", "correct"),
            "Invalid or unreviewed observation")
    require(type(item["source_crop_sha256"]) is str and HEX.fullmatch(item["source_crop_sha256"]),
            "Invalid crop hash")
    path = item["source_crop_path"]
    require(type(path) is str and 0 < len(path) <= 256 and "\\" not in path and
            not PurePosixPath(path).is_absolute() and
            all(part not in ("", ".", "..") for part in path.split("/")),
            "Unsafe crop reference")
    if field == "hero_cards":
        cards(value, 5 if hand["declared_game_type"] == "PLO5" else 6)
    elif field == "board":
        require(len(cards(value)) <= 5, "Board cannot exceed five cards")
    elif field in ("pot", "bet", "stack"):
        require(AMOUNT.fullmatch(value), "Invalid numeric field")
    else:
        require(value in ACTIONS, "Invalid action")
    return {"source_observation_index": idx, "pts_seconds": float(pts),
            "field": field, "value": value,
            "source_crop_sha256": item["source_crop_sha256"]}


def audit_hand(hand, used):
    keys = {"hand_id", "table_id", "declared_game_type", "start_pts_seconds",
            "end_pts_seconds", "boundaries_human_declared_and_visually_checked",
            "observations", "missing_observed_fields", "changing_card_fields_needing_street_review",
            "same_timestamp_card_collisions", "complete_hand_reconstructed",
            "ready_for_equity_or_ev", "status"}
    require(type(hand) is dict and set(hand) == keys, "Invalid hand schema")
    require(type(hand["hand_id"]) is str and HAND_ID.fullmatch(hand["hand_id"]),
            "Invalid hand ID")
    require(type(hand["table_id"]) is int and 1 <= hand["table_id"] <= 4 and
            hand["declared_game_type"] in ("PLO5", "PLO6") and
            type(hand["declared_game_type"]) is str, "Invalid table or game")
    start, end = hand["start_pts_seconds"], hand["end_pts_seconds"]
    require(type(start) in (int, float) and type(end) in (int, float) and
            math.isfinite(start) and math.isfinite(end) and 0 <= start < end and
            hand["boundaries_human_declared_and_visually_checked"] is True and
            hand["complete_hand_reconstructed"] is False and
            hand["ready_for_equity_or_ev"] is False and
            hand["status"] == "incomplete_hand_candidate_requires_action_history_and_ranges",
            "Invalid boundaries or unsafe math status")
    for name in ("missing_observed_fields", "changing_card_fields_needing_street_review",
                 "same_timestamp_card_collisions"):
        require(type(hand[name]) is list, "Invalid review flags")
    raw = hand["observations"]
    require(type(raw) is list and 1 <= len(raw) <= 32, "Invalid observation count")
    timeline = [observation(o, hand, used) for o in raw]
    require(timeline == sorted(timeline, key=lambda x: (x["pts_seconds"], x["source_observation_index"])),
            "Unsorted source timeline")
    board_snapshots, issues, actions, amounts = [], [], [], []
    latest_board = None
    board_conflicted = False
    hero_sets = []
    last_pot = None
    for pts in sorted({o["pts_seconds"] for o in timeline}):
        group = [o for o in timeline if o["pts_seconds"] == pts]
        boards = [o for o in group if o["field"] == "board"]
        heroes = [o for o in group if o["field"] == "hero_cards"]
        if len({o["value"] for o in boards}) > 1:
            issues.append({"code": "conflicting_board_same_timestamp", "pts_seconds": pts})
            board_conflicted = True
        if len({o["value"] for o in heroes}) > 1:
            issues.append({"code": "conflicting_hero_same_timestamp", "pts_seconds": pts})
        if heroes:
            current_hero = set(cards(heroes[0]["value"]))
            if hero_sets and current_hero != hero_sets[-1]:
                issues.append({"code": "hero_cards_changed_within_hand", "pts_seconds": pts})
            hero_sets.append(current_hero)
        if boards:
            board = cards(boards[0]["value"])
            if len(board) not in STREETS:
                issues.append({"code": "partial_board_not_a_street", "pts_seconds": pts})
                board_conflicted = True
            if latest_board is not None:
                if len(board) < len(latest_board):
                    issues.append({"code": "board_shrank_within_hand", "pts_seconds": pts})
                    board_conflicted = True
                elif board[:len(latest_board)] != latest_board:
                    issues.append({"code": "board_changed_not_prefix", "pts_seconds": pts})
                    board_conflicted = True
            latest_board = board
            board_snapshots.append({"pts_seconds": pts, "cards": board,
                                    "street_candidate": STREETS.get(len(board))})
        if latest_board is not None and any(set(latest_board) & h for h in hero_sets):
            if not any(i["code"] == "visible_hero_board_card_collision" for i in issues):
                issues.append({"code": "visible_hero_board_card_collision", "pts_seconds": pts})
            board_conflicted = True
        # A board first appearing at a timestamp cannot establish the action street
        # for actions at that same timestamp. Never promote this to a fact.
        action_street = (STREETS.get(len(latest_board)) if latest_board is not None and
                         not boards and not board_conflicted else None)
        for item in group:
            if item["field"] == "action":
                actions.append({"source_observation_index": item["source_observation_index"],
                                "pts_seconds": pts, "action_label": item["value"],
                                "street_candidate": action_street,
                                "actor": None, "amount": None,
                                "action_sequence_confirmed": False})
            if item["field"] in ("pot", "bet", "stack"):
                amount = Decimal(item["value"])
                if item["field"] == "pot":
                    if last_pot is not None and amount < last_pot:
                        issues.append({"code": "pot_decreased_review_context", "pts_seconds": pts})
                    last_pot = amount
                amounts.append({"source_observation_index": item["source_observation_index"],
                                "pts_seconds": pts, "field": item["field"],
                                "amount_as_observed": item["value"],
                                "currency_and_units_confirmed": False})
    if not actions:
        issues.append({"code": "no_observed_actions", "pts_seconds": None})
    if not board_snapshots:
        issues.append({"code": "no_observed_board", "pts_seconds": None})
    return {"hand_id": hand["hand_id"], "table_id": hand["table_id"],
            "declared_game_type": hand["declared_game_type"],
            "board_snapshots": board_snapshots, "observed_action_labels": actions,
            "observed_amounts": amounts, "review_flags": issues,
            "action_history_complete": False, "opponent_ranges_known": False,
            "ready_for_equity_or_ev": False,
            "status": "street_candidates_only_requires_human_action_reconstruction"}


def build(candidates_path, output_path, *, recording_path=None):
    source, output = Path(candidates_path), Path(output_path)
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink() and
            output.resolve() != source.resolve(), "Output must be new and separate")
    input_sha = sha(source) if source.is_file() and not source.is_symlink() else None
    data = read(source)
    expected = {"schema_version", "analysis_status", "recording_sha256",
                "source_reviewed_fields_sha256", "hand_windows_manifest_sha256",
                "source_region_samples_sha256", "hands", "complete_hand_reconstructed",
                "ready_for_equity_or_ev", "automatic_clip_selection_authorized", "warning"}
    require(type(data) is dict and set(data) == expected and
            type(data["schema_version"]) is int and data["schema_version"] == 1 and
            data["analysis_status"] == "human_declared_incomplete_hand_candidates" and
            data["complete_hand_reconstructed"] is False and
            data["ready_for_equity_or_ev"] is False and
            data["automatic_clip_selection_authorized"] is False,
            "Not a verified-schema incomplete hand candidate report")
    for key in ("recording_sha256", "source_reviewed_fields_sha256",
                "hand_windows_manifest_sha256", "source_region_samples_sha256"):
        require(type(data[key]) is str and HEX.fullmatch(data[key]), "Invalid source hash")
    require(type(data["warning"]) is str, "Missing warning")
    if recording_path is not None:
        recording = Path(recording_path)
        require(recording.is_file() and not recording.is_symlink() and
                sha(recording) == data["recording_sha256"], "Recording hash mismatch")
    hands = data["hands"]
    require(type(hands) is list and 1 <= len(hands) <= 64, "Invalid hands count")
    used, ids, windows = set(), set(), {}
    audited = []
    for hand in hands:
        item = audit_hand(hand, used)
        require(item["hand_id"] not in ids, "Duplicate hand ID")
        ids.add(item["hand_id"])
        table = item["table_id"]
        require(hand["start_pts_seconds"] >= windows.get(table, -1),
                "Overlapping or unordered hands")
        windows[table] = hand["end_pts_seconds"]
        audited.append(item)
    require(sha(source) == input_sha, "Source changed during audit")
    if recording_path is not None:
        require(sha(recording_path) == data["recording_sha256"],
                "Recording changed during audit")
    result = {"schema_version": 1, "analysis_status": "offline_action_street_candidates_only",
              "source_hand_candidates_sha256": input_sha,
              "recording_sha256": data["recording_sha256"],
              "recording_hash_checked_in_this_run": recording_path is not None,
              "hands": audited, "complete_hand_reconstructed": False,
              "ready_for_equity_or_ev": False,
              "automatic_clip_selection_authorized": False,
              "warning": "Street labels are hypotheses from reviewed board snapshots. Actors, betting sequence, ranges and EV are not established; input JSON provenance must be verified upstream."}
    with tempfile.TemporaryDirectory(prefix="plo_action_audit_", dir=output.parent) as folder:
        stage = Path(folder) / "audit.json"
        stage.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                         encoding="utf-8")
        os.link(stage, output)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hand_candidates")
    parser.add_argument("new_audit_json")
    parser.add_argument("--recording")
    args = parser.parse_args(argv)
    result = build(args.hand_candidates, args.new_audit_json, recording_path=args.recording)
    print(json.dumps({"status": result["analysis_status"], "hands": len(result["hands"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
