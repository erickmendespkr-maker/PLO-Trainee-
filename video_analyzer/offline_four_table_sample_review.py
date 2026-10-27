"""Offline four-table region sample review from user-authorized MP4/WebM recordings.

Produces source-PTS-bound, SHA-256-verified PNGs and a local HTML review page.
Grid/manual coordinates are *not* automatic poker-table detection. No OCR,
hand inference, equity/EV, or automatic clip approval is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from table_regions import Region, grid_regions, validate_regions
from video_validator import validate_recording

STATUS = "unverified_four_table_region_samples_for_manual_review_only"
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
PTS = re.compile(r"\bpts_time:\s*(-?\d+(?:\.\d+)?)")
MAX_SAMPLES = 8
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 160 * 1024 * 1024


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def _read_json(path):
    path = Path(path)
    _require(path.is_file() and not path.is_symlink() and
             0 < path.stat().st_size <= 64 * 1024, "Invalid JSON input")
    return json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=_no_duplicate_keys,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(args, timeout=90):
    try:
        return subprocess.run(args, stdin=subprocess.DEVNULL, check=True,
                              capture_output=True, timeout=timeout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError) as exc:
        raise ValueError(f"FFmpeg/FFprobe failed: {type(exc).__name__}") from exc


def _image_size(path):
    path = Path(path)
    _require(path.is_file() and not path.is_symlink() and
             24 <= path.stat().st_size <= MAX_IMAGE_BYTES, "Invalid PNG image")
    with path.open("rb") as stream:
        header = stream.read(24)
    _require(header[:16] == b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "Invalid PNG header")
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    _require(0 < width <= 8192 and 0 < height <= 8192, "Invalid PNG dimensions")
    return width, height


def _regions(layout, width, height):
    _require(type(layout) is dict and layout.get("schema_version") == 1 and
             type(layout.get("schema_version")) is int, "Invalid layout version")
    if layout.get("layout") == "grid":
        _require(set(layout) == {"schema_version", "layout", "rows", "columns"},
                 "Unexpected grid fields")
        rows, cols = layout["rows"], layout["columns"]
        _require(type(rows) is int and type(cols) is int and
                 1 <= rows * cols <= 4 and rows > 0 and cols > 0,
                 "Grid must contain one to four regions")
        regions = grid_regions(width, height, rows, cols)
    elif layout.get("layout") == "manual":
        _require(set(layout) == {"schema_version", "layout", "regions"} and
                 type(layout["regions"]) is list and 1 <= len(layout["regions"]) <= 4,
                 "Invalid manual regions")
        regions = []
        for item in layout["regions"]:
            _require(type(item) is dict and
                     set(item) == {"table_id", "x", "y", "width", "height"} and
                     all(type(v) is int for v in item.values()) and
                     1 <= item["table_id"] <= 4, "Invalid manual region")
            regions.append(Region(**item))
    else:
        raise ValueError("Unknown layout type")
    validate_regions(regions, width, height)
    return sorted(regions, key=lambda r: r.table_id)


def _timestamps(values, duration):
    _require(type(values) is list and 1 <= len(values) <= MAX_SAMPLES,
             "Require one to eight sample times")
    previous = -1.0
    for value in values:
        _require(type(value) in (int, float) and math.isfinite(value) and
                 0 <= value < duration and value > previous,
                 "Sample times must be finite, ordered, unique, and inside recording")
        previous = value
    return [float(v) for v in values]


def _extract_frame(video, requested_pts, output, expected_size):
    # -copyts preserves source PTS after input-side seek; without it FFmpeg
    # resets the timestamp to zero/relative time after -ss.
    proc = _run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info",
                 "-noautorotate", "-ss", str(requested_pts), "-copyts",
                 "-i", str(video), "-map", "0:v:0", "-an", "-sn", "-dn",
                 "-vf", "showinfo", "-frames:v", "1", "-update", "1",
                 "-f", "image2", "-vcodec", "png", str(output)])
    lines = [line for line in proc.stderr.decode("utf-8", "replace").splitlines()
             if "Parsed_showinfo" in line and "pts_time:" in line]
    _require(len(lines) == 1, "Cannot establish one decoded source PTS")
    match = PTS.search(lines[0])
    _require(match is not None, "Missing decoded source PTS")
    pts = float(match.group(1))
    _require(math.isfinite(pts) and pts >= requested_pts - 0.001 and
             pts < requested_pts + 5.0, "Decoded PTS unexpectedly far from seek")
    _require(_image_size(output) == expected_size, "Source frame dimensions mismatch")
    return pts


def _crop_frame(frame, region, output):
    _run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
          "-i", str(frame), "-vf", f"crop={region.width}:{region.height}:{region.x}:{region.y}",
          "-frames:v", "1", "-update", "1", "-f", "image2",
          "-vcodec", "png", str(output)], timeout=45)
    _require(_image_size(output) == (region.width, region.height),
             "Table crop dimensions mismatch")


def _page(report):
    sections = []
    for row in report["samples"]:
        crops = "".join(
            '<figure><img loading="lazy" src="' + html.escape(c["path"], quote=True) +
            '"><figcaption>Mesa ' + str(c["table_id"]) +
            ' — coordenadas declaradas, não detectadas</figcaption></figure>'
            for c in row["table_crops"])
        sections.append('<section><h2>Solicitado ' + str(row["requested_seek_seconds"]) +
                        ' s · PTS decodificado ' + str(row["decoded_source_pts_seconds"]) +
                        ' s</h2><div class="grid">' + crops + '</div></section>')
    return ("<!doctype html><html lang=pt-BR><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Revisão de regiões — PLO Trainee</title><style>"
            "body{font:16px system-ui;max-width:1150px;margin:auto;padding:24px}"
            ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px}"
            "figure{margin:0}img{width:100%;height:auto}section{margin:30px 0}"
            "figcaption{font-size:13px} .warn{background:#fff1c2;padding:12px}</style>"
            "<h1>Revisão offline de até quatro regiões</h1>"
            "<p class=warn>Regiões e quadros não verificam cartas, ações, limites de mãos "
            "ou decisões matemáticas. Revisão humana obrigatória.</p>"+
            "".join(sections)+"</html>\n")


def build(video_path, layout_json, output_dir, sample_times):
    """Export a create-only, auditable set of frame and table-region PNGs."""
    video, layout_path, output = map(Path, (video_path, layout_json, output_dir))
    _require(video.is_file() and not video.is_symlink(), "Unsafe recording")
    layout = _read_json(layout_path)
    _require(output.parent.is_dir() and not output.parent.is_symlink() and
             not output.exists() and not output.is_symlink(), "Output must not exist")
    _require(output.resolve() not in (video.resolve(), layout_path.resolve()) and
             not video.resolve().is_relative_to(output.resolve()) and
             not layout_path.resolve().is_relative_to(output.resolve()),
             "Unsafe output relationship")
    metadata = validate_recording(video)
    width, height, duration = (metadata["width"], metadata["height"],
                               metadata["duration_seconds"])
    regions = _regions(layout, width, height)
    times = _timestamps(sample_times, duration)
    before = _sha(video)
    layout_sha = _sha(layout_path)
    with tempfile.TemporaryDirectory(prefix=".plo_regions_", dir=output.parent) as temp:
        stage = Path(temp)
        (stage / "frames").mkdir()
        (stage / "tables").mkdir()
        total_size = 0
        samples = []
        for i, requested in enumerate(times):
            full_rel = f"frames/frame_{i:02d}.png"
            full_path = stage / full_rel
            pts = _extract_frame(video, requested, full_path, (width, height))
            total_size += full_path.stat().st_size
            crops = []
            for region in regions:
                rel = f"tables/table_{region.table_id:02d}_sample_{i:02d}.png"
                path = stage / rel
                _crop_frame(full_path, region, path)
                total_size += path.stat().st_size
                crops.append({"table_id": region.table_id, "path": rel,
                              "sha256": _sha(path), "width": region.width,
                              "height": region.height})
            _require(total_size <= MAX_TOTAL_IMAGE_BYTES, "Image output budget exceeded")
            samples.append({"requested_seek_seconds": requested,
                            "decoded_source_pts_seconds": pts,
                            "seek_delta_seconds": round(pts - requested, 6),
                            "frame_path": full_rel, "frame_sha256": _sha(full_path),
                            "table_crops": crops})
        _require(_sha(video) == before and _sha(layout_path) == layout_sha,
                 "Recording or layout changed during extraction")
        report = {"schema_version": 1, "analysis_status": STATUS,
                  "recording_sha256": before, "layout_sha256": layout_sha,
                  "recording_duration_seconds": duration,
                  "frame_width": width, "frame_height": height,
                  "regions": [vars(r) for r in regions], "samples": samples,
                  "timestamp_semantics": "decoded_source_pts_seconds_from_ffmpeg_showinfo",
                  "regions_human_confirmed": False,
                  "cards_actions_verified": False,
                  "hand_boundaries_verified": False,
                  "ready_for_equity_or_ev": False,
                  "automatic_clip_selection_authorized": False,
                  "warning": "Only human-declared grid/manual regions and decoded frame PTS; no poker recognition."}
        (stage / "region_samples.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8")
        (stage / "review.html").write_text(_page(report), encoding="utf-8")
        # Publish only after all outputs and input hashes have been verified.
        os.rename(stage, output)
    return report


def verify_bundle(output_dir, recording_path=None):
    """Check hashes, dimensions and fail-closed flags in an existing sample bundle."""
    output = Path(output_dir)
    _require(output.is_dir() and not output.is_symlink(), "Unsafe bundle directory")
    report = _read_json(output / "region_samples.json")
    _require(type(report) is dict and report.get("schema_version") == 1 and
             report.get("analysis_status") == STATUS and
             report.get("timestamp_semantics") ==
             "decoded_source_pts_seconds_from_ffmpeg_showinfo" and
             all(report.get(flag) is False for flag in (
                 "regions_human_confirmed", "cards_actions_verified",
                 "hand_boundaries_verified", "ready_for_equity_or_ev",
                 "automatic_clip_selection_authorized")), "Unsafe bundle status")
    _require(type(report.get("frame_width")) is int and
             type(report.get("frame_height")) is int, "Invalid frame size")
    regions = [Region(**r) for r in report["regions"]]
    _require(1 <= len(regions) <= 4 and all(1 <= r.table_id <= 4 for r in regions),
             "Invalid region IDs")
    validate_regions(regions, report["frame_width"], report["frame_height"])
    _require(type(report.get("samples")) is list and
             1 <= len(report["samples"]) <= MAX_SAMPLES, "Invalid sample count")
    _require(isinstance(report.get("recording_sha256"), str) and
             SHA256.fullmatch(report["recording_sha256"]) and
             isinstance(report.get("layout_sha256"), str) and
             SHA256.fullmatch(report["layout_sha256"]) and
             type(report.get("recording_duration_seconds")) in (int, float) and
             math.isfinite(report["recording_duration_seconds"]) and
             report["recording_duration_seconds"] > 0, "Invalid source provenance")
    seen = set()
    previous_requested = -1.0
    for i, sample in enumerate(report["samples"]):
        requested = sample["requested_seek_seconds"]
        pts = sample["decoded_source_pts_seconds"]
        _require(type(requested) in (int, float) and type(pts) in (int, float) and
                 math.isfinite(requested) and math.isfinite(pts) and
                 previous_requested < requested < report["recording_duration_seconds"] and
                 0 <= requested <= pts + 0.001 and pts < requested + 5.0 and
                 type(sample["seek_delta_seconds"]) in (int, float) and
                 abs(sample["seek_delta_seconds"] - (pts - requested)) < 1e-5,
                 "Invalid timestamp provenance")
        previous_requested = requested
        _require(sample["frame_path"] == f"frames/frame_{i:02d}.png",
                 "Invalid frame path")
        paths = [(sample["frame_path"], sample["frame_sha256"],
                  (report["frame_width"], report["frame_height"]))]
        _require(type(sample["table_crops"]) is list and
                 len(sample["table_crops"]) == len(regions), "Missing table crops")
        for region, crop in zip(regions, sample["table_crops"]):
            _require(crop["table_id"] == region.table_id and
                     crop["path"] == f"tables/table_{region.table_id:02d}_sample_{i:02d}.png" and
                     crop["width"] == region.width and crop["height"] == region.height,
                     "Invalid crop region")
            paths.append((crop["path"], crop["sha256"],
                          (region.width, region.height)))
        for relative, expected_hash, size in paths:
            _require(relative not in seen and isinstance(expected_hash, str) and
                     SHA256.fullmatch(expected_hash), "Invalid file reference")
            seen.add(relative)
            path = output / relative
            _require(_image_size(path) == size and _sha(path) == expected_hash,
                     "PNG hash or dimensions mismatch")
    if recording_path is not None:
        source = Path(recording_path)
        _require(source.is_file() and not source.is_symlink() and
                 _sha(source) == report["recording_sha256"],
                 "Source recording SHA-256 mismatch")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build")
    p.add_argument("recording")
    p.add_argument("regions_json")
    p.add_argument("new_output_directory")
    p.add_argument("--times", required=True, help="Ordered comma-separated source seconds")
    q = sub.add_parser("verify")
    q.add_argument("output_directory")
    q.add_argument("--recording")
    args = parser.parse_args(argv)
    if args.command == "build":
        report = build(args.recording, args.regions_json, args.new_output_directory,
                       [float(x) for x in args.times.split(",")])
    else:
        report = verify_bundle(args.output_directory, args.recording)
    print(json.dumps({"status": report["analysis_status"],
                      "samples": len(report["samples"]),
                      "tables": len(report["regions"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())