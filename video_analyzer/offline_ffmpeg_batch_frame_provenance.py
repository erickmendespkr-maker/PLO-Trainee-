"""Batch offline FFmpeg extraction of *requested* frames from recorded PLO sessions.

Decodes the recording once per request batch, rather than once per crop.
Produces the Cycle-126 evidence-manifest schema. Source/crop integrity and
FFmpeg-reported PTS are checked; card/action recognition is NOT performed.
No network, live capture, or poker platform integration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil

from offline_ffmpeg_frame_provenance import (
    MAX_CROP_BYTES, PTS_RE, SHA_RE, probe, read_request, require, run, source_hash,
)
from offline_action_evidence_link import link, read_json

MAX_FULL_FRAME_BYTES = 64 * 1024 * 1024


def _video_frames(video: Path, indices: list[int], work: Path, duration: float):
    """Return frame-index -> (PNG path, decoded PTS); one source decode."""
    # Inputs are validated integers from read_request, never arbitrary filter text.
    selection = "+".join(f"eq(n\\,{i})" for i in indices)
    pattern = work / "frame_%03d.png"
    timeout = min(1200, max(120, math.ceil(duration * 2)))
    result = run([
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info", "-noautorotate",
        "-i", str(video), "-map", "0:v:0", "-an", "-sn", "-dn",
        "-vf", f"select={selection},showinfo", "-fps_mode", "passthrough",
        "-f", "image2", "-vcodec", "png", str(pattern),
    ], timeout)
    logs = result.stderr.decode("utf-8", "replace")
    lines = [line for line in logs.splitlines()
             if "Parsed_showinfo" in line and "pts_time:" in line]
    require(len(lines) == len(indices), "Missing/extra selected frame PTS")
    found = sorted(work.glob("frame_*.png"))
    require(len(found) == len(indices), "Missing/extra decoded frame PNG")
    output = {}
    previous = -1.0
    for order, (index, line) in enumerate(zip(indices, lines), start=1):
        match = PTS_RE.search(line)
        require(match is not None, "Missing decoded frame PTS")
        pts = float(match.group(1))
        require(math.isfinite(pts) and 0 <= pts <= duration + 1 and pts >= previous,
                "Invalid or non-monotonic decoded frame PTS")
        previous = pts
        frame = work / f"frame_{order:03d}.png"
        require(frame.is_file() and not frame.is_symlink() and
                0 < frame.stat().st_size <= MAX_FULL_FRAME_BYTES and
                frame.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n",
                "Invalid decoded frame PNG")
        output[index] = (frame, pts)
    return output


def _crop_png(frame: Path, box: list[int], dest: Path):
    x, y, w, h = box
    run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
         "-i", str(frame), "-vf", f"crop={w}:{h}:{x}:{y}",
         "-frames:v", "1", "-f", "image2", "-vcodec", "png", str(dest)], 45)
    require(dest.is_file() and not dest.is_symlink() and
            0 < dest.stat().st_size <= MAX_CROP_BYTES, "Invalid crop size")
    raw = dest.read_bytes()
    require(raw.startswith(b"\x89PNG\r\n\x1a\n"), "Invalid crop PNG")
    require((int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")) ==
            (w, h), "Incorrect cropped dimensions")
    return hashlib.sha256(raw).hexdigest()


def create(video_path, ledger_path, request_path, output_directory, *, strategy="full_decode"):
    """Create a new output folder; remove it on any extraction/validation error."""
    require(strategy in ("full_decode", "indexed_seek"), "Unknown extraction strategy")
    video, ledger_file, out = map(Path, (video_path, ledger_path, output_directory))
    require(video.suffix.lower() in (".mp4", ".webm", ".mkv", ".mov"),
            "Unsupported recording extension")
    require(out.parent.is_dir() and not out.parent.is_symlink() and not out.exists(),
            "Unsafe output directory")
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
        work = out / "_temporary_full_frames"
        work.mkdir(mode=0o700)
        indices = sorted({item["frame_index"] for item in req["frames"]})
        if strategy == "indexed_seek":
            from offline_ffmpeg_seek_frame_provenance import seek_video_frames
            frames = seek_video_frames(video, indices, work, duration)
        else:
            frames = _video_frames(video, indices, work, duration)
        observations = []
        for item in req["frames"]:
            idx = item["event_index"]
            frame, pts = frames[item["frame_index"]]
            event_pts = ledger["events"][idx].get("source_pts_seconds")
            require(type(event_pts) in (int, float) and math.isfinite(event_pts) and
                    abs(event_pts - pts) <= 1.5, "Frame PTS too far from ledger event")
            name = f"event_{idx:03d}.png"
            crop_sha = _crop_png(frame, item["bbox_pixels"], out / name)
            observations.append({
                "event_index": idx, "frame_pts_seconds": pts, "crop_path": name,
                "crop_sha256": crop_sha, "bbox_pixels": item["bbox_pixels"],
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
        report = link(ledger, manifest, out)
        require(report["linked_count"] == len(observations), "Link validation failed")
        shutil.rmtree(work)
        (out / "evidence_manifest.json").write_text(
            json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (out / "provenance_status.json").write_text(json.dumps({
            "schema_version": 1, "source_sha256_verified_before_and_after": True,
            "frame_pts_observed_from_ffmpeg_showinfo": True,
            "crop_hashes_verified": True, "source_video_path": video.name,
            "frame_indices": [i["frame_index"] for i in req["frames"]],
            "distinct_frames_decoded": len(indices),
            "video_decode_passes": 1 if strategy == "full_decode" else len(indices),
            "frame_index_probe_passes": 0 if strategy == "full_decode" else 1,
            "extraction_strategy": strategy,
            "ocr_verified": False, "cards_actions_verified": False,
            "equity_ev_authorized": False,
            "limitations": [
                ("Full recording decoded once; no seeking optimization."
                 if strategy == "full_decode" else
                 "FFprobe indexes every decoded frame once; seek extracts requested frames separately."),
                "Frame PTS comes from FFmpeg decoding, not independent visual ground truth.",
                "No OCR or hand reconstruction is performed.",
                "Source path could be swapped concurrently despite double hashing.",
            ],
        }, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        return manifest
    except BaseException:
        shutil.rmtree(out)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recorded_video")
    parser.add_argument("ledger_report_json")
    parser.add_argument("frame_requests_json")
    parser.add_argument("new_output_directory")
    args = parser.parse_args(argv)
    manifest = create(args.recorded_video, args.ledger_report_json,
                      args.frame_requests_json, args.new_output_directory)
    print(json.dumps({"frames": len(manifest["observations"]),
                      "source_sha256": manifest["source_recording_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
