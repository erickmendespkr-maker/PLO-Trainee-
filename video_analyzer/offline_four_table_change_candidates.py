"""Offline *visual-change candidates* between human-declared table crops.

Not hand-boundary detection, OCR, poker recognition, or strategic advice.
The evidence is sparse: changes between sampled frames can miss entire hands.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

from offline_four_table_sample_review import verify_bundle

STATUS = "unverified_visual_change_candidates_for_manual_review_only"
FEATURE = "ffmpeg_area_scale_16x16_grayscale_mean_absolute_difference_v1"


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _feature(path):
    try:
        result = subprocess.run([
            "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
            "-i", str(path), "-map", "0:v:0", "-frames:v", "1",
            "-vf", "scale=16:16:flags=area,format=gray", "-f", "rawvideo",
            "-pix_fmt", "gray", "-"], check=True, capture_output=True,
            stdin=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Cannot decode crop feature") from exc
    if len(result.stdout) != 256:
        raise ValueError("Unexpected crop feature size")
    return result.stdout


def compute(bundle_path, threshold=0.12):
    """Verify source PNGs and return sparse visual-change evidence only."""
    if type(threshold) not in (float, int) or not math.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError("Threshold must be finite and in (0, 1]")
    bundle = Path(bundle_path)
    source = verify_bundle(bundle)
    samples = source["samples"]
    manifest_path = bundle / "region_samples.json"
    manifest_sha = _sha(manifest_path)
    regions = source["regions"]
    by_table = []
    for region in regions:
        table_id = region["table_id"]
        evidence = []
        previous_feature = None
        previous_sample = None
        for index, sample in enumerate(samples):
            crop = next(c for c in sample["table_crops"] if c["table_id"] == table_id)
            feature = _feature(bundle / crop["path"])
            if previous_feature is not None:
                score = sum(abs(a - b) for a, b in zip(previous_feature, feature)) / (256 * 255)
                evidence.append({
                    "from_sample_index": index - 1,
                    "to_sample_index": index,
                    "from_pts_seconds": previous_sample["decoded_source_pts_seconds"],
                    "to_pts_seconds": sample["decoded_source_pts_seconds"],
                    "from_crop_sha256": previous_sample["table_crops"][next(
                        i for i, c in enumerate(previous_sample["table_crops"]) if c["table_id"] == table_id)]["sha256"],
                    "to_crop_sha256": crop["sha256"],
                    "mean_absolute_difference": round(score, 8),
                    "candidate_visual_change": score >= threshold,
                    "interpretation": "pixel_change_only_not_a_verified_hand_boundary"
                })
            previous_feature, previous_sample = feature, sample
        by_table.append({"table_id": table_id, "comparisons": evidence})
    if _sha(manifest_path) != manifest_sha or verify_bundle(bundle) != source:
        raise ValueError("Source bundle changed during analysis")
    return {
        "schema_version": 1,
        "analysis_status": STATUS,
        "source_manifest_sha256": manifest_sha,
        "recording_sha256": source["recording_sha256"],
        "feature": FEATURE,
        "threshold": float(threshold),
        "samples_compared": len(samples),
        "tables": by_table,
        "hand_boundaries_verified": False,
        "cards_actions_verified": False,
        "ready_for_equity_or_ev": False,
        "automatic_clip_selection_authorized": False,
        "warning": "Sparse image changes are only review candidates, not verified poker hands or actions."
    }


def write_report(bundle_path, output_path, threshold=0.12):
    """Write create-only JSON, without changing the source bundle."""
    output = Path(output_path)
    if not output.parent.is_dir() or output.parent.is_symlink() or output.exists() or output.is_symlink():
        raise ValueError("Unsafe or existing report destination")
    report = compute(bundle_path, threshold)
    encoded = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    with tempfile.NamedTemporaryFile(prefix=".plo_changes_", suffix=".json",
                                     dir=output.parent, delete=False) as temp:
        temp_path = Path(temp.name)
        try:
            temp.write(encoded)
            temp.flush()
            os.fsync(temp.fileno())
        finally:
            pass
    try:
        os.link(temp_path, output)  # create-only; never replace an existing report
    finally:
        temp_path.unlink(missing_ok=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample_bundle")
    parser.add_argument("new_json_report")
    parser.add_argument("--threshold", type=float, default=0.12)
    args = parser.parse_args(argv)
    report = write_report(args.sample_bundle, args.new_json_report, args.threshold)
    print(json.dumps({"status": report["analysis_status"],
                      "tables": len(report["tables"]),
                      "comparisons": sum(len(t["comparisons"]) for t in report["tables"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
