"""Second-stage, offline review of proposed PTS corrections (no MP4 export).

Produces a human-editable second-review template, then an immutable,
create-only *planning* artifact for accepted timestamp changes. It revalidates
recording bytes, frame PTS, contact-sheet JPEGs and prior pipeline manifests.
Reviewer labels and review flags are self-declarations, not authentication.
Neither stage modifies historical clips, math, or annotations, and no output
of this module is authorization for automatic clip generation.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import stat

from offline_reviewed_decision_timeline import (
    NAME, SHA, build_index, file_hash, load_json, regular_bytes, require,
)
from offline_reviewed_pts_correction_import import build_corrections
from offline_reviewed_source_pts_audit import recording_hash

MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_NOTES = 500
MAX_REVIEWER = 80
REVIEW_STATUS = "requires_explicit_second_stage_human_review"
PLAN_STATUS = "human_review_claim_timestamp_plan_not_authorized_for_export"


def _root(recording, reference_template, proposals_path, directories):
    require(type(directories) in (list, tuple) and 1 <= len(directories) <= 40,
            "Expected 1-40 pipeline directories")
    root = Path(directories[0]).parent
    require(root.is_dir() and not root.is_symlink() and
            all(Path(d).parent.resolve() == root.resolve() and
                Path(d).is_dir() and not Path(d).is_symlink()
                for d in directories), "Invalid or mixed pipeline folders")
    for p in (reference_template, proposals_path):
        path = Path(p)
        require(path.parent.resolve() == root.resolve() or
                (path.name == "review_template.json" and
                 path.parent.parent.resolve() == root.resolve() and
                 not path.parent.is_symlink()),
                "Evidence files must be within the pipeline workspace")
    require(Path(reference_template).name == "review_template.json" and
            Path(proposals_path).suffix == ".json", "Invalid evidence file names")
    return root


def _new_path(path, root):
    p = Path(path)
    require(p.suffix == ".json" and NAME.fullmatch(p.stem) and
            p.parent.resolve() == root.resolve() and
            p.parent.is_dir() and not p.parent.is_symlink() and
            not p.exists() and not p.is_symlink(),
            "Output must be a new JSON file beside pipeline results")
    return p


def _write_new(path, data):
    raw = (json.dumps(data, indent=2, sort_keys=True,
                      ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    require(0 < len(raw) <= MAX_JSON_BYTES, "Report exceeds size limit")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            require(stat.S_ISREG(os.fstat(f.fileno()).st_mode), "Unsafe output")
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        Path(path).unlink(missing_ok=True)
        raise


def _verified_proposals(recording, reference_template, proposals_path, directories,
                        *, ffprobe="ffprobe", timeout_seconds=600):
    _root(recording, reference_template, proposals_path, directories)
    proposals_path = Path(proposals_path)
    original = load_json(proposals_path)
    require(len(regular_bytes(proposals_path, MAX_JSON_BYTES)) <= MAX_JSON_BYTES,
            "Proposal report exceeds size limit")
    digest, _ = file_hash(proposals_path, MAX_JSON_BYTES)
    fresh = build_corrections(recording, reference_template, directories,
                              ffprobe=ffprobe, timeout_seconds=timeout_seconds)
    require(original == fresh and
            original.get("status") == "human_proposed_pts_corrections_not_approved_for_pipeline" and
            original.get("approved_for_export") is False and
            type(original.get("corrections")) is list and
            1 <= len(original["corrections"]) <= 120,
            "Stale or unverified PTS proposals")
    require(file_hash(proposals_path, MAX_JSON_BYTES)[0] == digest,
            "Proposal file changed during verification")
    return original, digest


def _manifest_hashes(directories):
    return {Path(d).name: file_hash(Path(d) / "pipeline.json", MAX_JSON_BYTES)[0]
            for d in directories}


def _review_template(proposals, digest, directories):
    return {
        "schema_version": 1,
        "status": REVIEW_STATUS,
        "source_recording_sha256_verified_bytes": proposals["source_recording_sha256_verified_bytes"],
        "proposal_report_sha256_verified_bytes": digest,
        "pipeline_manifest_sha256_verified_bytes": _manifest_hashes(directories),
        "reviewer_label": "",
        "reviewed_source_frames": False,
        "reviewed_clip_windows": False,
        "reviewed_math_provenance": False,
        "decisions": [
            {"result_directory": c["result_directory"],
             "table_id": c["table_id"], "hand_label": c["hand_label"],
             "variant": c["variant"], "kind": c["kind"],
             "original_seconds": c["original_seconds"],
             "proposed_seconds": c["proposed_seconds"],
             "nearest_decoded_pts_seconds": c["nearest_decoded_pts_seconds"],
             "nearest_frame_index": c["nearest_frame_index"],
             "accept_correction": False, "review_notes": ""}
            for c in proposals["corrections"]
        ],
        "approved_for_export": False,
        "automatic_clip_selection_authorized": False,
        "video_content_verified": False,
        "ocr_accuracy_verified": False,
        "limitations": [
            "Human review flags and reviewer label are not authenticated.",
            "Source-frame proximity does not prove cards, actions or hand boundaries.",
            "Acceptance only produces a timestamp plan, never MP4 export permission.",
            "Monte Carlo and EV are not recomputed by this module.",
        ],
    }


def prepare(recording, reference_template, proposals_path, directories, new_template,
            *, ffprobe="ffprobe", timeout_seconds=600):
    root = _root(recording, reference_template, proposals_path, directories)
    output = _new_path(new_template, root)
    proposals, digest = _verified_proposals(recording, reference_template,
                                           proposals_path, directories,
                                           ffprobe=ffprobe, timeout_seconds=timeout_seconds)
    template = _review_template(proposals, digest, directories)
    _write_new(output, template)
    return template


def _safe_label(value):
    require(type(value) is str and 1 <= len(value.strip()) <= MAX_REVIEWER and
            value == value.strip() and
            not any(ord(c) < 32 or ord(c) == 127 for c in value),
            "Missing or invalid reviewer label")
    return value


def _validate_review(edited, expected):
    require(type(edited) is dict and set(edited) == set(expected),
            "Second-review template has unexpected fields")
    require({k: v for k, v in edited.items()
             if k not in {"reviewer_label", "reviewed_source_frames",
                          "reviewed_clip_windows", "reviewed_math_provenance", "decisions"}} ==
            {k: v for k, v in expected.items()
             if k not in {"reviewer_label", "reviewed_source_frames",
                          "reviewed_clip_windows", "reviewed_math_provenance", "decisions"}},
            "Second-review immutable evidence changed")
    flags = ("reviewed_source_frames", "reviewed_clip_windows", "reviewed_math_provenance")
    require(all(type(edited[k]) is bool for k in flags), "Invalid review flags")
    require(type(edited["decisions"]) is list and
            len(edited["decisions"]) == len(expected["decisions"]),
            "Review decision count mismatch")
    accepted = []
    for actual, original in zip(edited["decisions"], expected["decisions"]):
        require(type(actual) is dict and set(actual) == set(original) and
                {k: v for k, v in actual.items()
                 if k not in {"accept_correction", "review_notes"}} ==
                {k: v for k, v in original.items()
                 if k not in {"accept_correction", "review_notes"}},
                "Review decision evidence modified")
        require(type(actual["accept_correction"]) is bool and
                type(actual["review_notes"]) is str and
                len(actual["review_notes"]) <= MAX_NOTES and
                not any(ord(c) < 32 and c not in "\n\t" for c in actual["review_notes"]),
                "Invalid review decision or notes")
        if actual["accept_correction"]:
            accepted.append(actual)
    if accepted:
        _safe_label(edited["reviewer_label"])
        require(all(edited[k] is True for k in flags),
                "Accepted correction requires three explicit review checks")
    else:
        require(type(edited["reviewer_label"]) is str and
                len(edited["reviewer_label"]) <= MAX_REVIEWER,
                "Invalid reviewer label")
    return accepted


def build_plan(recording, reference_template, proposals_path, second_review,
               directories, *, ffprobe="ffprobe", timeout_seconds=600):
    root = _root(recording, reference_template, proposals_path, directories)
    review_path = Path(second_review)
    require(review_path.parent.resolve() == root.resolve() and
            review_path.is_file() and not review_path.is_symlink(),
            "Second-review JSON must be beside pipeline results")
    edited = load_json(review_path)
    require(len(regular_bytes(review_path, MAX_JSON_BYTES)) <= MAX_JSON_BYTES,
            "Second-review JSON exceeds size limit")
    review_sha, _ = file_hash(review_path, MAX_JSON_BYTES)
    proposals, proposal_sha = _verified_proposals(recording, reference_template,
                                                proposals_path, directories,
                                                ffprobe=ffprobe,
                                                timeout_seconds=timeout_seconds)
    expected = _review_template(proposals, proposal_sha, directories)
    accepted = _validate_review(edited, expected)
    index = build_index(directories)
    hands = {h["result_directory"]: h for h in index["hands"]}
    groups = {}
    for item in edited["decisions"]:
        groups.setdefault(item["result_directory"], []).append(item)
    plans = []
    for folder, items in sorted(groups.items()):
        if not any(i["accept_correction"] for i in items):
            continue
        require(all(i["accept_correction"] for i in items),
                "All proposed corrections for one hand must be reviewed together")
        hand = hands[folder]
        require(hand["clip_sha256"] is not None,
                "Cannot approve timestamp corrections for a blocked hand")
        original = {"start": hand["clip_start_seconds_human"],
                    "decision": hand["decision_seconds_human"],
                    "end": hand["clip_end_seconds_human"]}
        changed = {i["kind"]: i["proposed_seconds"] for i in items}
        require(len(changed) == len(items) and set(changed) <= set(original),
                "Duplicate or invalid timestamp correction kind")
        new = {k: changed.get(k, v) for k, v in original.items()}
        require(all(type(v) in (int, float) and math.isfinite(v) for v in new.values()) and
                original["start"] <= new["start"] <= new["decision"] <=
                new["end"] <= original["end"] and
                1 <= new["end"] - new["start"] <= 180,
                "Second-stage timestamp window exceeds original approved clip")
        plans.append({"result_directory": folder, "table_id": hand["table_id"],
                      "hand_label": hand["hand_label"], "variant": hand["variant"],
                      "original_clip_sha256_verified_bytes": hand["clip_sha256"],
                      "original_seconds": original, "reviewed_seconds": new,
                      "accepted_corrections": [{"kind": i["kind"],
                                                "requested_seconds": i["proposed_seconds"],
                                                "nearest_decoded_pts_seconds": i["nearest_decoded_pts_seconds"],
                                                "nearest_frame_index": i["nearest_frame_index"],
                                                "review_notes": i["review_notes"]}
                                               for i in items]})
    require(recording_hash(recording) == proposals["source_recording_sha256_verified_bytes"] and
            build_index(directories) == index and
            file_hash(proposals_path, MAX_JSON_BYTES)[0] == proposal_sha and
            file_hash(review_path, MAX_JSON_BYTES)[0] == review_sha and
            _manifest_hashes(directories) == expected["pipeline_manifest_sha256_verified_bytes"],
            "Evidence changed during second-stage review")
    return {
        "schema_version": 1, "status": PLAN_STATUS,
        "source_recording_sha256_verified_bytes": proposals["source_recording_sha256_verified_bytes"],
        "proposal_report_sha256_verified_bytes": proposal_sha,
        "second_review_sha256_verified_bytes": review_sha,
        "reviewer_label_claim_unverified": edited["reviewer_label"],
        "reviewed_source_frames_claim": edited["reviewed_source_frames"],
        "reviewed_clip_windows_claim": edited["reviewed_clip_windows"],
        "reviewed_math_provenance_claim": edited["reviewed_math_provenance"],
        "reviewed_hand_count": len(plans),
        "rejected_or_deferred_correction_count": len(edited["decisions"]) - len(accepted),
        "reviewed_windows": plans,
        "approved_for_export": False,
        "automatic_clip_selection_authorized": False,
        "video_content_verified": False,
        "ocr_accuracy_verified": False,
        "math_recomputed": False,
        "existing_clips_modified": False,
        "limitations": [
            "Review claims and reviewer label are not authenticated.",
            "Timestamp plan cannot be fed directly to clip export as approval.",
            "No visual recognition, range validation or new Monte Carlo was performed.",
            "A separate explicit annotation and export review is still required.",
        ],
    }


def finalize(recording, reference_template, proposals_path, second_review,
             directories, new_plan, *, ffprobe="ffprobe", timeout_seconds=600):
    root = _root(recording, reference_template, proposals_path, directories)
    output = _new_path(new_plan, root)
    result = build_plan(recording, reference_template, proposals_path,
                        second_review, directories, ffprobe=ffprobe,
                        timeout_seconds=timeout_seconds)
    _write_new(output, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="create second-review template")
    prep.add_argument("recording")
    prep.add_argument("reference_template")
    prep.add_argument("proposals_json")
    prep.add_argument("new_second_review_json")
    prep.add_argument("pipeline_directories", nargs="+")
    fin = sub.add_parser("finalize", help="create non-exportable timestamp plan")
    fin.add_argument("recording")
    fin.add_argument("reference_template")
    fin.add_argument("proposals_json")
    fin.add_argument("second_review_json")
    fin.add_argument("new_plan_json")
    fin.add_argument("pipeline_directories", nargs="+")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        result = prepare(args.recording, args.reference_template,
                         args.proposals_json, args.pipeline_directories,
                         args.new_second_review_json)
        summary = {"status": result["status"], "review_items": len(result["decisions"])}
    else:
        result = finalize(args.recording, args.reference_template,
                          args.proposals_json, args.second_review_json,
                          args.pipeline_directories, args.new_plan_json)
        summary = {"status": result["status"],
                   "reviewed_hand_count": result["reviewed_hand_count"]}
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
