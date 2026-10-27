"""Validate human-proposed source-PTS corrections without authorizing clip exports.

Reads a Cycle-141 contact-sheet template, rechecks source recording, pipeline
manifests and reference JPEG bytes, and snaps human-proposed times to decoded
source frame PTS. Produces a *new*, explicitly unapproved JSON audit artifact.
Does not alter annotations, clips, poker histories, or source recordings.
Only local, previously recorded MP4/WebM inputs; no online/live integration.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import stat

from offline_reviewed_decision_timeline import (
    NAME, SHA, build_index, file_hash, load_json, require, regular_bytes,
)
from offline_reviewed_source_pts_audit import (
    _scan_pts, build_report, recording_hash,
)
from offline_reviewed_pts_contact_sheet import _samples, _indices

MAX_TEMPLATE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 512 * 1024
MAX_CORRECTION_SECONDS = 5.0
MAX_SNAP_SECONDS = 0.15
FRAME_NAME = re.compile(r"frame_\d{4}\.jpg\Z")
EDITABLE = {"corrected_seconds", "approved_by_human"}
POINT_FIELDS = {"table_id", "hand_label", "variant", "result_directory",
                "kind", "within_tolerance", "original_human_seconds",
                "nearest_decoded_pts_seconds", "nearest_frame_index",
                "absolute_delta_seconds", "corrected_seconds",
                "approved_by_human", "reference_images"}


def _finite(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            "Invalid corrected timestamp")
    return float(value)


def _check_template(template, report, reference_dir):
    require(type(template) is dict and template.get("schema_version") == 1 and
            template.get("status") == "requires_human_review_not_approved_for_pipeline" and
            template.get("approved_for_export") is False and
            template.get("video_content_verified") is False and
            template.get("ocr_accuracy_verified") is False and
            template.get("automatic_hand_boundary_correction") is False,
            "Invalid or already approved review template")
    for key, expected in (
        ("source_recording_sha256_verified_bytes", report["source_recording_sha256_verified_bytes"]),
        ("pts_audit_status", report["status"]),
        ("timestamps_checked", report["timestamps_checked"]),
        ("timestamps_outside_tolerance", report["timestamps_outside_tolerance"]),
        ("frame_count", report["frame_scan"]["decoded_frames_scanned"]),
    ):
        require(type(template.get(key)) is type(expected) and template[key] == expected,
                "Review template no longer matches source audit: " + key)
    images = template.get("reference_images")
    points = template.get("review_points")
    require(type(images) is dict and type(points) is list and len(points) <= 120,
            "Invalid review images or points")
    expected = None
    for include in (False, True):
        candidate = _samples(report, include)
        if len(candidate) != len(points):
            continue
        if all(type(point) is dict and set(point) == POINT_FIELDS and
               {k: v for k, v in point.items() if k not in EDITABLE | {"reference_images"}} ==
               {k: v for k, v in row.items() if k not in EDITABLE}
               for point, row in zip(points, candidate)):
            expected = candidate
            break
    require(expected is not None, "Review points differ from fresh source audit")
    selected = _indices(expected, report["frame_scan"]["decoded_frames_scanned"])
    require(set(images) == {str(i) for i in selected}, "Reference frame set mismatch")
    require({p.name for p in reference_dir.iterdir()} ==
            {"contact_sheet.html", "review_template.json"} |
            {v.get("file") for v in images.values() if type(v) is dict},
            "Unexpected reference files")
    for ordinal, index in enumerate(selected):
        info = images[str(index)]
        require(type(info) is dict and set(info) == {"file", "sha256", "bytes"} and
                info["file"] == f"frame_{ordinal:04d}.jpg" and
                FRAME_NAME.fullmatch(info["file"]) and
                type(info["sha256"]) is str and SHA.fullmatch(info["sha256"]) and
                type(info["bytes"]) is int and 4 <= info["bytes"] <= MAX_IMAGE_BYTES,
                "Invalid reference image metadata")
        path = reference_dir / info["file"]
        digest, length = file_hash(path, MAX_IMAGE_BYTES)
        require((digest, length) == (info["sha256"], info["bytes"]),
                "Reference JPEG was modified")
        raw = regular_bytes(path, MAX_IMAGE_BYTES)
        require(raw.startswith(b"\xff\xd8") and raw.endswith(b"\xff\xd9"),
                "Invalid reference JPEG")
    for point in points:
        center = point["nearest_frame_index"]
        names = [images[str(i)]["file"] for i in
                 (center - 1, center, center + 1) if str(i) in images]
        require(type(point["reference_images"]) is list and
                point["reference_images"] == names,
                "Review point reference images were modified")
    return points


def build_corrections(recording, reference_template, directories, *,
                      ffprobe="ffprobe", timeout_seconds=600,
                      tolerance_seconds=0.15, max_shift_seconds=MAX_CORRECTION_SECONDS):
    require(type(directories) in (list, tuple) and 1 <= len(directories) <= 40,
            "Expected 1–40 pipeline folders")
    require(type(max_shift_seconds) in (float, int) and
            math.isfinite(max_shift_seconds) and 0 < max_shift_seconds <= 30,
            "Invalid maximum correction shift")
    reference_template = Path(reference_template)
    reference_dir = reference_template.parent
    require(reference_template.name == "review_template.json" and
            reference_dir.is_dir() and not reference_dir.is_symlink() and
            not reference_dir.parent.is_symlink() and
            all(Path(d).parent.resolve() == reference_dir.parent.resolve()
                for d in directories), "Review folder must be beside pipeline results")
    # load_json rejects duplicate keys, NaN/Infinity, symlinks and oversized JSON.
    template = load_json(reference_template)
    require(len(regular_bytes(reference_template, MAX_TEMPLATE_BYTES)) <= MAX_TEMPLATE_BYTES,
            "Review template exceeds size limit")
    template_sha, _ = file_hash(reference_template, MAX_TEMPLATE_BYTES)
    report = build_report(recording, directories, ffprobe=ffprobe,
                          timeout_seconds=timeout_seconds,
                          tolerance_seconds=tolerance_seconds)
    points = _check_template(template, report, reference_dir)
    original_index = build_index(directories)
    hand_rows = {h["result_directory"]: h for h in original_index["hands"]}
    proposed = []
    for point in points:
        approved = point["approved_by_human"]
        corrected = point["corrected_seconds"]
        require(type(approved) is bool, "Invalid human review flag")
        require((corrected is None and approved is False) or
                (corrected is not None and approved is True),
                "Correction requires an explicit human review flag")
        if corrected is None:
            continue
        corrected = _finite(corrected)
        require(abs(corrected - point["original_human_seconds"]) <= max_shift_seconds,
                "Correction exceeds maximum allowed shift")
        hand = hand_rows[point["result_directory"]]
        require(hand["clip_sha256"] is not None, "Blocked hand cannot be corrected here")
        proposed.append({"result_directory": point["result_directory"],
                         "table_id": point["table_id"], "hand_label": point["hand_label"],
                         "variant": point["variant"], "kind": point["kind"],
                         "original_seconds": point["original_human_seconds"],
                         "proposed_seconds": corrected,
                         "human_review_flag_from_template": True})
    # Scan the source again to find the *actual* nearest decoded frame for
    # each corrected timestamp; never trust a user-supplied frame index.
    lookups = [{"human_seconds": p["proposed_seconds"]} for p in proposed]
    if lookups:
        _scan_pts(recording, lookups, ffprobe, timeout_seconds, 500_000)
    for item, found in zip(proposed, lookups):
        require(found["absolute_delta_seconds"] <= MAX_SNAP_SECONDS + 1e-9,
                "Corrected time is not close enough to a decoded source frame")
        item["nearest_decoded_pts_seconds"] = found["nearest_decoded_pts_seconds"]
        item["nearest_frame_index"] = found["nearest_frame_index"]
        item["pts_delta_seconds"] = found["absolute_delta_seconds"]
    # A corrected decision cannot fall outside the *previously approved*
    # clip interval. For corrected start/end, check ordering as a group.
    grouped = {}
    for item in proposed:
        grouped.setdefault(item["result_directory"], {})[item["kind"]] = item["proposed_seconds"]
    for folder, changes in grouped.items():
        hand = hand_rows[folder]
        start = changes.get("start", hand["clip_start_seconds_human"])
        decision = changes.get("decision", hand["decision_seconds_human"])
        end = changes.get("end", hand["clip_end_seconds_human"])
        require(0 <= start <= decision <= end and 1 <= end - start <= 180,
                "Corrected timestamps violate hand interval ordering")
    require(recording_hash(recording) == report["source_recording_sha256_verified_bytes"] and
            build_index(directories) == original_index and
            file_hash(reference_template, MAX_TEMPLATE_BYTES)[0] == template_sha,
            "Source, pipeline or review template changed during import")
    _check_template(template, report, reference_dir)  # recheck image hashes
    return {
        "schema_version": 1,
        "status": "human_proposed_pts_corrections_not_approved_for_pipeline",
        "source_recording_sha256_verified_bytes": report["source_recording_sha256_verified_bytes"],
        "review_template_sha256_verified_bytes": template_sha,
        "reference_image_sha256_verified": True,
        "pipeline_artifacts_sha256_verified": True,
        "original_timestamps_checked": report["timestamps_checked"],
        "proposed_correction_count": len(proposed),
        "corrections": proposed,
        "approved_for_export": False,
        "video_content_verified": False,
        "ocr_accuracy_verified": False,
        "hand_boundaries_verified": False,
        "automatic_clip_selection_authorized": False,
        "limitations": [
            "Human review flag is a claim in the edited template, not verified reviewer identity.",
            "Decoded-frame proximity does not prove visible cards, actions or hand boundaries.",
            "No existing clip, annotation or math result was modified or reapproved.",
            "Manual reapproval of clip windows and mathematical provenance is required.",
        ],
    }


def export(recording, reference_template, directories, new_output, **kwargs):
    output = Path(new_output)
    parent = Path(reference_template).parent.parent
    require(output.suffix == ".json" and NAME.fullmatch(output.stem) and
            output.parent.resolve() == parent.resolve() and
            output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink(),
            "Output must be a new JSON beside the pipeline folders")
    report = build_corrections(recording, reference_template, directories, **kwargs)
    raw = (json.dumps(report, indent=2, ensure_ascii=False,
                      sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    require(0 < len(raw) <= 2 * 1024 * 1024, "Correction report exceeds size limit")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Unsafe output")
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording")
    parser.add_argument("review_template")
    parser.add_argument("new_output_json")
    parser.add_argument("pipeline_directories", nargs="+")
    parser.add_argument("--tolerance-seconds", type=float, default=0.15)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    result = export(args.recording, args.review_template, args.pipeline_directories,
                    args.new_output_json, tolerance_seconds=args.tolerance_seconds,
                    timeout_seconds=args.timeout_seconds)
    print(json.dumps({"status": result["status"],
                      "proposed_correction_count": result["proposed_correction_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
