"""Create offline, *incomplete* hand candidates from SHA-verified human OCR reviews.

Usage: python offline_four_table_hand_candidates.py BUNDLE OCR_JSON REVIEW_MANIFEST
       REVIEWED_FIELDS_JSON HAND_WINDOWS_JSON NEW_OUTPUT_JSON [--recording MP4]

HAND_WINDOWS_JSON v1: {"schema_version":1,"source_reviewed_fields_sha256":"...",
 "hands":[{"hand_id":"h1","table_id":1,"game_type":"PLO5",
 "start_pts_seconds":0.0,"end_pts_seconds":12.0,
 "boundaries_visually_checked":true,"observation_indices":[0,3]}]}

The windows and game type are human declarations, not machine inferences. Even
complete-looking snapshots cannot prove action order, hidden cards or ranges.
No equity, EV, automatic clip selection or playable poker is performed.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import tempfile

from offline_four_table_ocr_human_review import read, review, sha, require
from offline_four_table_sample_review import verify_bundle

HAND_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
MAX_HANDS = 64
MAX_OBSERVATIONS = 32


def build(bundle_path, ocr_path, review_manifest_path, reviewed_path,
          windows_path, output_path, *, recording_path=None):
    bundle, ocr, decisions, reviewed, windows, output = map(Path, (
        bundle_path, ocr_path, review_manifest_path, reviewed_path, windows_path,
        output_path))
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink(), "Output must be new")
    require(not output.resolve().is_relative_to(bundle.resolve()),
            "Output must be outside source bundle")
    require(all(output.resolve() != p.resolve() for p in (ocr, decisions, reviewed, windows)),
            "Output cannot replace input")
    input_hashes = {str(p): sha(p) for p in (ocr, decisions, reviewed, windows)}
    # Re-run the previous human-review validator against original crops and OCR.
    # Compare the *entire* verified result; an edited review JSON cannot pass.
    with tempfile.TemporaryDirectory(prefix="plo_hand_verify_", dir=output.parent) as folder:
        verification = Path(folder) / "verified.json"
        expected = review(bundle, ocr, decisions, verification,
                          recording_path=recording_path)
        actual = read(reviewed)
        require(actual == expected and sha(verification) == input_hashes[str(reviewed)],
                "Reviewed OCR report does not match verified source")
    source = verify_bundle(bundle, recording_path)
    manifest = read(windows)
    require(type(manifest) is dict and set(manifest) ==
            {"schema_version", "source_reviewed_fields_sha256", "hands"} and
            type(manifest["schema_version"]) is int and manifest["schema_version"] == 1 and
            manifest["source_reviewed_fields_sha256"] == input_hashes[str(reviewed)],
            "Invalid hand-window manifest binding")
    hands = manifest["hands"]
    require(type(hands) is list and 1 <= len(hands) <= MAX_HANDS,
            "Expected 1..64 hand candidates")
    candidates, seen_ids, used_indices, windows_by_table = [], set(), set(), {}
    observations = actual["reviewed_candidates"]
    require(type(observations) is list and len(observations) <= MAX_OBSERVATIONS,
            "Invalid reviewed observation count")
    duration = source["recording_duration_seconds"]
    for hand in hands:
        require(type(hand) is dict and set(hand) == {
            "hand_id", "table_id", "game_type", "start_pts_seconds",
            "end_pts_seconds", "boundaries_visually_checked", "observation_indices"},
            "Invalid hand candidate fields")
        hid, table, game = hand["hand_id"], hand["table_id"], hand["game_type"]
        start, end = hand["start_pts_seconds"], hand["end_pts_seconds"]
        require(type(hid) is str and HAND_ID.fullmatch(hid) and hid not in seen_ids,
                "Invalid or duplicate hand ID")
        seen_ids.add(hid)
        require(type(table) is int and table in {r["table_id"] for r in source["regions"]}
                and game in ("PLO5", "PLO6") and type(game) is str,
                "Invalid table or game declaration")
        require(type(start) in (int, float) and type(end) in (int, float) and
                math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= duration,
                "Invalid hand time window")
        require(hand["boundaries_visually_checked"] is True,
                "Hand boundaries require explicit human visual check")
        previous_end = windows_by_table.get(table, -1.0)
        require(start >= previous_end, "Overlapping or unordered hands on one table")
        windows_by_table[table] = end
        indices = hand["observation_indices"]
        require(type(indices) is list and 1 <= len(indices) <= MAX_OBSERVATIONS and
                all(type(i) is int and 0 <= i < len(observations) for i in indices) and
                indices == sorted(set(indices)), "Invalid or duplicate observation indices")
        require(not used_indices.intersection(indices), "Observation reused across hands")
        used_indices.update(indices)
        timeline, values_by_field = [], {}
        for i in indices:
            item = observations[i]
            require(item["review_decision"] in ("confirm", "correct") and
                    item["visual_evidence_checked"] is True and
                    type(item["reviewed_value"]) is str and
                    item["table_id"] == table, "Rejected or cross-table observation")
            pts = item["decoded_source_pts_seconds"]
            require(type(pts) in (int, float) and math.isfinite(pts) and
                    start <= pts <= end, "Observation outside declared hand window")
            field, value = item["field"], item["reviewed_value"]
            values_by_field.setdefault(field, set()).add(value)
            timeline.append({"reviewed_candidate_index": i, "pts_seconds": pts,
                             "field": field, "value": value,
                             "source_crop_sha256": item["source_crop_sha256"],
                             "source_crop_path": item["source_crop_path"],
                             "review_decision": item["review_decision"]})
        timeline.sort(key=lambda x: (x["pts_seconds"], x["reviewed_candidate_index"]))
        conflicts = [field for field in sorted(values_by_field)
                     if field in ("hero_cards", "board") and len(values_by_field[field]) > 1]
        # A board can legitimately grow across streets; multiple values require
        # a separate street-level review, not silent resolution.
        card_collisions = []
        for pts in sorted({x["pts_seconds"] for x in timeline}):
            at_pts = {x["field"]: x["value"].split() for x in timeline
                      if x["pts_seconds"] == pts and x["field"] in ("hero_cards", "board")}
            if "hero_cards" in at_pts and "board" in at_pts:
                shared = sorted(set(at_pts["hero_cards"]) & set(at_pts["board"]))
                if shared:
                    card_collisions.append({"pts_seconds": pts, "cards": shared})
        missing = [field for field in ("hero_cards", "board", "pot", "action")
                   if field not in values_by_field]
        candidates.append({"hand_id": hid, "table_id": table, "declared_game_type": game,
                           "start_pts_seconds": float(start), "end_pts_seconds": float(end),
                           "boundaries_human_declared_and_visually_checked": True,
                           "observations": timeline, "missing_observed_fields": missing,
                           "changing_card_fields_needing_street_review": conflicts,
                           "same_timestamp_card_collisions": card_collisions,
                           "complete_hand_reconstructed": False,
                           "ready_for_equity_or_ev": False,
                           "status": "incomplete_hand_candidate_requires_action_history_and_ranges"})
    require(all(sha(p) == digest for p, digest in ((Path(k), v) for k, v in input_hashes.items())),
            "Source JSON changed during grouping")
    require(verify_bundle(bundle, recording_path) == source,
            "Source crops changed during grouping")
    result = {"schema_version": 1, "analysis_status": "human_declared_incomplete_hand_candidates",
              "recording_sha256": source["recording_sha256"],
              "source_reviewed_fields_sha256": input_hashes[str(reviewed)],
              "hand_windows_manifest_sha256": input_hashes[str(windows)],
              "source_region_samples_sha256": actual["source_region_samples_sha256"],
              "hands": candidates, "complete_hand_reconstructed": False,
              "ready_for_equity_or_ev": False, "automatic_clip_selection_authorized": False,
              "warning": "Sparse reviewed observations do not establish complete action history, opponent ranges, equity or EV."}
    with tempfile.TemporaryDirectory(prefix="plo_hand_output_", dir=output.parent) as folder:
        stage = Path(folder) / "hands.json"
        stage.write_text(json.dumps(result, indent=2, ensure_ascii=False,
                                    allow_nan=False) + "\n", encoding="utf-8")
        os.link(stage, output)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("bundle", "ocr_report", "review_manifest", "reviewed_fields",
                "hand_windows", "new_output_json"):
        parser.add_argument(arg)
    parser.add_argument("--recording")
    args = parser.parse_args(argv)
    result = build(args.bundle, args.ocr_report, args.review_manifest,
                   args.reviewed_fields, args.hand_windows, args.new_output_json,
                   recording_path=args.recording)
    print(json.dumps({"status": result["analysis_status"], "hands": len(result["hands"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
