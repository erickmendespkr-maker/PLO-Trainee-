"""Read-only offline HTML review page for terminal MP4 audit reports.

Input is a small JSON manifest in the same folder as the source recording,
exported clips and Cycle-130 tail-audit reports. Every referenced file must be
regular, local, and content-hash consistent. All alerts remain *diagnostic*.
No OCR, hand reconstruction, equity, EV, or automatic decisions are authorized.
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
from urllib.parse import quote

MAX_REPORT = 128 * 1024
MAX_MANIFEST = 128 * 1024
MAX_HTML = 512 * 1024
MAX_VIDEO_BYTES = 12 * 1024**3
MAX_ENTRIES = 40
SHA = re.compile(r"[0-9a-f]{64}\Z")
CATEGORIES = {
    "no_anomaly_detected_in_compared_tail": "Nenhuma anomalia detectada na cauda (não é prova)",
    "possible_added_terminal_duplicate": "Possível duplicação terminal",
    "possible_missing_terminal_frames": "Possível ausência de quadros finais",
    "multiple_possible_terminal_anomalies": "Múltiplas anomalias possíveis",
    "indeterminate_static_or_insufficient_source_motion": "Indeterminado: cena estática",
    "indeterminate_terminal_difference": "Indeterminado: diferença visual",
}


def require(condition, why):
    if not condition:
        raise ValueError(why)


def _no_duplicates(pairs):
    obj = {}
    for k, v in pairs:
        require(k not in obj, "Duplicate JSON key")
        obj[k] = v
    return obj


def _no_constant(value):
    raise ValueError(f"Non-finite JSON constant: {value}")


def regular_file(root: Path, name: str, suffix: str | tuple[str, ...], max_bytes: int) -> Path:
    require(type(name) is str and 1 <= len(name) <= 180 and
            name not in (".", "..") and name == Path(name).name and
            not any(ch in name for ch in ("/", "\\", "\x00")) and
            name.lower().endswith(suffix), "Unsafe local filename")
    path = root / name
    require(path.is_file() and not path.is_symlink(), "Missing/unsafe local file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= max_bytes,
                "Invalid file size/type")
    finally:
        os.close(fd)
    return path


def digest(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_VIDEO_BYTES,
                "Invalid file size")
        sha = hashlib.sha256()
        while chunk := stream.read(1024 * 1024):
            sha.update(chunk)
        after = os.fstat(stream.fileno())
        require((before.st_size, before.st_mtime_ns, before.st_ino) ==
                (after.st_size, after.st_mtime_ns, after.st_ino),
                "File changed during hashing")
        return sha.hexdigest()


def read_json(path: Path, maximum: int) -> dict:
    require(path.stat().st_size <= maximum, "JSON too large")
    obj = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicates,
                     parse_constant=_no_constant)
    require(type(obj) is dict, "Expected JSON object")
    return obj


def load(manifest_path: str | Path) -> tuple[str, list[dict], list[tuple[Path, str]]]:
    path = Path(manifest_path)
    root = path.parent
    require(root.is_dir() and not root.is_symlink(), "Unsafe manifest folder")
    regular_file(root, path.name, ".json", MAX_MANIFEST)
    manifest = read_json(path, MAX_MANIFEST)
    require(set(manifest) == {"schema_version", "session_label", "source_recording", "entries"} and
            type(manifest["schema_version"]) is int and manifest["schema_version"] == 1 and
            type(manifest["session_label"]) is str and
            0 < len(manifest["session_label"]) <= 120 and
            type(manifest["entries"]) is list and
            1 <= len(manifest["entries"]) <= MAX_ENTRIES, "Invalid review manifest")
    source = regular_file(root, manifest["source_recording"],
                          (".mp4", ".webm", ".mkv", ".mov"), MAX_VIDEO_BYTES)
    source_sha = digest(source)
    seen = {path.name, source.name}
    files = [(path, digest(path)), (source, source_sha)]
    rows = []
    for entry in manifest["entries"]:
        require(type(entry) is dict and set(entry) == {"clip", "tail_audit", "hand_label"} and
                type(entry["hand_label"]) is str and
                1 <= len(entry["hand_label"]) <= 120, "Invalid review entry")
        clip = regular_file(root, entry["clip"], ".mp4", MAX_VIDEO_BYTES)
        audit = regular_file(root, entry["tail_audit"], ".json", MAX_REPORT)
        require(clip.name not in seen and audit.name not in seen and clip != audit,
                "Duplicate input filename")
        seen.update((clip.name, audit.name))
        report = read_json(audit, MAX_REPORT)
        require(report.get("schema_version") == 1 and
                report.get("status") == "terminal_sequence_diagnostic_only" and
                report.get("classification") in CATEGORIES and
                type(report.get("source_sha256")) is str and
                SHA.fullmatch(report["source_sha256"]) and
                type(report.get("clip_sha256")) is str and
                SHA.fullmatch(report["clip_sha256"]) and
                report["source_sha256"] == source_sha and
                report["clip_sha256"] == digest(clip),
                "Tail audit does not match source/clip bytes")
        for flag in ("possible_added_terminal_duplicate", "possible_missing_terminal_frames",
                     "visual_provenance_verified", "ocr_verified", "equity_ev_authorized"):
            require(type(report.get(flag)) is bool, "Invalid diagnostic flag")
        require(not report["visual_provenance_verified"] and
                not report["ocr_verified"] and not report["equity_ev_authorized"],
                "Unexpected claim of verification")
        for key in ("terminal_frame_mae_0_to_255", "source_container_duration_seconds",
                    "clip_container_duration_seconds"):
            value = report.get(key)
            require(type(value) in (int, float) and math.isfinite(value) and
                    value >= 0, "Invalid diagnostic number")
        if report["classification"] == "possible_added_terminal_duplicate":
            require(report["possible_added_terminal_duplicate"], "Contradictory duplicate flag")
        if report["classification"] == "possible_missing_terminal_frames":
            require(report["possible_missing_terminal_frames"], "Contradictory missing flag")
        files.extend([(clip, report["clip_sha256"]), (audit, digest(audit))])
        rows.append({"hand_label": entry["hand_label"], "clip": clip.name,
                     "classification": report["classification"],
                     "terminal_mae": report["terminal_frame_mae_0_to_255"],
                     "source_seconds": report["source_container_duration_seconds"],
                     "clip_seconds": report["clip_container_duration_seconds"],
                     "duplicate": report["possible_added_terminal_duplicate"],
                     "missing": report["possible_missing_terminal_frames"]})
    return manifest["session_label"], rows, files


def render(label: str, rows: list[dict]) -> str:
    escape = lambda x: html.escape(str(x), quote=True)
    cards = []
    for row in rows:
        clean = row["classification"] == "no_anomaly_detected_in_compared_tail"
        badge = "sem-anomalia-detectada" if clean else "revisao-temporal-necessaria"
        url = "./" + quote(row["clip"], safe="")
        cards.append(f'''<article><h2>{escape(row['hand_label'])}</h2>
<p class="badge">{escape(badge)} · {escape(CATEGORIES[row['classification']])}</p>
<video controls preload="none" playsinline src="{escape(url)}">Corte local indisponível.</video>
<p>MAE do último quadro: {row['terminal_mae']:.3f}/255 · Duração fonte: {row['source_seconds']:.3f}s · Corte: {row['clip_seconds']:.3f}s.</p>
<p>Possível duplicação: {str(row['duplicate']).lower()} · Possíveis quadros ausentes: {str(row['missing']).lower()}.</p>
<p>Revisão humana do vídeo e das cartas/ações continua obrigatória.</p></article>''')
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self' file:; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>PLO Trainee · Auditoria temporal · {escape(label)}</title><style>
:root{{color-scheme:dark}}body{{font:16px/1.5 system-ui,sans-serif;max-width:960px;margin:auto;padding:1.5rem;background:#101827;color:#eef4fc}}
header,article,aside{{border:1px solid #41536b;border-radius:12px;padding:1rem;margin:1rem 0;background:#1b293d}}
aside{{border-color:#e6aa54;background:#44301e}}video{{width:100%;max-height:400px;background:black}}
.badge{{font-weight:bold}}h2{{overflow-wrap:anywhere}}
</style></head><body><header><h1>PLO Trainee · Revisão temporal offline</h1>
<p>{escape(label)} · {len(rows)} cortes · {sum(r['classification'] != 'no_anomaly_detected_in_compared_tail' for r in rows)} alertas/indeterminações temporais.</p></header>
<aside><strong>Diagnóstico, não prova.</strong> Comparação de pixels pode confundir cenas estáticas, reencodificação e quadros repetidos. Nenhuma carta, ação, equity, EV ou decisão estratégica foi validada. Não existe autorização para análise automática.</aside>
{''.join(cards)}<footer><p>Somente leitura · arquivo local · sem JavaScript ou conexão com plataformas de pôquer.</p></footer></body></html>'''


def export(manifest_path: str | Path, new_html_path: str | Path) -> dict:
    target = Path(new_html_path)
    manifest = Path(manifest_path)
    require(target.suffix.lower() == ".html" and target.parent.is_dir() and
            not target.parent.is_symlink() and target.parent.resolve() == manifest.parent.resolve() and
            not target.exists() and not target.is_symlink(),
            "HTML output must be new and beside the manifest")
    label, rows, hashes = load(manifest)
    payload = render(label, rows).encode("utf-8")
    require(len(payload) <= MAX_HTML, "HTML too large")
    require(all(digest(path) == expected for path, expected in hashes),
            "Input changed while generating review")
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Unsafe output")
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return {"status": "offline_temporal_review_not_video_verified", "clips": len(rows),
            "temporal_alerts_or_indeterminate": sum(
                row["classification"] != "no_anomaly_detected_in_compared_tail" for row in rows),
            "manual_review_required": True, "equity_ev_authorized": False,
            "output": str(target)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("temporal_review_manifest_json")
    parser.add_argument("new_temporal_review_html")
    args = parser.parse_args(argv)
    print(json.dumps(export(args.temporal_review_manifest_json, args.new_temporal_review_html)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
