"""Offline FFmpeg frame-to-crop provenance for recorded PLO5/PLO6 sessions.

Creates a Cycle-126-compatible evidence manifest, but does NOT certify OCR,
card/action recognition, betting rules, or suitability for equity/EV.
Only run against user-authorized, local recordings; no network or live capture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

MAX_VIDEO_BYTES = 12 * 1024**3
MAX_CROP_BYTES = 8 * 1024**2
MAX_JSON_BYTES = 2 * 1024**2
MAX_FRAMES = 16
MAX_SECONDS = 7200
PTS_RE = re.compile(r"\bpts_time:\s*(-?\d+(?:\.\d+)?)")
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def pairs_unique(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, "Duplicate JSON key")
        obj[key] = value
    return obj


def read_request(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= MAX_JSON_BYTES,
            "Unsafe request file")
    obj = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs_unique,
                     parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
    require(type(obj) is dict and set(obj) == {"schema_version", "frames"} and
            type(obj["schema_version"]) is int and obj["schema_version"] == 1 and
            type(obj["frames"]) is list and 1 <= len(obj["frames"]) <= MAX_FRAMES,
            "Invalid request schema")
    seen = set()
    for item in obj["frames"]:
        require(type(item) is dict and set(item) == {"event_index", "frame_index", "bbox_pixels"},
                "Invalid frame request")
        ev, frame, box = item["event_index"], item["frame_index"], item["bbox_pixels"]
        require(type(ev) is int and 0 <= ev < 500 and ev not in seen, "Invalid event index")
        seen.add(ev)
        require(type(frame) is int and 0 <= frame <= 1_000_000, "Invalid frame index")
        require(type(box) is list and len(box) == 4 and
                all(type(v) is int and 0 <= v <= 32768 for v in box) and
                box[2] > 0 and box[3] > 0, "Invalid bounding box")
    return obj


def source_hash(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "Unsafe recording path")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_VIDEO_BYTES,
                "Invalid recording size/type")
        digest = hashlib.sha256()
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
        after = os.fstat(handle.fileno())
        require((before.st_size, before.st_mtime_ns, before.st_ino) ==
                (after.st_size, after.st_mtime_ns, after.st_ino), "Recording changed while hashing")
    return digest.hexdigest()


def run(args, timeout):
    try:
        return subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=True, timeout=timeout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise ValueError(f"FFmpeg/FFprobe failed: {type(exc).__name__}") from exc


def probe(path):
    result = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                  "-show_entries", "stream=width,height,codec_type:format=duration",
                  "-of", "json", str(path)], 45)
    obj = json.loads(result.stdout)
    streams = obj.get("streams", [])
    require(len(streams) == 1 and streams[0].get("codec_type") == "video", "Missing video stream")
    width, height = streams[0].get("width"), streams[0].get("height")
    require(type(width) is int and type(height) is int and
            0 < width <= 7680 and 0 < height <= 4320, "Unsupported video dimensions")
    try:
        duration = float(obj["format"]["duration"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Missing recording duration") from exc
    require(math.isfinite(duration) and 0 < duration <= MAX_SECONDS, "Unsupported duration")
    return width, height, duration


def extract(path, frame_index, box, dest, duration):
    x, y, w, h = box
    vf = f"select=eq(n\\,{frame_index}),showinfo,crop={w}:{h}:{x}:{y}"
    result = run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info", "-noautorotate",
                  "-i", str(path), "-map", "0:v:0", "-an", "-sn", "-dn",
                  "-vf", vf, "-frames:v", "1", "-fps_mode", "passthrough",
                  "-f", "image2", "-vcodec", "png", str(dest)], 120)
    logs = result.stderr.decode("utf-8", "replace")
    showinfo = [line for line in logs.splitlines() if "Parsed_showinfo" in line and "pts_time:" in line]
    require(len(showinfo) == 1, "Cannot establish unique decoded-frame PTS")
    match = PTS_RE.search(showinfo[0])
    require(match is not None, "Missing decoded-frame PTS")
    pts = float(match.group(1))
    require(math.isfinite(pts) and 0 <= pts <= duration + 1, "Frame PTS outside recording")
    require(dest.is_file() and not dest.is_symlink(), "Missing extracted crop")
    raw = dest.read_bytes()
    require(0 < len(raw) <= MAX_CROP_BYTES and raw.startswith(b"\x89PNG\r\n\x1a\n"),
            "Invalid PNG crop")
    return pts, hashlib.sha256(raw).hexdigest()


def create(video_path, ledger_path, request_path, output_directory):
    """Extract selected frames, verify source hash stability, write manifest last.

    The output directory must not already exist. On failure it is removed.
    """
    video, ledger_file, out = map(Path, (video_path, ledger_path, output_directory))
    require(video.suffix.lower() in (".mp4", ".webm", ".mkv", ".mov"), "Unsupported extension")
    require(out.parent.is_dir() and not out.parent.is_symlink() and not out.exists(),
            "Unsafe output directory")
    from offline_action_evidence_link import read_json
    ledger, _ = read_json(ledger_file)
    require(ledger.get("schema_version") == 1 and
            ledger.get("status") == "conditional_observation_ledger_not_video_verified" and
            ledger.get("video_evidence_verified") is False and
            ledger.get("ready_for_equity_or_ev") is False and
            type(ledger.get("events")) is list and len(ledger["events"]) <= 500 and
            type(ledger.get("table_id")) is int and 1 <= ledger["table_id"] <= 4 and
            ledger.get("variant") in ("PLO5", "PLO6") and
            type(ledger.get("hand_label")) is str and
            type(ledger.get("input_canonical_sha256")) is str and
            SHA_RE.fullmatch(ledger["input_canonical_sha256"]), "Unsupported ledger")
    req = read_request(request_path)
    for item in req["frames"]:
        require(item["event_index"] < len(ledger["events"]), "Event outside ledger")
    before = source_hash(video)
    width, height, duration = probe(video)
    for item in req["frames"]:
        x, y, w, h = item["bbox_pixels"]
        require(x + w <= width and y + h <= height, "Crop outside video dimensions")
    out.mkdir(mode=0o700)
    try:
        observations = []
        for item in req["frames"]:
            idx = item["event_index"]
            name = f"event_{idx:03d}.png"
            pts, crop_sha = extract(video, item["frame_index"], item["bbox_pixels"],
                                    out / name, duration)
            event_pts = ledger["events"][idx].get("source_pts_seconds")
            require(type(event_pts) in (int, float) and math.isfinite(event_pts) and
                    abs(event_pts - pts) <= 1.5, "Frame PTS too far from ledger event")
            observations.append({
                "event_index": idx, "frame_pts_seconds": pts,
                "crop_path": name, "crop_sha256": crop_sha,
                "bbox_pixels": item["bbox_pixels"],
                "recognition_confidence": 0.0, "extraction_method": "ffmpeg_frame",
            })
        require(source_hash(video) == before, "Recording changed during extraction")
        manifest = {
            "schema_version": 1, "source_recording_sha256": before,
            "source_duration_seconds": duration,
            "ledger_input_canonical_sha256": ledger["input_canonical_sha256"],
            "table_id": ledger["table_id"], "hand_label": ledger["hand_label"],
            "observations": observations,
        }
        # Verify compatibility without claiming recognition truth.
        from offline_action_evidence_link import link
        report = link(ledger, manifest, out)
        require(report["linked_count"] == len(observations), "Link validation failed")
        (out / "evidence_manifest.json").write_text(
            json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (out / "provenance_status.json").write_text(json.dumps({
            "schema_version": 1, "source_sha256_verified_before_and_after": True,
            "frame_pts_observed_from_ffmpeg_showinfo": True,
            "crop_hashes_verified": True, "source_video_path": video.name,
            "frame_indices": [i["frame_index"] for i in req["frames"]],
            "ocr_verified": False, "cards_actions_verified": False,
            "equity_ev_authorized": False,
            "limitations": ["FFmpeg PTS is decoder output, not independent visual ground truth.",
                            "No OCR or hand reconstruction is performed.",
                            "A source file can be replaced concurrently despite double hashing."],
        }, indent=2) + "\n", encoding="utf-8")
        return manifest
    except BaseException:
        shutil.rmtree(out)
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("recorded_video")
    p.add_argument("ledger_report_json")
    p.add_argument("frame_requests_json")
    p.add_argument("new_output_directory")
    a = p.parse_args(argv)
    manifest = create(a.recorded_video, a.ledger_report_json,
                      a.frame_requests_json, a.new_output_directory)
    print(json.dumps({"frames": len(manifest["observations"]),
                      "source_sha256": manifest["source_recording_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
