"""Unverified Tesseract text proposals from SHA-verified, offline table crops.

A human supplies a bounded ROI for each sample/table/field. No text is promoted
into a poker fact, hand boundary, action, equity input, or clip decision.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from io import StringIO
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

from offline_four_table_sample_review import verify_bundle

STATUS = "unverified_four_table_ocr_proposals_only"
FIELDS = frozenset(("hero_cards", "board", "pot", "bet", "stack", "action"))
MAX_TASKS = 32
MAX_JSON_BYTES = 64 * 1024
MAX_TSV_BYTES = 1024 * 1024


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def _load_json(path):
    path = Path(path)
    _require(path.is_file() and not path.is_symlink() and
             0 < path.stat().st_size <= MAX_JSON_BYTES, "Invalid ROI manifest")
    return json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=_unique_pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def _parse_tsv(raw):
    _require(len(raw) <= MAX_TSV_BYTES, "Oversized OCR output")
    rows = csv.DictReader(StringIO(raw.decode("utf-8", "replace")), delimiter="\t")
    _require(rows.fieldnames is not None and
             {"text", "conf"}.issubset(rows.fieldnames), "Invalid Tesseract TSV")
    words, confidences = [], []
    for row in rows:
        word = (row.get("text") or "").strip()
        if not word:
            continue
        try:
            confidence = float(row["conf"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid OCR confidence") from exc
        _require(math.isfinite(confidence), "Nonfinite OCR confidence")
        if confidence < 0:
            continue
        _require(0 <= confidence <= 100, "OCR confidence outside engine scale")
        words.append(word)
        confidences.append(confidence / 100)
    return " ".join(words)[:4096], len(words), (sum(confidences) / len(confidences)
                                               if confidences else None)


def _validate_tasks(manifest, source, source_sha):
    _require(type(manifest) is dict and set(manifest) ==
             {"schema_version", "source_manifest_sha256", "tasks"} and
             type(manifest["schema_version"]) is int and
             manifest["schema_version"] == 1 and
             manifest["source_manifest_sha256"] == source_sha,
             "ROI manifest must bind the exact source manifest SHA-256")
    tasks = manifest["tasks"]
    _require(type(tasks) is list and 1 <= len(tasks) <= MAX_TASKS,
             "Expected 1..32 manual OCR tasks")
    samples = source["samples"]
    seen = set()
    validated = []
    for task in tasks:
        _require(type(task) is dict and set(task) ==
                 {"table_id", "sample_index", "field", "roi"}, "Invalid OCR task fields")
        table_id, sample_index, field = (task["table_id"], task["sample_index"], task["field"])
        _require(type(table_id) is int and 1 <= table_id <= 4 and
                 type(sample_index) is int and 0 <= sample_index < len(samples) and
                 type(field) is str and field in FIELDS, "Invalid OCR task identity")
        key = (table_id, sample_index, field)
        _require(key not in seen, "Duplicate table/sample/field task")
        seen.add(key)
        crops = [c for c in samples[sample_index]["table_crops"]
                 if c["table_id"] == table_id]
        _require(len(crops) == 1, "Missing or ambiguous table crop")
        crop = crops[0]
        roi = task["roi"]
        _require(type(roi) is dict and set(roi) == {"x", "y", "width", "height"} and
                 all(type(v) is int for v in roi.values()), "Invalid ROI coordinates")
        x, y, w, h = (roi[k] for k in ("x", "y", "width", "height"))
        _require(x >= 0 and y >= 0 and 8 <= w <= 2048 and 8 <= h <= 2048 and
                 x + w <= crop["width"] and y + h <= crop["height"],
                 "ROI outside verified table crop")
        validated.append((task, crop))
    return validated


def _ocr(crop_path, roi, temporary_image):
    x, y, w, h = (roi[k] for k in ("x", "y", "width", "height"))
    command = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
               "-i", str(crop_path), "-vf", f"crop={w}:{h}:{x}:{y}",
               "-frames:v", "1", "-update", "1", "-f", "image2", "-vcodec", "png",
               str(temporary_image)]
    try:
        subprocess.run(command, stdin=subprocess.DEVNULL, check=True,
                       capture_output=True, timeout=30)
        _require(temporary_image.is_file() and not temporary_image.is_symlink() and
                 0 < temporary_image.stat().st_size <= 16 * 1024 * 1024,
                 "Invalid OCR ROI image")
        proc = subprocess.run(["tesseract", str(temporary_image), "stdout",
                               "--psm", "6", "tsv"], stdin=subprocess.DEVNULL,
                              check=True, capture_output=True, timeout=30)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("FFmpeg/Tesseract OCR failed") from exc
    return _parse_tsv(proc.stdout)


def scan(bundle_path, roi_manifest_path, output_path, *, recording_path=None):
    """Verify source bundle and write a create-only, non-authoritative OCR report."""
    bundle, manifest_path, output = map(Path, (bundle_path, roi_manifest_path, output_path))
    _require(output.parent.is_dir() and not output.parent.is_symlink() and
             not output.exists() and not output.is_symlink(), "Output must be new")
    _require(not output.resolve().is_relative_to(bundle.resolve()),
             "Output cannot be inside the source bundle")
    source = verify_bundle(bundle, recording_path)
    source_manifest = bundle / "region_samples.json"
    source_sha = _sha(source_manifest)
    manifest = _load_json(manifest_path)
    manifest_sha = _sha(manifest_path)
    validated = _validate_tasks(manifest, source, source_sha)
    candidates = []
    with tempfile.TemporaryDirectory(prefix="plo_ocr_", dir=output.parent) as folder:
        image = Path(folder) / "roi.png"
        for task, crop in validated:
            sample = source["samples"][task["sample_index"]]
            crop_path = bundle / crop["path"]
            _require(not crop_path.is_symlink() and _sha(crop_path) == crop["sha256"],
                     "Crop changed before OCR")
            raw, count, confidence = _ocr(crop_path, task["roi"], image)
            _require(_sha(crop_path) == crop["sha256"], "Crop changed during OCR")
            candidates.append({"table_id": task["table_id"],
                               "sample_index": task["sample_index"],
                               "decoded_source_pts_seconds": sample["decoded_source_pts_seconds"],
                               "field": task["field"], "roi": task["roi"],
                               "source_crop_path": crop["path"],
                               "source_crop_sha256": crop["sha256"],
                               "raw_ocr_text": raw, "word_count": count,
                               "tesseract_mean_word_confidence_uncalibrated": confidence,
                               "parsed_candidate": None, "status": "needs_manual_review"})
            image.unlink(missing_ok=True)
        _require(_sha(source_manifest) == source_sha and
                 _sha(manifest_path) == manifest_sha, "Input manifest changed")
        verify_bundle(bundle, recording_path)
        report = {"schema_version": 1, "analysis_status": STATUS,
                  "source_region_samples_sha256": source_sha,
                  "roi_manifest_sha256": manifest_sha,
                  "recording_sha256": source["recording_sha256"],
                  "ocr_engine": "tesseract_psm6_on_ffmpeg_manual_roi",
                  "engine_confidence_is_calibrated_probability": False,
                  "requires_manual_review": True,
                  "ready_for_equity_or_ev": False,
                  "automatic_hand_or_action_inference": False,
                  "candidates": candidates,
                  "warning": "Raw OCR only; source PTS from decoded frames; no poker facts, actions or ranges confirmed."}
        stage = Path(folder) / "report.json"
        stage.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")
        # Atomic, no-overwrite publication; hard-link fails if output already exists.
        os.link(stage, output)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle")
    parser.add_argument("roi_manifest")
    parser.add_argument("new_output_json")
    parser.add_argument("--recording", help="Optional original recording for SHA check")
    args = parser.parse_args(argv)
    result = scan(args.bundle, args.roi_manifest, args.new_output_json,
                  recording_path=args.recording)
    print(json.dumps({"status": result["analysis_status"],
                      "candidates": len(result["candidates"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
