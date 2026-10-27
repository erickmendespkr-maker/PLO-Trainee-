"""Create offline JPEG reference frames for *human review* of decoded-source PTS.

The source is an already-recorded local MP4/WebM. All prior pipeline hashes
are rechecked by the cycle-140 PTS audit before a single image is published.
Only out-of-tolerance timestamps are included by default. Optionally include
one decision reference per exported hand. Nothing is OCR-verified or approved;
this is NOT an automatic hand-boundary correction or poker assistant.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from urllib.parse import quote

from offline_reviewed_decision_timeline import build_index, require, NAME
from offline_reviewed_source_pts_audit import build_report, recording_hash

MAX_REFERENCES = 120
MAX_IMAGES = 360
MAX_JPEG_BYTES = 512 * 1024
MAX_REPORT_BYTES = 2 * 1024 * 1024


def _samples(report, include_decisions):
    require(type(include_decisions) is bool, "Invalid include_decisions flag")
    items = []
    for hand in report["hands"]:
        for point in hand["frame_pts_checks"]:
            if point["within_tolerance"] and not (include_decisions and point["kind"] == "decision"):
                continue
            items.append({
                "table_id": hand["table_id"], "hand_label": hand["hand_label"],
                "variant": hand["variant"], "result_directory": hand["result_directory"],
                "kind": point["kind"], "within_tolerance": point["within_tolerance"],
                "original_human_seconds": point["human_seconds"],
                "nearest_decoded_pts_seconds": point["nearest_decoded_pts_seconds"],
                "nearest_frame_index": point["nearest_frame_index"],
                "absolute_delta_seconds": point["absolute_delta_seconds"],
                "corrected_seconds": None, "approved_by_human": False,
            })
    require(len(items) <= MAX_REFERENCES, "Too many reference points")
    return items


def _indices(items, total_frames):
    require(type(total_frames) is int and total_frames > 0, "Invalid decoded frame count")
    selected = set()
    for item in items:
        index = item["nearest_frame_index"]
        require(type(index) is int and 0 <= index < total_frames,
                "Invalid decoded frame index")
        selected.update(i for i in (index - 1, index, index + 1) if 0 <= i < total_frames)
    require(len(selected) <= MAX_IMAGES, "Too many reference images")
    return sorted(selected)


def _extract(recording, selected, directory, ffmpeg, timeout_seconds):
    """Single bounded decode pass, selecting exact frame indices (not approximate seek)."""
    if not selected:
        return {}
    require(type(timeout_seconds) is int and 1 <= timeout_seconds <= 1800,
            "Invalid FFmpeg timeout")
    # All inputs to the filter are validated integers. FFmpeg's select filter
    # counts decoded video frames in the same presentation order as FFprobe.
    expression = "+".join(f"eq(n\\,{n})" for n in selected)
    pattern = directory / "frame_%04d.jpg"
    command = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin",
               "-protocol_whitelist", "file", "-i", str(Path(recording).resolve()),
               "-map", "0:v:0", "-an", "-sn", "-dn", "-vf",
               f"select='{expression}',scale=320:-2:flags=bicubic",
               "-fps_mode", "vfr", "-frames:v", str(len(selected)),
               "-q:v", "4", "-start_number", "0", str(pattern)]
    try:
        proc = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("FFmpeg reference extraction timed out") from exc
    require(proc.returncode == 0, "FFmpeg reference extraction failed")
    outputs = sorted(directory.glob("frame_*.jpg"))
    require(len(outputs) == len(selected), "Unexpected number of extracted reference frames")
    mapping = {}
    for ordinal, (index, path) in enumerate(zip(selected, outputs)):
        require(path.name == f"frame_{ordinal:04d}.jpg" and
                path.is_file() and not path.is_symlink(), "Unexpected extracted image")
        size = path.stat().st_size
        require(4 <= size <= MAX_JPEG_BYTES, "Reference JPEG size out of bounds")
        with path.open("rb") as stream:
            require(stream.read(2) == b"\xff\xd8", "Invalid JPEG signature")
            stream.seek(-2, os.SEEK_END)
            require(stream.read(2) == b"\xff\xd9", "Incomplete JPEG")
        mapping[index] = {"file": path.name,
                          "sha256": _hash(path), "bytes": size}
    return mapping


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _page(report, items, images):
    esc = lambda x: html.escape(str(x), quote=True)
    cards = []
    for item in items:
        center = item["nearest_frame_index"]
        pictures = []
        for index in (center - 1, center, center + 1):
            if index not in images:
                continue
            filename = images[index]["file"]
            pictures.append('<figure><img loading="lazy" src="./' +
                            quote(filename, safe="") + '" alt="Quadro decodificado ' +
                            str(index) + '"><figcaption>Frame #' + str(index) +
                            (' · PTS mais próximo' if index == center else ' · vizinho') +
                            '</figcaption></figure>')
        cards.append('<article><h2>Mesa ' + esc(item["table_id"]) + ' · ' +
                     esc(item["hand_label"]) + ' · ' + esc(item["kind"]) +
                     '</h2><p>Timestamp humano: ' + f'{item["original_human_seconds"]:.3f}' +
                     ' s · PTS mais próximo: ' + f'{item["nearest_decoded_pts_seconds"]:.3f}' +
                     ' s · diferença: ' + f'{item["absolute_delta_seconds"]:.3f}' +
                     ' s · ' + ('dentro da tolerância' if item["within_tolerance"] else
                                'FORA DA TOLERÂNCIA') +
                     '</p><div class="frames">' + ''.join(pictures) + '</div></article>')
    if not cards:
        cards.append('<article><p>Nenhum timestamp sinalizado. Ative '
                     '<code>--include-decisions</code> para incluir quadros de decisões '
                     'mesmo quando os timestamps estiverem dentro da tolerância.</p></article>')
    return ('''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' file:; style-src 'unsafe-inline'; script-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>PLO Trainee · Referências para revisão</title><style>
:root{color-scheme:dark}body{background:#111827;color:#f3f4f6;font:16px/1.5 system-ui,sans-serif;max-width:1120px;margin:auto;padding:20px}article,header,aside{border:1px solid #4b5563;background:#1f2937;border-radius:12px;padding:16px;margin:14px 0}aside{border-color:#f59e0b}.frames{display:flex;gap:12px;flex-wrap:wrap}figure{margin:0;flex:1 1 220px;max-width:320px}img{width:100%;height:auto;border:1px solid #64748b;border-radius:6px}figcaption{font-size:13px}code{overflow-wrap:anywhere}</style></head><body>'''
            '<header><h1>PLO Trainee · Quadros de referência</h1><p>' +
            str(len(items)) + ' pontos para revisão · ' + str(len(images)) +
            ' quadros extraídos · ' + str(report["timestamps_outside_tolerance"]) +
            ' timestamps fora da tolerância.</p></header>' +
            '<aside><strong>Revisão humana obrigatória.</strong> Estas imagens são referências '
            'de quadros decodificados, não prova de carta, ação ou início/fim de mão. '
            'O arquivo JSON é um modelo de correção não aprovado e não pode '
            'autorizar exportações automaticamente.</aside>' + ''.join(cards) +
            '<footer><p>Fonte SHA-256: <code>' +
            esc(report["source_recording_sha256_verified_bytes"]) +
            '</code>. Somente arquivos locais; sem JavaScript ou rede.</p></footer></body></html>')


def export(recording, directories, new_directory, *, include_decisions=False,
           ffmpeg="ffmpeg", ffprobe="ffprobe", timeout_seconds=600,
           tolerance_seconds=0.15):
    require(type(directories) in (list, tuple) and len(directories) > 0,
            "Missing pipeline directories")
    parent = Path(directories[0]).parent
    destination = Path(new_directory)
    require(NAME.fullmatch(destination.name) is not None and
            destination.parent.resolve() == parent.resolve() and
            parent.is_dir() and not parent.is_symlink() and
            not destination.exists() and not destination.is_symlink(),
            "Output must be a new directory beside pipeline folders")
    require(all(Path(d).parent.resolve() == parent.resolve() for d in directories),
            "Mixed pipeline directories")
    require(type(timeout_seconds) is int and 1 <= timeout_seconds <= 1800,
            "Invalid FFmpeg timeout")
    original_index = build_index(directories)
    report = build_report(recording, directories, ffprobe=ffprobe,
                          timeout_seconds=timeout_seconds,
                          tolerance_seconds=tolerance_seconds)
    items = _samples(report, include_decisions)
    selected = _indices(items, report["frame_scan"]["decoded_frames_scanned"])
    source_sha = report["source_recording_sha256_verified_bytes"]
    with tempfile.TemporaryDirectory(prefix=".plo_reference_", dir=parent) as temporary:
        stage = Path(temporary)
        images = _extract(recording, selected, stage, ffmpeg, timeout_seconds)
        require(recording_hash(recording) == source_sha,
                "Source recording changed during reference extraction")
        require(build_index(directories) == original_index,
                "Pipeline results changed during reference extraction")
        # The report is a manual-review artifact only, NOT an approved annotation.
        for item in items:
            center = item["nearest_frame_index"]
            item["reference_images"] = [images[i]["file"] for i in
                                        (center - 1, center, center + 1) if i in images]
        template = {
            "schema_version": 1,
            "status": "requires_human_review_not_approved_for_pipeline",
            "source_recording_sha256_verified_bytes": source_sha,
            "pts_audit_status": report["status"],
            "timestamps_checked": report["timestamps_checked"],
            "timestamps_outside_tolerance": report["timestamps_outside_tolerance"],
            "frame_count": report["frame_scan"]["decoded_frames_scanned"],
            "reference_images": {str(k): v for k, v in images.items()},
            "review_points": items,
            "approved_for_export": False,
            "video_content_verified": False,
            "ocr_accuracy_verified": False,
            "automatic_hand_boundary_correction": False,
            "limitations": [
                "PTS and frame proximity do not establish poker content accuracy.",
                "Neighbouring frame PTS are not individually audited here.",
                "Corrected seconds are blank until entered by a human reviewer.",
                "This template is not a pipeline-approved clip annotation.",
            ],
        }
        payloads = {
            "review_template.json": (json.dumps(template, indent=2, sort_keys=True,
                                                 ensure_ascii=False, allow_nan=False) + "\n").encode(),
            "contact_sheet.html": _page(report, items, images).encode(),
        }
        require(all(0 < len(raw) <= MAX_REPORT_BYTES for raw in payloads.values()),
                "Reference report exceeds size limit")
        for name, raw in payloads.items():
            (stage / name).write_bytes(raw)
        # Publish only after successful verification and extraction. Create-only
        # hardlinks avoid overwriting any existing result; rollback on failure.
        destination.mkdir(mode=0o700, exist_ok=False)
        published = []
        try:
            allowed = {"review_template.json", "contact_sheet.html"} | {
                meta["file"] for meta in images.values()}
            require({p.name for p in stage.iterdir()} == allowed,
                    "Unexpected staged output")
            for path in sorted(stage.iterdir()):
                require(path.is_file() and not path.is_symlink(), "Unsafe staged output")
                target = destination / path.name
                os.link(path, target, follow_symlinks=False)
                published.append(target)
        except BaseException:
            for path in reversed(published):
                path.unlink(missing_ok=True)
            try:
                destination.rmdir()
            except OSError:
                pass
            raise
    return template


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording")
    parser.add_argument("new_reference_directory")
    parser.add_argument("pipeline_directories", nargs="+")
    parser.add_argument("--include-decisions", action="store_true")
    parser.add_argument("--tolerance-seconds", type=float, default=0.15)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    report = export(args.recording, args.pipeline_directories, args.new_reference_directory,
                    include_decisions=args.include_decisions,
                    tolerance_seconds=args.tolerance_seconds,
                    timeout_seconds=args.timeout_seconds)
    print(json.dumps({"status": report["status"],
                      "review_points": len(report["review_points"]),
                      "reference_images": len(report["reference_images"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
