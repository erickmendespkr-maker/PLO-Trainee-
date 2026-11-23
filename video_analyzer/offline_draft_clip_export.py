"""Export unverified MP4 draft windows with FFmpeg and explicit audit metadata."""
import hashlib
import json
import math
import subprocess
from pathlib import Path


def export_draft_clips(plan, source, output_dir, *, ffmpeg="ffmpeg", ffprobe="ffprobe"):
    if not isinstance(plan, dict) or not isinstance(plan.get("clips"), list) or plan.get("exported") is not False:
        raise ValueError("expected unexported draft plan")
    digest = plan.get("source_video_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("invalid source digest")
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(source)
    h = hashlib.sha256()
    with source.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != digest:
        raise ValueError("source digest mismatch")
    probe = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(source)], check=True, capture_output=True, text=True)
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    planned = plan.get("video_duration_s")
    if isinstance(planned, bool) or not isinstance(planned, (int, float)) or not math.isfinite(planned) or abs(duration - planned) > 0.5:
        raise ValueError("plan duration differs from source")
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    for i, clip in enumerate(plan["clips"]):
        if not isinstance(clip, dict) or clip.get("status") != "DRAFT_REVIEW_ONLY":
            reports.append({"hand_index": clip.get("hand_index", i) if isinstance(clip, dict) else i, "status": "SKIPPED_REVIEW_REQUIRED"})
            continue
        start, end = clip.get("start_s"), clip.get("end_s")
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in (start, end)) or start < 0 or end <= start or end > duration + 0.01:
            reports.append({"hand_index": clip.get("hand_index", i), "status": "SKIPPED_INVALID_INTERVAL"})
            continue
        target = output / f"draft_hand_{i:04d}.mp4"
        try:
            subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-n", "-ss", str(start), "-i", str(source), "-t", str(end - start), "-map", "0:v:0", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(target)], check=True, capture_output=True, text=True)
            check = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(target)], check=True, capture_output=True, text=True)
            actual = float(json.loads(check.stdout)["format"]["duration"])
            if not target.is_file() or target.stat().st_size == 0 or not math.isfinite(actual) or abs(actual - (end - start)) > 0.5:
                raise ValueError("clip duration/size verification failed")
            reports.append({"hand_index": clip.get("hand_index", i), "table_id": clip.get("table_id"), "timeline_issue_codes": clip.get("timeline_issue_codes", []), "draft_reason": clip.get("reason"), "status": "EXPORTED_UNVERIFIED_DRAFT", "filename": target.name, "duration_s": actual, "source_start_s": start, "source_end_s": end, "visual_review_required": True, "strategic_analysis_verified": False})
        except (subprocess.CalledProcessError, ValueError) as exc:
            target.unlink(missing_ok=True)
            reports.append({"hand_index": clip.get("hand_index", i), "status": "EXPORT_FAILED", "reason": type(exc).__name__})
    report = {"schema_version": 1, "source_video_sha256": digest, "visual_accuracy_verified": False, "strategic_analysis_verified": False, "clips": reports}
    (output / "draft_export_manifest.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report
