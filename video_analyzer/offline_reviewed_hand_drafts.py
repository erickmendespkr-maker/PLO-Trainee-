"""Offline draft hand histories from *human-reviewed* OCR observations.

Usage: python offline_reviewed_hand_drafts.py REVIEWED_JSON BOUNDARIES_JSON NEW_OUTPUT_DIR

Boundaries JSON: {"schema_version":1,"reviewed_report_sha256":"...",
"hands":[{"hand_id":"H001","table_id":1,"variant":"PLO5",
"start_seconds":1.0,"end_seconds":22.0,"note":"Manually marked"}]}

No automatic hand boundary inference, no equity or EV authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

MAX_JSON = 4 * 1024 * 1024
SHA = re.compile(r"[a-f0-9]{64}\Z")
HAND = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
CARD = re.compile(r"[2-9TJQKA][cdhs]\Z")
AMOUNT = re.compile(r"(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?\Z")
FIELDS = {"hero_cards", "board", "pot", "bet", "stack", "action"}
RESOLVED = {"confirmed", "corrected"}
DECISIONS = RESOLVED | {"rejected", "inconclusive", "pending"}
ACTIONS = {"fold", "check", "call", "bet", "raise", "all-in"}


def check(ok, message):
    if not ok:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        check(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def read_json(path):
    path = Path(path)
    check(path.is_file() and not path.is_symlink()
          and 0 < path.stat().st_size <= MAX_JSON, "Unsafe JSON input")
    return json.loads(path.read_text("utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def validate_value(field, value, variant=None):
    check(type(value) is str and 0 < len(value) <= 128 and value == value.strip(),
          "Invalid reviewed field value")
    if field in {"pot", "bet", "stack"}:
        check(AMOUNT.fullmatch(value) is not None, "Invalid amount")
    elif field == "action":
        check(value in ACTIONS, "Invalid action")
    else:
        cards = value.split(" ")
        check(all(CARD.fullmatch(c) for c in cards) and len(set(cards)) == len(cards),
              "Invalid or duplicate cards")
        if field == "hero_cards":
            check(len(cards) in (5, 6), "Invalid hero card count")
            if variant is not None:
                check(len(cards) == (5 if variant == "PLO5" else 6),
                      "Hero card count incompatible with variant")
        else:
            check(1 <= len(cards) <= 5, "Invalid board card count")


def build(reviewed_path, boundaries_path, output_dir):
    reviewed_path, boundaries_path, output_dir = map(
        Path, (reviewed_path, boundaries_path, output_dir))
    check(output_dir.parent.is_dir() and not output_dir.parent.is_symlink()
          and not output_dir.exists() and not output_dir.is_symlink()
          and HAND.fullmatch(output_dir.name) is not None, "Unsafe output directory")
    report_sha, boundaries_sha = digest(reviewed_path), digest(boundaries_path)
    report, boundary_doc = read_json(reviewed_path), read_json(boundaries_path)
    check(type(report) is dict and type(report.get("schema_version")) is int
          and report["schema_version"] == 1
          and report.get("analysis_status") == "offline_human_reviewed_ocr_observations_only"
          and report.get("ready_for_equity_or_ev") is False
          and report.get("hands_reconstructed") is False
          and type(report.get("observations")) is list
          and 1 <= len(report["observations"]) <= 64
          and type(report.get("source_roi_ocr_report_sha256")) is str
          and SHA.fullmatch(report["source_roi_ocr_report_sha256"]) is not None,
          "Invalid reviewed report provenance")
    check(type(boundary_doc) is dict
          and set(boundary_doc) == {"schema_version", "reviewed_report_sha256", "hands"}
          and type(boundary_doc["schema_version"]) is int
          and boundary_doc["schema_version"] == 1
          and boundary_doc["reviewed_report_sha256"] == report_sha
          and type(boundary_doc["hands"]) is list
          and 1 <= len(boundary_doc["hands"]) <= 200,
          "Invalid hand boundary provenance")
    obs, seen_indices = [], set()
    for item in report["observations"]:
        check(type(item) is dict
              and type(item.get("proposal_index")) is int
              and item["proposal_index"] >= 0
              and item["proposal_index"] not in seen_indices
              and type(item.get("table_id")) is int and 1 <= item["table_id"] <= 4
              and finite_number(item.get("decoded_source_pts_seconds"))
              and item.get("field") in FIELDS
              and item.get("decision") in DECISIONS
              and type(item.get("source_frame_sha256")) is str
              and SHA.fullmatch(item["source_frame_sha256"]) is not None
              and type(item.get("roi_png_sha256")) is str
              and SHA.fullmatch(item["roi_png_sha256"]) is not None,
              "Invalid reviewed observation")
        seen_indices.add(item["proposal_index"])
        if item["decision"] in RESOLVED:
            validate_value(item["field"], item.get("normalized_value"))
        else:
            check(item.get("normalized_value") is None, "Unresolved value cannot be used")
        obs.append(item)
    hands, seen_hands, by_table = [], set(), {i: [] for i in range(1, 5)}
    for item in boundary_doc["hands"]:
        check(type(item) is dict
              and set(item) == {"hand_id", "table_id", "variant",
                                "start_seconds", "end_seconds", "note"}
              and type(item["hand_id"]) is str and HAND.fullmatch(item["hand_id"])
              and item["hand_id"] not in seen_hands
              and type(item["table_id"]) is int and 1 <= item["table_id"] <= 4
              and item["variant"] in ("PLO5", "PLO6")
              and finite_number(item["start_seconds"])
              and finite_number(item["end_seconds"])
              and item["start_seconds"] < item["end_seconds"]
              and type(item["note"]) is str and 0 < len(item["note"].strip()) <= 500,
              "Invalid manual hand boundary")
        seen_hands.add(item["hand_id"])
        by_table[item["table_id"]].append(item)
    for table_hands in by_table.values():
        table_hands.sort(key=lambda x: x["start_seconds"])
        for earlier, later in zip(table_hands, table_hands[1:]):
            check(earlier["end_seconds"] <= later["start_seconds"],
                  "Overlapping hands on same table")
    assigned = set()
    for table_id in range(1, 5):
        for boundary in by_table[table_id]:
            included = [x for x in obs if x["table_id"] == table_id
                        and boundary["start_seconds"] <= x["decoded_source_pts_seconds"]
                        < boundary["end_seconds"]]
            assigned.update(x["proposal_index"] for x in included)
            included.sort(key=lambda x: (x["decoded_source_pts_seconds"], x["proposal_index"]))
            values, conflicts, unresolved = {}, [], []
            for entry in included:
                field = entry["field"]
                if entry["decision"] not in RESOLVED:
                    unresolved.append(entry["proposal_index"])
                    continue
                value = entry["normalized_value"]
                validate_value(field, value, boundary["variant"])
                values.setdefault(field, []).append({
                    "value": value, "timestamp_seconds": entry["decoded_source_pts_seconds"],
                    "proposal_index": entry["proposal_index"], "review": entry["decision"]})
            hero_sets = {frozenset(entry["value"].split()) for entry in values.get("hero_cards", [])}
            if len(hero_sets) > 1:
                conflicts.append("conflicting_hero_cards_observations")
            board_snapshots = [entry["value"].split() for entry in values.get("board", [])]
            if any(not (a == b[:len(a)] or b == a[:len(b)])
                   for a in board_snapshots for b in board_snapshots):
                conflicts.append("conflicting_board_observations")
            for hero in values.get("hero_cards", []):
                for board in values.get("board", []):
                    if set(hero["value"].split()) & set(board["value"].split()):
                        conflicts.append("hero_board_card_collision")
            missing = [f for f in ("hero_cards", "board", "pot", "action")
                       if f not in values]
            if not included:
                conflicts.append("no_observations_in_interval")
            hands.append({
                "hand_id": boundary["hand_id"], "table_id": table_id,
                "variant": boundary["variant"],
                "start_seconds": boundary["start_seconds"],
                "end_seconds": boundary["end_seconds"],
                "boundary_origin": "manual_unverified",
                "boundary_note": boundary["note"],
                "observation_indices": [x["proposal_index"] for x in included],
                "reviewed_fields": values, "unresolved_indices": unresolved,
                "missing_fields": missing, "consistency_warnings": sorted(set(conflicts)),
                "status": "draft_requires_human_reconstruction",
                "ready_for_equity_or_ev": False})
    result = {
        "schema_version": 1,
        "analysis_status": "offline_reviewed_hand_drafts_only",
        "source_reviewed_report_sha256": report_sha,
        "source_boundaries_sha256": boundaries_sha,
        "source_roi_ocr_report_sha256": report["source_roi_ocr_report_sha256"],
        "hands_reconstructed": False, "ready_for_equity_or_ev": False,
        "hands": hands,
        "unassigned_observation_indices": sorted(
            x["proposal_index"] for x in obs if x["proposal_index"] not in assigned),
        "warning": "Manual intervals and reviewed OCR are incomplete evidence; no equity or EV."}
    with tempfile.TemporaryDirectory(prefix=".plo_drafts_", dir=output_dir.parent) as temp:
        stage = Path(temp)
        (stage / "hand_drafts.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", "utf-8")
        check(digest(reviewed_path) == report_sha
              and digest(boundaries_path) == boundaries_sha, "Inputs changed during processing")
        check(not output_dir.exists(), "Output appeared during processing")
        os.rename(stage, output_dir)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reviewed_json")
    parser.add_argument("boundaries_json")
    parser.add_argument("new_output_dir")
    args = parser.parse_args(argv)
    result = build(args.reviewed_json, args.boundaries_json, args.new_output_dir)
    print(json.dumps({"drafts": len(result["hands"]),
                      "unassigned": len(result["unassigned_observation_indices"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
