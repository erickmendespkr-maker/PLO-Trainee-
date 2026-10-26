"""Reproducible *synthetic-only* benchmark for two offline frame extractors.

Measures complete one-pass decode vs FFprobe full-frame indexing + separate
FFmpeg seeks, including indexing overhead. Never processes user video, uploads,
network services, live poker, or claims production performance from this test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from offline_ffmpeg_batch_frame_provenance import _video_frames
from offline_ffmpeg_seek_frame_provenance import seek_video_frames


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(argv: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=True, timeout=timeout)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Synthetic FFmpeg benchmark failed: {type(exc).__name__}") from exc


def _synthetic(path: Path, seconds: int, fps: int, gop: int) -> None:
    command(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-f", "lavfi",
             "-i", f"testsrc2=size=160x120:rate={fps}:duration={seconds}",
             "-an", "-c:v", "mpeg4", "-g", str(gop), "-bf", "2", "-q:v", "3",
             "-f", "mp4", str(path)], 120)
    require(path.is_file() and 0 < path.stat().st_size <= 128 * 1024 * 1024,
            "Invalid generated fixture")


def benchmark(*, seconds: int = 12, fps: int = 10,
              gops: tuple[int, ...] = (10, 60),
              indices: tuple[int, ...] = (5, 60, 110)) -> dict:
    require(type(seconds) is int and 2 <= seconds <= 90, "Seconds must be 2–90")
    require(type(fps) is int and 2 <= fps <= 30, "FPS must be 2–30")
    require(type(gops) is tuple and 1 <= len(gops) <= 3 and
            len(set(gops)) == len(gops) and
            all(type(g) is int and 2 <= g <= 300 for g in gops), "Invalid GOP values")
    require(type(indices) is tuple and 1 <= len(indices) <= 12 and
            all(type(i) is int and 0 <= i < seconds * fps for i in indices) and
            tuple(sorted(set(indices))) == indices, "Invalid frame indices")
    require(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    version = command(["ffmpeg", "-version"], 10).stdout.decode("utf-8", "replace").splitlines()[0]
    result = {"schema_version": 1, "status": "synthetic_performance_only",
              "fixture": {"seconds": seconds, "fps": fps, "gops": list(gops),
                          "indices": list(indices), "resolution": [160, 120],
                          "codec": "mpeg4", "b_frames": 2},
              "ffmpeg_version": version, "runs": [],
              "real_session_performance_verified": False,
              "ocr_verified": False, "equity_ev_authorized": False,
              "limitations": [
                  "Wall-clock timings are environment-specific, single-run, and include process startup.",
                  "Indexed seek includes a full FFprobe frame-index scan before individual seeks.",
                  "Synthetic 160x120 MPEG-4 is not representative of hour-long multi-table recordings.",
                  "Only decoded PTS and PNG bytes are compared; no OCR or poker hand analysis.",
              ]}
    with tempfile.TemporaryDirectory(prefix="plo_synthetic_bench_") as td:
        root = Path(td)
        for gop in gops:
            video = root / f"synthetic_gop_{gop}.mp4"
            _synthetic(video, seconds, fps, gop)
            full_dir, seek_dir = root / f"full_{gop}", root / f"seek_{gop}"
            full_dir.mkdir(); seek_dir.mkdir()
            before = sha(video)
            t0 = time.perf_counter()
            full = _video_frames(video, list(indices), full_dir, float(seconds))
            full_elapsed = time.perf_counter() - t0
            t1 = time.perf_counter()
            diagnostics = {}
            sought = seek_video_frames(video, list(indices), seek_dir, float(seconds),
                                      diagnostics=diagnostics)
            seek_elapsed = time.perf_counter() - t1
            require(sha(video) == before, "Fixture changed while benchmarking")
            matches = []
            for index in indices:
                full_png, full_pts = full[index]
                seek_png, seek_pts = sought[index]
                require(abs(full_pts - seek_pts) <= 0.001,
                        "Extraction strategies returned different frame timestamps")
                require(sha(full_png) == sha(seek_png),
                        "Extraction strategies returned different decoded frame PNGs")
                matches.append({"index": index, "pts_seconds": full_pts,
                                "png_sha256": sha(full_png)})
            result["runs"].append({"gop": gop, "video_sha256": before,
                                   "full_decode_seconds": round(full_elapsed, 6),
                                   "indexed_seek_including_probe_seconds": round(seek_elapsed, 6),
                                   "indexed_to_full_time_ratio": round(seek_elapsed / max(full_elapsed, 1e-9), 4),
                                   "full_decode_fallbacks": diagnostics["full_decode_fallbacks"],
                                   "exact_png_and_pts_match": True, "frames": matches})
    return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("new_report_json")
    p.add_argument("--seconds", type=int, default=12)
    p.add_argument("--fps", type=int, default=10)
    p.add_argument("--gops", default="10,60")
    p.add_argument("--indices", default="5,60,110")
    a = p.parse_args(argv)
    target = Path(a.new_report_json)
    require(target.suffix.lower() == ".json" and target.parent.is_dir() and
            not target.parent.is_symlink() and not target.exists() and
            not target.is_symlink(), "Output must be a new JSON file")
    try:
        gops = tuple(int(s) for s in a.gops.split(","))
        indices = tuple(int(s) for s in a.indices.split(","))
    except ValueError as exc:
        raise ValueError("GOP and index values must be integers") from exc
    data = benchmark(seconds=a.seconds, fps=a.fps, gops=gops, indices=indices)
    with target.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"runs": len(data["runs"]), "synthetic_only": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
