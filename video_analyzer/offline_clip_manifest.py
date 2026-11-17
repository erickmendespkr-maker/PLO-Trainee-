"""Conservative, offline FFmpeg clip manifest; proposals are never confirmed hands."""
import hashlib
import json
import math

def _num(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + " must be finite")
    return float(value)

def build_clip_manifest(video_sha256, duration_seconds, proposals, padding_seconds=2.0, max_tables=4):
    def digest(value):
        return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    if not digest(video_sha256):
        raise ValueError("invalid video SHA256")
    duration, padding = _num(duration_seconds, "duration"), _num(padding_seconds, "padding")
    if duration <= 0 or padding < 0 or type(max_tables) is not int or not 1 <= max_tables <= 4:
        raise ValueError("invalid duration, padding or table limit")
    if not isinstance(proposals, list):
        raise ValueError("proposals must be list")
    clips = []
    for p in proposals:
        if not isinstance(p, dict) or type(p.get("table_id")) is not int or not 1 <= p["table_id"] <= max_tables:
            raise ValueError("invalid table")
        start, end = _num(p.get("start_seconds"), "start"), _num(p.get("end_seconds"), "end")
        if not 0 <= start < end <= duration or not digest(p.get("evidence_sha256")):
            raise ValueError("invalid interval or evidence digest")
        key = f'{video_sha256}:{p["table_id"]}:{start:.6f}:{end:.6f}:{p["evidence_sha256"]}'
        clips.append({"clip_id": hashlib.sha256(key.encode()).hexdigest()[:24],
                      "table_id": p["table_id"], "start_seconds": max(0.0, start-padding),
                      "end_seconds": min(duration, end+padding),
                      "source_interval": [start, end], "evidence_sha256": p["evidence_sha256"],
                      "review_status": "pending_human_review",
                      "strategic_analysis_status": "insufficient_verified_evidence",
                      "label": "CANDIDATE ONLY - NOT A CONFIRMED HAND"})
    clips.sort(key=lambda c: (c["start_seconds"], c["table_id"], c["clip_id"]))
    if len({c["clip_id"] for c in clips}) != len(clips):
        raise ValueError("duplicate candidate")
    return {"schema_version": 1, "video_sha256": video_sha256,
            "duration_seconds": duration, "status": "review_required", "clips": clips}

def ffmpeg_clip_arguments(input_path, output_path, clip):
    """Argument vector only: caller must invoke subprocess without shell=True."""
    if not isinstance(clip, dict) or clip.get("review_status") != "pending_human_review":
        raise ValueError("clip requires review")
    start, end = _num(clip.get("start_seconds"), "start"), _num(clip.get("end_seconds"), "end")
    if not 0 <= start < end or not str(input_path) or not str(output_path):
        raise ValueError("invalid clip")
    return ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-ss", f"{start:.6f}",
            "-i", str(input_path), "-t", f"{end-start:.6f}", "-map", "0:v:0",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags",
            "+faststart", str(output_path)]

def manifest_json(manifest):
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
