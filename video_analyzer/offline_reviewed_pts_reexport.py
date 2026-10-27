"""Explicit, create-only MP4 re-export after a second-stage offline PTS review.

A timestamp plan is NOT export authorization. A separate, self-declared human
approval is required; source frames, cards, actions, ranges and reviewer identity
are not authenticated by this module. Original clips and reports are immutable.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile

from offline_reviewed_decision_timeline import build_index, file_hash, load_json, require
from offline_reviewed_pts_second_review import (
    MAX_JSON_BYTES, PLAN_STATUS, _new_path, _root, _write_new, build_plan,
)
from offline_reviewed_math_clip_export import export as export_math_clip
from offline_reviewed_source_pts_audit import recording_hash

STATUS = "requires_separate_explicit_human_export_approval"
EXPORTED = "reexported_from_human_claim_not_visual_poker_verified"
NAME = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
FLAGS = ("reviewed_source_frames", "reviewed_corrected_window",
         "reviewed_math_and_range_assumptions")


def _evidence(recording, reference, proposals, second_review, plan_path, directories):
    root = _root(recording, reference, proposals, directories)
    plan_path = Path(plan_path)
    require(plan_path.parent.resolve() == root.resolve() and
            plan_path.is_file() and not plan_path.is_symlink(),
            "Plan must be a regular JSON beside pipeline results")
    plan = load_json(plan_path)
    plan_sha, _ = file_hash(plan_path, MAX_JSON_BYTES)
    expected = build_plan(recording, reference, proposals, second_review, directories)
    require(plan == expected and plan.get("status") == PLAN_STATUS and
            plan.get("approved_for_export") is False and
            plan.get("automatic_clip_selection_authorized") is False,
            "Stale or unauthorized timestamp plan")
    require(file_hash(plan_path, MAX_JSON_BYTES)[0] == plan_sha,
            "Plan changed during verification")
    index = build_index(directories)
    return root, plan, plan_sha, index


def _template(root, plan, plan_sha, index, result_directory):
    require(type(result_directory) is str and NAME.fullmatch(result_directory),
            "Invalid result directory")
    windows = [w for w in plan["reviewed_windows"]
               if w["result_directory"] == result_directory]
    require(len(windows) == 1, "Select exactly one accepted hand")
    window = windows[0]
    rows = [h for h in index["hands"] if h["result_directory"] == result_directory]
    require(len(rows) == 1 and rows[0]["clip_sha256"] ==
            window["original_clip_sha256_verified_bytes"],
            "Original clip provenance mismatch")
    folder = root / result_directory
    annotation_sha, _ = file_hash(folder / "annotation_input.json", MAX_JSON_BYTES)
    math_sha, _ = file_hash(folder / "math.json", MAX_JSON_BYTES)
    manifest_sha, _ = file_hash(folder / "pipeline.json", MAX_JSON_BYTES)
    return {
        "schema_version": 1, "status": STATUS,
        "timestamp_plan_sha256_verified_bytes": plan_sha,
        "source_recording_sha256_verified_bytes": plan["source_recording_sha256_verified_bytes"],
        "result_directory": result_directory, "table_id": window["table_id"],
        "hand_label": window["hand_label"], "variant": window["variant"],
        "original_clip_sha256_verified_bytes": window["original_clip_sha256_verified_bytes"],
        "pipeline_manifest_sha256_verified_bytes": manifest_sha,
        "original_annotation_sha256_verified_bytes": annotation_sha,
        "original_math_sha256_verified_bytes": math_sha,
        "original_seconds": window["original_seconds"],
        "reviewed_seconds": window["reviewed_seconds"],
        "reviewer_label_claim_unverified": "", "notes": "",
        "reviewed_source_frames": False,
        "reviewed_corrected_window": False,
        "reviewed_math_and_range_assumptions": False,
        "approved_for_export": False,
        "automatic_clip_selection_authorized": False,
        "video_content_verified": False, "ocr_accuracy_verified": False,
    }


def prepare(recording, reference, proposals, second_review, plan_path,
            directories, result_directory, new_approval_path):
    root, plan, plan_sha, index = _evidence(
        recording, reference, proposals, second_review, plan_path, directories)
    output = _new_path(new_approval_path, root)
    template = _template(root, plan, plan_sha, index, result_directory)
    _write_new(output, template)
    return template


def _approval(edited, expected):
    require(type(edited) is dict and set(edited) == set(expected),
            "Approval schema mismatch")
    editable = set(FLAGS) | {"approved_for_export", "reviewer_label_claim_unverified", "notes"}
    require({k: v for k, v in edited.items() if k not in editable} ==
            {k: v for k, v in expected.items() if k not in editable},
            "Immutable export evidence changed")
    require(all(edited[f] is True for f in FLAGS) and
            edited["approved_for_export"] is True and
            edited["automatic_clip_selection_authorized"] is False and
            edited["video_content_verified"] is False and
            edited["ocr_accuracy_verified"] is False,
            "Explicit separate review is required")
    label = edited["reviewer_label_claim_unverified"]
    notes = edited["notes"]
    require(type(label) is str and 1 <= len(label) <= 80 and
            label == label.strip() and all(32 <= ord(c) < 127 for c in label),
            "Invalid reviewer label")
    require(type(notes) is str and len(notes) <= 300 and
            all(ord(c) >= 32 for c in notes), "Invalid review notes")


def reexport(recording, reference, proposals, second_review, plan_path,
             directories, approval_path, output_stem):
    root, plan, plan_sha, index = _evidence(
        recording, reference, proposals, second_review, plan_path, directories)
    approval_path = Path(approval_path)
    require(approval_path.parent.resolve() == root.resolve() and
            approval_path.is_file() and not approval_path.is_symlink(),
            "Approval JSON must be beside pipeline results")
    edited = load_json(approval_path)
    approval_sha, _ = file_hash(approval_path, MAX_JSON_BYTES)
    result_directory = edited.get("result_directory")
    expected = _template(root, plan, plan_sha, index, result_directory)
    _approval(edited, expected)
    stem = Path(output_stem)
    require(stem.parent.resolve() == root.resolve() and
            stem.parent.is_dir() and not stem.parent.is_symlink() and
            NAME.fullmatch(stem.name), "Unsafe output stem")
    targets = [stem.with_suffix(ext) for ext in (".mp4", ".json", ".srt", ".audit.json")]
    require(all(not p.exists() and not p.is_symlink() for p in targets),
            "Re-export destination already exists")
    folder = root / result_directory
    original_annotation = load_json(folder / "annotation_input.json")
    require(type(original_annotation) is dict and
            original_annotation.get("approved_for_export") is True,
            "Original clip annotation not approved")
    new_annotation = dict(original_annotation)
    new_annotation.update(start_seconds=edited["reviewed_seconds"]["start"],
                          decision_seconds=edited["reviewed_seconds"]["decision"],
                          end_seconds=edited["reviewed_seconds"]["end"])
    require(recording_hash(recording) == edited["source_recording_sha256_verified_bytes"],
            "Recording hash changed")
    with tempfile.TemporaryDirectory(prefix=".plo_reexport_", dir=root) as temp:
        temp = Path(temp)
        annotation_path = temp / "approved_annotation.json"
        annotation_path.write_text(json.dumps(new_annotation, allow_nan=False), encoding="utf-8")
        result = export_math_clip(recording, folder / "handoff.json",
                                  folder / "candidate.json", folder / "math.json",
                                  annotation_path, temp / "clip")
        # Re-verify the original source, exact plan and all pipeline artifacts.
        require(recording_hash(recording) == edited["source_recording_sha256_verified_bytes"] and
                file_hash(plan_path, MAX_JSON_BYTES)[0] == plan_sha and
                file_hash(approval_path, MAX_JSON_BYTES)[0] == approval_sha and
                build_index(directories) == index and
                file_hash(folder / "pipeline.json", MAX_JSON_BYTES)[0] ==
                expected["pipeline_manifest_sha256_verified_bytes"],
                "Source or evidence changed during MP4 export")
        audit = {
            "schema_version": 1, "status": EXPORTED,
            "source_recording_sha256_verified_bytes": edited["source_recording_sha256_verified_bytes"],
            "timestamp_plan_sha256_verified_bytes": plan_sha,
            "separate_approval_sha256_verified_bytes": approval_sha,
            "original_clip_sha256_verified_bytes": edited["original_clip_sha256_verified_bytes"],
            "reexported_clip_sha256_verified_bytes": result["clip_sha256"],
            "result_directory": result_directory, "reviewed_seconds": edited["reviewed_seconds"],
            "reviewer_label_claim_unverified": edited["reviewer_label_claim_unverified"],
            "review_flags_are_self_declarations": True,
            "monte_carlo_recomputed": False, "video_content_verified": False,
            "ocr_accuracy_verified": False, "automatic_clip_selection_authorized": False,
            "existing_clips_modified": False,
            "limitations": ["Review flags do not authenticate the reviewer or poker content.",
                            "Monte Carlo and EV were reused, not recomputed.",
                            "Corrected PTS proximity does not establish correct cards or actions."],
        }
        (temp / "clip.audit.json").write_text(
            json.dumps(audit, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8")
        linked = []
        try:
            for ext, dst in zip((".mp4", ".json", ".srt", ".audit.json"), targets):
                os.link(temp / ("clip" + ext), dst)
                linked.append(dst)
        except BaseException:
            for dst in linked:
                dst.unlink(missing_ok=True)
            raise
    return audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "export"):
        p = sub.add_parser(name)
        for arg in ("recording", "reference_template", "proposals_json",
                    "second_review_json", "timestamp_plan_json"):
            p.add_argument(arg)
        p.add_argument("result_or_approval")
        p.add_argument("new_approval_or_output_stem")
        p.add_argument("pipeline_directories", nargs="+")
    args = parser.parse_args(argv)
    a = (args.recording, args.reference_template, args.proposals_json,
         args.second_review_json, args.timestamp_plan_json)
    if args.command == "prepare":
        result = prepare(*a, args.pipeline_directories, args.result_or_approval,
                         args.new_approval_or_output_stem)
    else:
        result = reexport(*a, args.pipeline_directories, args.result_or_approval,
                          args.new_approval_or_output_stem)
    print(json.dumps({"status": result["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
