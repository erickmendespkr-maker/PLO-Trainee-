"""Bounded repeated synthetic FFmpeg benchmark matrix for offline extraction.

Reports medians and spread for complete decode vs indexed seeks (including
FFprobe). No performance guarantee or strategy selection for real poker video.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics

from offline_ffmpeg_extraction_benchmark import benchmark, require


def spaced_indices(seconds: int, fps: int, count: int) -> tuple[int, ...]:
    total = seconds * fps
    require(type(count) is int and 1 <= count <= min(12, total), "Invalid frame count")
    # Avoid only requesting the first/last frame; distribute interior points.
    indices = tuple((k * (total - 1)) // (count + 1) for k in range(1, count + 1))
    require(len(set(indices)) == count, "Repeated frame index")
    return indices


def matrix(*, durations: tuple[int, ...] = (6, 12), fps: int = 10,
           counts: tuple[int, ...] = (1, 5), gops: tuple[int, ...] = (10, 60),
           repeats: int = 2) -> dict:
    require(type(durations) is tuple and 1 <= len(durations) <= 3 and
            len(set(durations)) == len(durations) and
            all(type(s) is int and 2 <= s <= 90 for s in durations),
            "Invalid durations")
    require(type(counts) is tuple and 1 <= len(counts) <= 3 and
            len(set(counts)) == len(counts) and
            all(type(c) is int and 1 <= c <= 12 for c in counts),
            "Invalid counts")
    require(type(gops) is tuple and 1 <= len(gops) <= 3 and
            len(set(gops)) == len(gops) and
            all(type(g) is int and 2 <= g <= 300 for g in gops),
            "Invalid GOPs")
    require(type(fps) is int and 2 <= fps <= 30, "Invalid FPS")
    require(type(repeats) is int and 2 <= repeats <= 4, "At least 2 repeats required")
    require(len(durations) * len(counts) * len(gops) * repeats <= 36,
            "Too many benchmark runs")
    rows = []
    version = None
    for seconds in durations:
        for count in counts:
            indices = spaced_indices(seconds, fps, count)
            for gop in gops:
                full, indexed, fallbacks = [], [], []
                for _ in range(repeats):
                    run = benchmark(seconds=seconds, fps=fps, gops=(gop,), indices=indices)
                    item = run["runs"][0]
                    require(item["exact_png_and_pts_match"], "Frame mismatch in matrix")
                    full.append(item["full_decode_seconds"])
                    indexed.append(item["indexed_seek_including_probe_seconds"])
                    fallbacks.append(item["full_decode_fallbacks"])
                    version = run["ffmpeg_version"]
                f_med, i_med = statistics.median(full), statistics.median(indexed)
                rows.append({
                    "seconds": seconds, "fps": fps, "gop": gop,
                    "requested_frames": count, "indices": list(indices),
                    "full_decode_seconds_runs": full,
                    "indexed_seek_including_probe_seconds_runs": indexed,
                    "fallback_counts": fallbacks,
                    "full_decode_median_seconds": round(f_med, 6),
                    "indexed_seek_median_seconds": round(i_med, 6),
                    "indexed_over_full_median_ratio": round(i_med / max(f_med, 1e-9), 4),
                    "faster_in_this_synthetic_sample": "full_decode" if f_med < i_med else
                        "indexed_seek" if i_med < f_med else "tie",
                    "exact_png_and_pts_match_in_all_runs": True,
                })
    return {
        "schema_version": 1, "status": "synthetic_repeated_benchmark_only",
        "ffmpeg_version": version, "repeats_per_configuration": repeats,
        "runs_count": len(rows) * repeats, "configurations": rows,
        "real_session_performance_verified": False,
        "automatic_strategy_selection_authorized": False,
        "ocr_verified": False, "equity_ev_authorized": False,
        "limitations": [
            "Medians of bounded repeated runs are not confidence intervals or guarantees.",
            "Synthetic MPEG-4 at 160x120 is not representative of real four-table sessions.",
            "Benchmark includes FFprobe indexing and fallback overhead, but not video upload or OCR.",
            "Host load and process startup can dominate short-video timing.",
            "No extraction strategy is automatically selected from these observations.",
        ],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("new_report_json")
    p.add_argument("--durations", default="6,12")
    p.add_argument("--fps", type=int, default=10)
    p.add_argument("--counts", default="1,5")
    p.add_argument("--gops", default="10,60")
    p.add_argument("--repeats", type=int, default=2)
    args = p.parse_args(argv)
    target = Path(args.new_report_json)
    require(target.suffix.lower() == ".json" and target.parent.is_dir() and
            not target.parent.is_symlink() and not target.exists() and
            not target.is_symlink(), "Output must be a new JSON file")
    try:
        durations = tuple(int(x) for x in args.durations.split(","))
        counts = tuple(int(x) for x in args.counts.split(","))
        gops = tuple(int(x) for x in args.gops.split(","))
    except ValueError as exc:
        raise ValueError("Durations, counts and GOPs must be integers") from exc
    result = matrix(durations=durations, fps=args.fps, counts=counts,
                    gops=gops, repeats=args.repeats)
    with target.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"configurations": len(result["configurations"]),
                      "runs": result["runs_count"], "synthetic_only": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
