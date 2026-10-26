"""Link offline PLO5/PLO6 ledger events to supplied frame crops, without asserting visual truth.

Only hashes of *supplied crop files* are checked. The recording SHA-256 is a
claim in the manifest, not independently verified against the source video.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat

MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_CROP_BYTES = 8 * 1024 * 1024
MAX_OBSERVATIONS = 500
MAX_SECONDS = 7200
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, name, *, minimum=0, maximum=MAX_SECONDS):
    check(type(value) in (int, float) and math.isfinite(value) and
          minimum <= value <= maximum, f"Invalid {name}")
    return value


def sha256(value, name):
    check(type(value) is str and HEX64.fullmatch(value) is not None, f"Invalid {name}")
    return value


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        check(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def read_json(path):
    path = Path(path)
    check(path.is_file() and not path.is_symlink() and
          0 < path.stat().st_size <= MAX_JSON_BYTES, "Unsafe JSON input")
    raw = path.read_bytes()
    check(0 < len(raw) <= MAX_JSON_BYTES, "Unsafe JSON input length")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                       parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    check(type(value) is dict, "Expected JSON object")
    return value, raw


def crop_bytes(root, relative):
    check(type(relative) is str and len(relative) <= 256 and "\\" not in relative,
          "Unsafe crop path")
    p = PurePosixPath(relative)
    check(not p.is_absolute() and p.parts and
          all(x not in (".", "..", "") for x in relative.split("/")) and
          p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"),
          "Unsafe crop path")
    root = Path(root)
    check(root.is_dir() and not root.is_symlink(), "Unsafe crop root")
    current = root
    for part in p.parts[:-1]:
        current = current / part
        check(current.is_dir() and not current.is_symlink(), "Unsafe crop directory")
    file_path = current / p.parts[-1]
    check(file_path.is_file() and not file_path.is_symlink() and
          0 < file_path.stat().st_size <= MAX_CROP_BYTES, "Unsafe crop file")
    fd = os.open(file_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        with os.fdopen(fd, "rb") as f:
            check(stat.S_ISREG(os.fstat(f.fileno()).st_mode), "Unsafe crop type")
            raw = f.read(MAX_CROP_BYTES + 1)
    except BaseException:
        raise
    check(0 < len(raw) <= MAX_CROP_BYTES, "Unsafe crop size")
    return raw


def link(ledger, manifest, crops_root):
    check(type(ledger) is dict and ledger.get("schema_version") == 1 and
          ledger.get("status") == "conditional_observation_ledger_not_video_verified" and
          ledger.get("video_evidence_verified") is False and
          ledger.get("ready_for_equity_or_ev") is False and
          type(ledger.get("events")) is list and len(ledger["events"]) <= 500 and
          type(ledger.get("table_id")) is int and 1 <= ledger["table_id"] <= 4 and
          ledger.get("variant") in ("PLO5", "PLO6") and
          type(ledger.get("hand_label")) is str and
          type(ledger.get("input_canonical_sha256")) is str,
          "Not a supported unverified ledger report")
    sha256(ledger["input_canonical_sha256"], "ledger digest")
    check(type(manifest) is dict and set(manifest) == {
        "schema_version", "source_recording_sha256", "source_duration_seconds",
        "ledger_input_canonical_sha256", "table_id", "hand_label", "observations"},
        "Invalid evidence manifest schema")
    check(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1 and
          type(manifest["table_id"]) is int and manifest["table_id"] == ledger["table_id"] and
          type(manifest["hand_label"]) is str and manifest["hand_label"] == ledger["hand_label"] and
          sha256(manifest["ledger_input_canonical_sha256"], "manifest ledger digest") ==
          ledger["input_canonical_sha256"], "Evidence manifest/ledger mismatch")
    sha256(manifest["source_recording_sha256"], "recording digest claim")
    duration = number(manifest["source_duration_seconds"], "recording duration", minimum=0.001)
    observations = manifest["observations"]
    check(type(observations) is list and len(observations) <= MAX_OBSERVATIONS,
          "Invalid observations")
    events = ledger["events"]
    for i, event in enumerate(events):
        check(type(event) is dict and type(event.get("event_index")) is int and
              event["event_index"] == i and event.get("street") in
              ("preflop", "flop", "turn", "river") and
              number(event.get("source_pts_seconds"), "event PTS") <= duration and
              number(event.get("confidence"), "event confidence", maximum=1) <= 1,
              "Invalid ledger event")
    rows = []
    seen = set()
    for item in observations:
        check(type(item) is dict and set(item) == {
            "event_index", "frame_pts_seconds", "crop_path", "crop_sha256",
            "bbox_pixels", "recognition_confidence", "extraction_method"},
            "Invalid observation schema")
        idx = item["event_index"]
        check(type(idx) is int and 0 <= idx < len(events) and idx not in seen,
              "Duplicate or invalid event reference")
        seen.add(idx)
        pts = number(item["frame_pts_seconds"], "frame PTS")
        check(pts <= duration and
              abs(pts - events[idx]["source_pts_seconds"]) <= 1.5,
              "Frame timestamp outside event tolerance")
        bbox = item["bbox_pixels"]
        check(type(bbox) is list and len(bbox) == 4 and
              all(type(v) is int and 0 <= v <= 32768 for v in bbox) and
              bbox[2] > 0 and bbox[3] > 0 and
              bbox[0] + bbox[2] <= 32768 and bbox[1] + bbox[3] <= 32768,
              "Invalid crop bounding box")
        confidence = number(item["recognition_confidence"], "recognition confidence", maximum=1)
        check(item["extraction_method"] in ("synthetic", "manual_crop", "ffmpeg_frame"),
              "Invalid extraction method")
        digest = sha256(item["crop_sha256"], "crop digest")
        raw = crop_bytes(crops_root, item["crop_path"])
        check(hashlib.sha256(raw).hexdigest() == digest, "Crop digest mismatch")
        rows.append({
            "event_index": idx, "street": events[idx]["street"],
            "actor": events[idx].get("actor"), "kind": events[idx].get("kind"),
            "event_pts_seconds": events[idx]["source_pts_seconds"],
            "frame_pts_seconds": pts,
            "pts_difference_seconds": round(pts - events[idx]["source_pts_seconds"], 6),
            "crop_path": item["crop_path"], "crop_sha256": digest,
            "bbox_pixels": bbox, "recognition_confidence": confidence,
            "ledger_event_confidence": events[idx]["confidence"],
            "extraction_method": item["extraction_method"],
            "crop_bytes_hash_verified": True,
            "source_recording_frame_verified": False,
        })
    missing = [i for i in range(len(events)) if i not in seen]
    return {
        "schema_version": 1,
        "status": "crop_hashes_verified_recording_and_visual_truth_unverified",
        "variant": ledger["variant"], "table_id": ledger["table_id"],
        "hand_label": ledger["hand_label"],
        "ledger_input_canonical_sha256": ledger["input_canonical_sha256"],
        "source_recording_sha256_claim_unverified": manifest["source_recording_sha256"],
        "source_duration_seconds_claim_unverified": duration,
        "linked_observations": sorted(rows, key=lambda x: x["event_index"]),
        "unlinked_event_indices": missing,
        "linked_count": len(rows), "ledger_event_count": len(events),
        "video_evidence_verified": False, "ocr_accuracy_verified": False,
        "betting_rules_verified": False, "ready_for_equity_or_ev": False,
        "automatic_clip_selection_authorized": False,
        "limitations": [
            "Crop SHA-256 proves byte consistency only, not origin in the claimed recording.",
            "Recording SHA-256 and duration are manifest claims; recording bytes are not read.",
            "PTS proximity and bounding boxes do not verify the image content or action.",
            "OCR confidence and event confidence are separate uncalibrated values.",
            "Unlinked events and omitted actions remain unknown.",
        ],
    }


def export(ledger_path, manifest_path, crops_root, output_path):
    ledger_file, manifest_file, dest = map(Path, (ledger_path, manifest_path, output_path))
    check(dest.suffix.lower() == ".json" and dest.parent.is_dir() and
          not dest.parent.is_symlink() and not dest.exists() and
          dest.resolve() not in (ledger_file.resolve(), manifest_file.resolve()),
          "Unsafe output path")
    ledger, ledger_raw = read_json(ledger_file)
    manifest, manifest_raw = read_json(manifest_file)
    report = link(ledger, manifest, crops_root)
    payload = (json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    check(len(payload) <= MAX_JSON_BYTES and ledger_file.read_bytes() == ledger_raw and
          manifest_file.read_bytes() == manifest_raw, "Input changed or report oversized")
    fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            check(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Unsafe output type")
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_report_json")
    parser.add_argument("evidence_manifest_json")
    parser.add_argument("crops_directory")
    parser.add_argument("new_report_json")
    args = parser.parse_args(argv)
    report = export(args.ledger_report_json, args.evidence_manifest_json,
                    args.crops_directory, args.new_report_json)
    print(json.dumps({"linked": report["linked_count"],
                      "unlinked": len(report["unlinked_event_indices"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
