"""Offline, read-only index of reviewed PLO5/PLO6 pipeline outputs.

Binds declared decision timestamps to existing hand/clip/math artifacts by
checking their exact file bytes. Does NOT decode video, verify OCR/PTS, or
select clips automatically. Requires individually published pipeline folders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

SHA = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
FILES = {"review_input.json", "annotation_input.json", "handoff.json",
         "candidate.json", "math.json", "clip.mp4", "clip.json", "clip.srt"}
SUCCESS = "offline_conditional_math_and_approved_clip_exported"
BLOCKED = {"blocked_review", "blocked_math"}
MAX_JSON = 2 * 1024 * 1024


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def pairs_unique(pairs):
    data = {}
    for key, value in pairs:
        require(key not in data, "Duplicate JSON key")
        data[key] = value
    return data


def no_nonfinite(value):
    raise ValueError("Nonfinite JSON value: " + value)


def regular_bytes(path, limit):
    path = Path(path)
    require(not path.is_symlink() and not path.parent.is_symlink(), "Symlink input")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit,
                "Invalid file type or size")
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        require(len(raw) == before.st_size and
                (before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_ino, after.st_size, after.st_mtime_ns), "File changed during read")
    return raw


def load_json(path):
    raw = regular_bytes(path, MAX_JSON)
    def safe_float(value):
        number = float(value)
        require(math.isfinite(number), "Nonfinite JSON value")
        return number
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs_unique,
                      parse_constant=no_nonfinite, parse_float=safe_float)


def file_hash(path, limit):
    # Streaming for MP4, no unbounded in-memory reads.
    path = Path(path)
    require(not path.is_symlink() and not path.parent.is_symlink(), "Symlink input")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit,
                "Invalid file type or size")
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(stream.fileno())
        require((before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_ino, after.st_size, after.st_mtime_ns), "File changed during hash")
    return digest.hexdigest(), before.st_size


def finite(value):
    require(type(value) in (float, int) and math.isfinite(value), "Invalid timestamp")
    return float(value)


def load_result(folder):
    folder = Path(folder)
    require(folder.is_dir() and not folder.is_symlink() and
            not folder.parent.is_symlink() and NAME.fullmatch(folder.name),
            "Invalid pipeline directory")
    manifest = load_json(folder / "pipeline.json")
    require(type(manifest) is dict and manifest.get("schema_version") == 1 and
            manifest.get("status") in BLOCKED | {SUCCESS} and
            type(manifest.get("files")) is dict, "Unsupported pipeline manifest")
    listed = manifest["files"]
    require(set(listed) <= FILES and
            {p.name for p in folder.iterdir()} == set(listed) | {"pipeline.json"},
            "Unexpected or missing pipeline files")
    for name, info in listed.items():
        require(type(info) is dict and set(info) == {"sha256", "bytes"} and
                type(info["sha256"]) is str and SHA.fullmatch(info["sha256"]) and
                type(info["bytes"]) is int and info["bytes"] > 0,
                "Invalid file manifest entry")
        cap = 1024**3 if name == "clip.mp4" else (65536 if name == "clip.srt" else MAX_JSON)
        digest, length = file_hash(folder / name, cap)
        require(digest == info["sha256"] and length == info["bytes"],
                "Pipeline artifact digest mismatch")
    require({"review_input.json", "annotation_input.json", "handoff.json"} <= set(listed),
            "Missing provenance artifacts")
    require(manifest.get("review_input_sha256") == listed["review_input.json"]["sha256"] and
            manifest.get("annotation_input_sha256") == listed["annotation_input.json"]["sha256"],
            "Snapshot hash mismatch")
    for key in ("video_evidence_verified", "ocr_accuracy_verified",
                "opponent_range_verified", "strategic_error_proven",
                "automatic_clip_selection_authorized"):
        require(manifest.get(key) is False, "Unsupported verification claim")
    table, label, variant = manifest.get("table_id"), manifest.get("hand_label"), manifest.get("variant")
    require(type(table) is int and 1 <= table <= 4 and
            type(label) is str and 0 < len(label) <= 64 and
            not any(ord(ch) < 32 for ch in label) and variant in ("PLO5", "PLO6"),
            "Invalid hand identity")
    handoff = load_json(folder / "handoff.json")
    require(all(handoff.get(k) == v for k, v in
                (("table_id", table), ("hand_label", label), ("variant", variant))),
            "Handoff identity mismatch")
    source_claim = handoff.get("source_recording_sha256_claim_unverified")
    require(type(source_claim) is str and SHA.fullmatch(source_claim),
            "Invalid recording SHA claim")
    status = manifest["status"]
    row = {"result_directory": folder.name, "table_id": table,
           "hand_label": label, "variant": variant, "pipeline_status": status,
           "decision_seconds_human": None, "clip_start_seconds_human": None,
           "clip_end_seconds_human": None, "clip_sha256": None,
           "equity_monte_carlo": None, "ev_call_chips_conditional": None,
           "blocked_reasons": manifest.get("blocked_reasons"),
           "video_content_verified": False, "automatic_selection_authorized": False}
    require(type(row["blocked_reasons"]) is list, "Invalid blocked reasons")
    if status in BLOCKED:
        require(manifest.get("clip_exported") is False and
                "clip.mp4" not in listed and "clip.json" not in listed and
                "clip.srt" not in listed and row["blocked_reasons"],
                "Blocked hand incorrectly has a clip")
        return row, source_claim, None
    require(manifest.get("clip_exported") is True and
            manifest.get("monte_carlo_recomputed") is True and
            not row["blocked_reasons"] and
            {"candidate.json", "math.json", "clip.mp4", "clip.json", "clip.srt"} <= set(listed),
            "Successful pipeline missing math/clip evidence")
    clip, math_report, annotation = (load_json(folder / n) for n in
                                      ("clip.json", "math.json", "annotation_input.json"))
    require(all(clip.get(k) == v for k, v in
                (("table_id", table), ("hand_label", label), ("variant", variant))) and
            all(math_report.get(k) == v for k, v in
                (("table_id", table), ("hand_label", label), ("variant", variant))),
            "Math/clip identity mismatch")
    require(clip.get("clip_sha256") == listed["clip.mp4"]["sha256"] ==
            manifest.get("clip_sha256") and
            clip.get("bridge_input_sha256_verified_bytes") == listed["candidate.json"]["sha256"] ==
            math_report.get("input_sha256") and
            clip.get("clip_explanation_is_conditional") is True and
            math_report.get("monte_carlo_recomputed") is True,
            "Clip/math provenance mismatch")
    source = clip.get("source_recording_sha256_verified_bytes")
    require(type(source) is str and SHA.fullmatch(source) and
            source == manifest.get("source_recording_sha256_verified_bytes") ==
            handoff.get("source_recording_sha256_claim_unverified"),
            "Recording identity mismatch")
    start, moment, end = (finite(clip.get(k)) for k in
                          ("start_seconds", "decision_seconds", "end_seconds"))
    require(0 <= start <= moment <= end and 1 <= end - start <= 180 and
            all(annotation.get(k) == clip.get(k) for k in
                ("start_seconds", "decision_seconds", "end_seconds", "table_id", "hand_label")) and
            annotation.get("approved_for_export") is True,
            "Invalid human-approved timestamp association")
    equity = finite(clip.get("equity"))
    ev = finite(clip.get("ev_call_chips"))
    require(0 <= equity <= 1 and math_report.get("equity") == equity and
            math_report.get("ev_call_chips") == ev, "Math summary mismatch")
    row.update({"decision_seconds_human": moment, "clip_start_seconds_human": start,
                "clip_end_seconds_human": end, "clip_sha256": clip["clip_sha256"],
                "equity_monte_carlo": equity, "ev_call_chips_conditional": ev})
    return row, source_claim, source


def build_index(directories):
    require(type(directories) in (list, tuple) and 1 <= len(directories) <= 40,
            "Expected 1–40 pipeline results")
    roots = [Path(p) for p in directories]
    require(len({p.resolve() for p in roots}) == len(roots), "Repeated pipeline directory")
    records, claims, sources, identities = [], set(), set(), set()
    for folder in roots:
        row, claim, source = load_result(folder)
        claims.add(claim)
        key = row["table_id"], row["hand_label"]
        require(key not in identities, "Duplicate table/hand identity")
        identities.add(key)
        if source is not None:
            sources.add(source)
        records.append(row)
    require(len(claims) == 1 and len(sources) <= 1 and
            (not sources or sources == claims), "Multiple recording identities in one session")
    records.sort(key=lambda r: (r["decision_seconds_human"] is None,
                                r["decision_seconds_human"] if r["decision_seconds_human"] is not None else 0,
                                r["table_id"], r["hand_label"]))
    overlaps = []
    for i, a in enumerate(records):
        if a["clip_start_seconds_human"] is None:
            continue
        for b in records[i+1:]:
            if b["clip_start_seconds_human"] is None or a["table_id"] != b["table_id"]:
                continue
            if max(a["clip_start_seconds_human"], b["clip_start_seconds_human"]) < min(
                    a["clip_end_seconds_human"], b["clip_end_seconds_human"]):
                overlaps.append([a["result_directory"], b["result_directory"]])
    return {"schema_version": 1,
            "status": "offline_declared_decision_timeline_not_video_verified",
            "source_recording_sha256_claim_unverified": next(iter(claims)),
            "source_recording_sha256_verified_for_exported_clips": next(iter(sources), None),
            "hand_count": len(records),
            "exported_clip_count": sum(r["clip_sha256"] is not None for r in records),
            "blocked_count": sum(r["clip_sha256"] is None for r in records),
            "same_table_clip_window_overlaps_review_only": overlaps,
            "hands": records, "video_content_verified": False,
            "ocr_accuracy_verified": False, "timestamp_pts_verified": False,
            "automatic_clip_selection_authorized": False,
            "limitations": ["Human-declared timestamps are not source PTS verified against frames.",
                            "SHA-256 confirms file identity, not poker recognition accuracy.",
                            "Monte Carlo sampling uncertainty excludes opponent-range uncertainty.",
                            "Overlap warnings are review hints, not evidence of incorrect hands."]}


def export(directories, output):
    output = Path(output)
    require(output.suffix == ".json" and NAME.fullmatch(output.stem) and
            output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink(), "Output must be new JSON")
    # Require output beside pipeline directories, preventing unexpected paths.
    require(all(Path(p).parent.resolve() == output.parent.resolve() for p in directories),
            "Output must be beside pipeline directories")
    index = build_index(directories)
    payload = (json.dumps(index, sort_keys=True, ensure_ascii=False,
                          allow_nan=False, indent=2) + "\n").encode("utf-8")
    require(len(payload) <= MAX_JSON, "Timeline output too large")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_index_json")
    parser.add_argument("pipeline_directories", nargs="+")
    args = parser.parse_args(argv)
    result = export(args.pipeline_directories, args.new_index_json)
    print(json.dumps({"status": result["status"], "hand_count": result["hand_count"],
                      "exported_clip_count": result["exported_clip_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
