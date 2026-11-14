"""Offline crop evidence report: sample decoded RGB hashes, not poker observations."""
import hashlib
import json
import math
import subprocess
from pathlib import Path

def collect_crop_frame_evidence(directory, *, max_samples=5):
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("regular directory required")
    if type(max_samples) is not int or not 1 <= max_samples <= 12:
        raise ValueError("invalid sample count")
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("regular manifest required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "UNREVIEWED_TABLE_CROPS" or manifest.get("poker_analysis_verified") is not False:
        raise ValueError("unreviewed manifest required")
    tables = manifest.get("tables")
    if not isinstance(tables, list) or not 1 <= len(tables) <= 4:
        raise ValueError("expected 1-4 tables")
    result = []
    seen = set()
    for table in tables:
        if not isinstance(table, dict) or table.get("verified_by_human") is not False or table.get("hand_reconstructed") is not False:
            raise ValueError("unsupported verification claim")
        table_id = table.get("table_id")
        if type(table_id) is not int or table_id not in range(1, 5) or table_id in seen:
            raise ValueError("invalid table id")
        seen.add(table_id)
        if table.get("file") != f"table_{table_id}.mkv":
            raise ValueError("unexpected filename")
        path = directory / table["file"]
        if path.is_symlink() or not path.is_file():
            raise ValueError("regular crop required")
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height:frame=best_effort_timestamp_time",
            "-show_frames", "-of", "json", str(path)], capture_output=True, check=True, timeout=90)
        data = json.loads(probe.stdout)
        streams, frames = data.get("streams", []), data.get("frames", [])
        if len(streams) != 1 or not 1 <= len(frames) <= 20000:
            raise ValueError("invalid video frames")
        w, h = streams[0]["width"], streams[0]["height"]
        if not 2 <= w <= 4096 or not 2 <= h <= 4096:
            raise ValueError("invalid dimensions")
        pts = [float(frame["best_effort_timestamp_time"]) for frame in frames]
        if any(not math.isfinite(t) for t in pts) or any(b <= a for a, b in zip(pts, pts[1:])):
            raise ValueError("invalid PTS")
        n = min(max_samples, len(frames))
        indices = sorted({i * (len(frames)-1) // (n-1) for i in range(n)}) if n > 1 else [0]
        samples = []
        for index in indices:
            rgb = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                "-i", str(path), "-vf", f"select=eq(n\\,{index})", "-frames:v", "1",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                capture_output=True, check=True, timeout=120).stdout
            if len(rgb) != w*h*3:
                raise ValueError("frame decode mismatch")
            samples.append({"frame_index": index, "crop_pts_seconds": pts[index],
                            "rgb_sha256": hashlib.sha256(rgb).hexdigest()})
        result.append({"table_id": table_id, "decoded_frame_count": len(frames),
                       "samples": samples, "status": "UNREVIEWED_FRAME_EVIDENCE"})
    return {"status": "TECHNICAL_FRAME_EVIDENCE_ONLY", "tables": result,
            "source_absolute_pts_verified": False, "ocr_verified": False,
            "hands_verified": False, "equity_ev_verified": False}
