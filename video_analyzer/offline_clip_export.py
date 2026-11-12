"""Offline FFmpeg export of a reviewed clip with provenance; no strategic verdict."""
import hashlib
import json
import math
import subprocess
from pathlib import Path

def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def probe_duration(source):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(source)], capture_output=True, text=True, check=True, timeout=30)
    value = float(json.loads(result.stdout)["format"]["duration"])
    if not math.isfinite(value) or value <= 0:
        raise ValueError("invalid source duration")
    return value

def export_clip(source, output_dir, plan, *, timeout=180):
    """Export reencoded MP4 and JSON sidecar; plan must come from validated clip gate."""
    source, outdir = Path(source), Path(output_dir)
    if not source.is_file() or source.is_symlink():
        raise ValueError("source must be a regular local file")
    if not isinstance(plan, dict) or plan.get("strategic_verdict_allowed") is not False:
        raise ValueError("plan must forbid strategic verdicts")
    expected = plan.get("source_sha256")
    if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("invalid source hash")
    if sha256_file(source) != expected:
        raise ValueError("source SHA-256 mismatch")
    name = plan.get("output_name")
    if not isinstance(name, str) or not name.endswith(".mp4") or name in (".mp4", "..mp4") or Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("unsafe output filename")
    start, end = plan.get("start_seconds"), plan.get("end_seconds")
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in (start, end)) or not 0 <= start < end:
        raise ValueError("invalid clip interval")
    duration = probe_duration(source)
    if end > duration + 0.02:
        raise ValueError("clip exceeds measured duration")
    if type(plan.get("duration_seconds")) not in (int, float) or abs(plan["duration_seconds"] - (end - start)) > 1e-6:
        raise ValueError("plan duration mismatch")
    if plan.get("review_status") not in ("confirmed", "insufficient_data"):
        raise ValueError("invalid review status")
    outdir.mkdir(parents=True, exist_ok=True)
    target, sidecar = outdir / name, outdir / (name + ".json")
    if target.exists() or sidecar.exists() or target.is_symlink() or sidecar.is_symlink():
        raise FileExistsError("output already exists")
    partial = outdir / (name + ".partial.mp4")
    if partial.exists() or partial.is_symlink():
        raise FileExistsError("partial output exists")
    try:
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-ss", str(start), "-i", str(source), "-t", str(end - start), "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "aac", "-movflags", "+faststart", "-y", str(partial)], check=True, capture_output=True, text=True, timeout=timeout)
        actual = probe_duration(partial)
        if abs(actual - (end - start)) > .25:
            raise ValueError("exported clip duration outside tolerance")
        metadata = {"schema_version": 1, "source_sha256": expected, "clip_sha256": sha256_file(partial), "table_id": plan.get("table_id"), "hand_id": plan.get("hand_id"), "start_seconds": start, "end_seconds": end, "actual_clip_duration_seconds": actual, "review_status": plan["review_status"], "annotation": "INSUFFICIENT_DATA" if plan["review_status"] == "insufficient_data" else "CONDITIONAL MODEL ONLY", "strategic_verdict_allowed": False, "method": "ffmpeg reencode; timestamps approximate within codec tolerance"}
        created = False
        try:
            partial.rename(target)
            created = True
            sidecar.write_text(json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        except Exception:
            if created:
                target.unlink(missing_ok=True)
            raise
        return metadata
    finally:
        partial.unlink(missing_ok=True)
