"""Read-only decoded-frame PTS cross-check for reviewed offline PLO5/PLO6 clips.

Re-audits cycle-139 pipeline artifacts and SHA-256 of the actual recording,
then checks the nearest decoded source frame PTS to *human-entered* times.
This does not verify the visual content, OCR, actions, hand boundaries, or EV.
Only pre-recorded local MP4/WebM inputs are accepted. No live interfaces.
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
import stat
import subprocess
import tempfile
import time
from urllib.parse import quote

from offline_reviewed_decision_timeline import build_index, file_hash, require, NAME

MAX_VIDEO_BYTES = 16 * 1024**3
MAX_PTS_BYTES = 32 * 1024 * 1024
MAX_FRAMES = 500_000
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
PTS_PATTERN = re.compile(r"-?\d+(?:\.\d+)?\Z")


def safe_output(path, extension, parent):
    path = Path(path)
    require(path.suffix == extension and NAME.fullmatch(path.stem) and
            path.parent.resolve() == parent.resolve() and
            path.parent.is_dir() and not path.parent.is_symlink() and
            not path.exists() and not path.is_symlink(),
            "Output must be a new local file beside the pipeline folders")
    return path


def recording_hash(recording):
    video = Path(recording)
    require(video.suffix.lower() in (".mp4", ".webm") and
            video.is_file() and not video.is_symlink() and
            not video.parent.is_symlink(), "Unsafe or unsupported recording")
    return file_hash(video, MAX_VIDEO_BYTES)[0]


def _points(index):
    points = []
    for hand in index["hands"]:
        if hand["clip_sha256"] is None:
            continue
        for kind, field in (("start", "clip_start_seconds_human"),
                            ("decision", "decision_seconds_human"),
                            ("end", "clip_end_seconds_human")):
            target = hand[field]
            require(type(target) in (int, float) and math.isfinite(target) and target >= 0,
                    "Invalid human timestamp")
            points.append({"directory": hand["result_directory"], "kind": kind,
                           "human_seconds": float(target), "nearest_frame_index": None,
                           "nearest_decoded_pts_seconds": None, "absolute_delta_seconds": None})
    return points


def _scan_pts(recording, points, ffprobe, timeout_seconds, max_frames):
    """FFprobe decodes frame metadata to a bounded temporary file, not RAM.

    Sorting is only for nearest-frame lookup. We do not infer actions from frames.
    """
    require(type(timeout_seconds) is int and 1 <= timeout_seconds <= 1800,
            "Invalid ffprobe timeout")
    require(type(max_frames) is int and 1 <= max_frames <= MAX_FRAMES,
            "Invalid frame limit")
    command = [str(ffprobe), "-v", "error", "-protocol_whitelist", "file",
               "-select_streams", "v:0", "-show_frames", "-show_entries",
               "frame=best_effort_timestamp_time", "-of", "csv=p=0",
               "-i", str(Path(recording).resolve())]
    start = time.monotonic()
    with tempfile.TemporaryFile(mode="w+b") as stream:
        try:
            proc = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stream,
                                  stderr=subprocess.PIPE, timeout=timeout_seconds,
                                  check=False)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("FFprobe frame scan timed out") from exc
        require(proc.returncode == 0, "FFprobe frame scan failed")
        require(stream.tell() <= MAX_PTS_BYTES, "FFprobe PTS output exceeds limit")
        stream.seek(0)
        # Two-pointer nearest-neighbour scan: O(frames + timestamps), rather
        # than comparing every frame with every human-entered timestamp.
        # On exact ties the earlier decoded frame wins, matching the original
        # exhaustive scan's deterministic behaviour.
        ordered = sorted(points, key=lambda p: p["human_seconds"])
        pending = 0
        frame_count = 0
        previous = None
        first = None
        last = None
        for raw in stream:
            line = raw.decode("ascii", errors="strict").strip()
            if not line:
                continue
            token = line.split(",", 1)[0]
            require(PTS_PATTERN.fullmatch(token) is not None,
                    "FFprobe returned an invalid frame PTS")
            pts = float(token)
            require(math.isfinite(pts), "Nonfinite frame PTS")
            # A negative PTS step, however small, invalidates the two-pointer
            # nearest-frame assumption. Reject rather than silently mis-map.
            require(previous is None or pts >= previous,
                    "Decoded frame PTS are not monotonic")
            frame_count += 1
            require(frame_count <= max_frames, "Frame count exceeds configured limit")
            if first is None:
                first = pts
            last = pts
            while pending < len(ordered) and ordered[pending]["human_seconds"] <= pts:
                item = ordered[pending]
                target = item["human_seconds"]
                # Choose the earlier frame on ties; epsilon only protects
                # representation jitter and mirrors the previous 1e-9 rule.
                if previous is not None and abs(previous - target) <= abs(pts - target) + 1e-9:
                    nearest, index = previous, frame_count - 2
                else:
                    nearest, index = pts, frame_count - 1
                item["nearest_frame_index"] = index
                item["nearest_decoded_pts_seconds"] = nearest
                item["absolute_delta_seconds"] = abs(nearest - target)
                pending += 1
            previous = pts
        require(frame_count > 0, "No decoded video frames")
        # Human timestamps beyond the final decoded frame map to the last
        # frame, so they remain review warnings instead of being dropped.
        for item in ordered[pending:]:
            item["nearest_frame_index"] = frame_count - 1
            item["nearest_decoded_pts_seconds"] = previous
            item["absolute_delta_seconds"] = abs(previous - item["human_seconds"])
        return {"decoded_frames_scanned": frame_count,
                "first_decoded_pts_seconds": first,
                "last_decoded_pts_seconds": last,
                "ffprobe_elapsed_seconds": round(time.monotonic() - start, 3)}


def build_report(recording, pipeline_directories, *, tolerance_seconds=0.15,
                 ffprobe="ffprobe", timeout_seconds=600, max_frames=MAX_FRAMES):
    require(type(tolerance_seconds) in (float, int) and
            math.isfinite(tolerance_seconds) and 0 < tolerance_seconds <= 2,
            "Invalid PTS tolerance")
    index = build_index(pipeline_directories)  # Re-check all pipeline SHA-256s.
    actual_sha = recording_hash(recording)
    require(actual_sha == index["source_recording_sha256_claim_unverified"] and
            (index["source_recording_sha256_verified_for_exported_clips"] is None or
             actual_sha == index["source_recording_sha256_verified_for_exported_clips"]),
            "Actual recording SHA-256 differs from pipeline claims")
    points = _points(index)
    scan = _scan_pts(recording, points, ffprobe, timeout_seconds, max_frames)
    # Check the recording did not change while ffprobe was reading it; recheck
    # the pipeline artifacts too, so a changed clip is never published as valid.
    require(recording_hash(recording) == actual_sha,
            "Recording changed during PTS audit")
    require(build_index(pipeline_directories) == index,
            "Pipeline results changed during PTS audit")
    by_directory = {}
    for point in points:
        point["within_tolerance"] = point["absolute_delta_seconds"] <= tolerance_seconds + 1e-9
        by_directory.setdefault(point["directory"], []).append(point)
    hands = []
    for row in index["hands"]:
        samples = by_directory.get(row["result_directory"], [])
        hands.append({"result_directory": row["result_directory"],
                      "table_id": row["table_id"], "hand_label": row["hand_label"],
                      "variant": row["variant"], "pipeline_status": row["pipeline_status"],
                      "clip_sha256": row["clip_sha256"],
                      "frame_pts_checks": samples,
                      "all_declared_times_near_decoded_frames":
                          bool(samples) and all(s["within_tolerance"] for s in samples),
                      "video_content_verified": False})
    return {"schema_version": 1,
            "status": "offline_decoded_frame_pts_crosscheck_not_content_verified",
            "source_recording_sha256_verified_bytes": actual_sha,
            "source_recording_file_size_limit_bytes": MAX_VIDEO_BYTES,
            "frame_pts_tolerance_seconds": float(tolerance_seconds),
            "hand_count": len(hands), "exported_clip_count": len(by_directory),
            "timestamps_checked": len(points),
            "timestamps_outside_tolerance": sum(not p["within_tolerance"] for p in points),
            "frame_scan": scan, "hands": hands,
            "source_file_sha256_verified": True,
            "source_decoded_pts_crosschecked": True,
            "human_hand_boundaries_verified": False,
            "video_content_verified": False, "ocr_accuracy_verified": False,
            "automatic_clip_selection_authorized": False,
            "limitations": [
                "Nearest decoded PTS only checks proximity to human-entered seconds.",
                "PTS proximity does not prove that the right hand or action is visible.",
                "A source SHA-256 match proves bytes match prior claims, not OCR accuracy.",
                "Blocked hands have no approved decision timestamps to check.",
                "Equity/EV and opponent ranges are not recalculated in this audit.",
            ]}


def render_html(report):
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    for hand in report["hands"]:
        rows = []
        for sample in hand["frame_pts_checks"]:
            rows.append("<tr><td>" + esc(sample["kind"]) + "</td><td>" +
                        f'{sample["human_seconds"]:.3f}' + "</td><td>" +
                        f'{sample["nearest_decoded_pts_seconds"]:.3f}' + "</td><td>" +
                        f'{sample["absolute_delta_seconds"]:.3f}' + "</td><td>" +
                        ("Próximo" if sample["within_tolerance"] else "Revisar") + "</td></tr>")
        if hand["clip_sha256"]:
            href = "./" + quote(hand["result_directory"], safe="") + "/clip.mp4"
            media = '<video controls preload="none" src="' + esc(href) + '"></video>'
        else:
            media = "<p>Mão bloqueada: sem clipe e sem timestamp aprovado.</p>"
        cards.append("<article><h2>Mesa " + str(hand["table_id"]) + " · " +
                     esc(hand["hand_label"]) + " · " + esc(hand["variant"]) +
                     "</h2>" + media + ("<table><thead><tr><th>Marco</th><th>Humano (s)</th>"
                     "<th>Frame PTS (s)</th><th>Diferença (s)</th><th>Status</th></tr></thead>"
                     "<tbody>" + "".join(rows) + "</tbody></table>" if rows else "") + "</article>")
    return ('''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self' file:; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>PLO Trainee · PTS da gravação</title><style>
:root{color-scheme:dark}body{font:16px/1.5 system-ui,sans-serif;max-width:1000px;margin:auto;padding:1.5rem;background:#101827;color:#f2f6ff}article,header,aside{border:1px solid #52627b;border-radius:12px;padding:1rem;margin:1rem 0;background:#1d2b40}aside{border-color:#dc9d58;background:#46331d}video{width:100%;max-height:280px;background:black}table{width:100%;border-collapse:collapse}th,td{padding:.5rem;border:1px solid #52627b;text-align:left}code{overflow-wrap:anywhere}</style></head><body>'''
            '<header><h1>PLO Trainee · Auditoria de PTS offline</h1><p>' +
            str(report["hand_count"]) + ' mãos · ' + str(report["timestamps_checked"]) +
            ' marcos verificados contra quadros decodificados · ' +
            str(report["timestamps_outside_tolerance"]) + ' fora da tolerância.</p></header>' +
            '<aside><strong>Não é reconhecimento de pôquer.</strong> Proximidade temporal entre timestamp humano e frame decodificado não comprova cartas, ações, limites de mãos ou correção de equity/EV. Nenhuma seleção automática.</aside>' +
            ''.join(cards) + '<footer><p>SHA-256 da gravação: <code>' +
            esc(report["source_recording_sha256_verified_bytes"]) +
            '</code>. Arquivos locais, sem rede ou JavaScript.</p></footer></body></html>')


def export(recording, directories, new_json, new_html, **kwargs):
    require(type(directories) in (list, tuple) and len(directories) > 0,
            "Missing pipeline directories")
    parent = Path(directories[0]).parent
    require(all(Path(d).parent.resolve() == parent.resolve() for d in directories),
            "Mixed pipeline parent directories")
    out_json = safe_output(new_json, ".json", parent)
    out_html = safe_output(new_html, ".html", parent)
    require(out_json != out_html, "Repeated output path")
    report = build_report(recording, directories, **kwargs)
    payloads = [(out_json, (json.dumps(report, indent=2, sort_keys=True,
                                      ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")),
                (out_html, render_html(report).encode("utf-8"))]
    require(all(0 < len(raw) <= MAX_OUTPUT_BYTES for _, raw in payloads),
            "Report exceeds size limit")
    created = []
    try:
        for path, raw in payloads:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, "O_NOFOLLOW", 0), 0o600)
            created.append(path)
            with os.fdopen(fd, "wb") as stream:
                require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode),
                        "Unsafe output")
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording")
    parser.add_argument("new_report_json")
    parser.add_argument("new_report_html")
    parser.add_argument("pipeline_directories", nargs="+")
    parser.add_argument("--tolerance-seconds", type=float, default=0.15)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    report = export(args.recording, args.pipeline_directories,
                    args.new_report_json, args.new_report_html,
                    tolerance_seconds=args.tolerance_seconds,
                    timeout_seconds=args.timeout_seconds)
    print(json.dumps({"status": report["status"],
                      "timestamps_checked": report["timestamps_checked"],
                      "timestamps_outside_tolerance": report["timestamps_outside_tolerance"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
