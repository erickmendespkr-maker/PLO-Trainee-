"""Conservative offline review -> Monte Carlo -> conditional EV -> approved MP4.

Only explicitly reviewed, recorded PLO5/PLO6 hands are accepted. A successful
run establishes *file and model consistency*, not OCR/video-action accuracy or
strategic correctness. No live poker integration, betting, or auto-selection.

A new output directory is created only after all required stages finish; a
blocked stage publishes an audit report without claiming a computed result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from offline_review_queue_math_handoff import export as handoff_export

NAME = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
FILES = ("handoff.json", "candidate.json", "math.json", "clip.mp4",
         "clip.json", "clip.srt")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _bridge_export(candidate, output):
    # Import lazily so a blocked hand never initializes the Monte Carlo engine.
    from offline_reviewed_range_equity_bridge import export
    return export(candidate, output)


def _clip_export(video, handoff, candidate, math, annotation, stem):
    from offline_reviewed_math_clip_export import export
    return export(video, handoff, candidate, math, annotation, stem)


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _stage_input(source, target, limit=2 * 1024 * 1024):
    """Snapshot exact input bytes without following symlinks or trusting file size."""
    fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit,
                "Invalid input file size or type")
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        require(len(raw) == before.st_size and
                (before.st_ino, before.st_mtime_ns, before.st_size) ==
                (after.st_ino, after.st_mtime_ns, after.st_size),
                "Input changed during snapshot")
    with target.open("xb") as output:
        output.write(raw)
    return hashlib.sha256(raw).hexdigest()


def _publish(stage, destination, summary):
    """Create-only hardlinks, rolling back only links created by this call."""
    paths = sorted(p for p in stage.iterdir() if p.is_file())
    summary["files"] = {p.name: {"sha256": _sha(p), "bytes": p.stat().st_size}
                        for p in paths}
    manifest = stage / "pipeline.json"
    manifest.write_text(json.dumps(summary, ensure_ascii=False, allow_nan=False,
                                   sort_keys=True, indent=2) + "\n", encoding="utf-8")
    paths.append(manifest)
    destination.mkdir(mode=0o700, exist_ok=False)
    linked = []
    try:
        for source in paths:
            target = destination / source.name
            os.link(source, target, follow_symlinks=False)
            linked.append(target)
    except BaseException:
        for target in reversed(linked):
            target.unlink(missing_ok=True)
        try:
            destination.rmdir()
        except OSError:
            pass  # Do not delete files created by another process.
        raise


def run(recording, reviewed_queue_input, manual_clip_annotation, new_output_dir):
    """Execute existing validated modules; do not modify input files.

    A blocked handoff or math report produces a *blocked* audit directory.
    Clip export requires explicitly approved timestamps and successful math.
    """
    video = Path(recording)
    queue = Path(reviewed_queue_input)
    annotation = Path(manual_clip_annotation)
    destination = Path(new_output_dir)
    require(NAME.fullmatch(destination.name) is not None and
            destination.parent.is_dir() and not destination.parent.is_symlink() and
            not destination.exists() and not destination.is_symlink(),
            "Output must be a new safe directory")
    require(video.is_file() and not video.is_symlink() and
            video.suffix.lower() in (".mp4", ".webm") and
            not video.parent.is_symlink(), "Unsafe recording")
    require(queue.is_file() and not queue.is_symlink() and
            not queue.parent.is_symlink(), "Unsafe review input")
    require(annotation.is_file() and not annotation.is_symlink() and
            not annotation.parent.is_symlink(), "Unsafe clip annotation")
    summary = {
        "schema_version": 1,
        "status": "not_started",
        "monte_carlo_recomputed": False,
        "clip_exported": False,
        "video_evidence_verified": False,
        "ocr_accuracy_verified": False,
        "opponent_range_verified": False,
        "strategic_error_proven": False,
        "automatic_clip_selection_authorized": False,
        "blocked_reasons": [],
        "limitations": [
            "Review, visible cards, ranges and timestamps remain declared, not OCR-verified.",
            "Monte Carlo uncertainty excludes opponent-range and annotation uncertainty.",
            "EV is heads-up call versus fold, without future betting or side pots.",
            "No strategic error is proven; clip export requires manual approval.",
        ],
    }
    with tempfile.TemporaryDirectory(prefix=".plo_pipeline_", dir=destination.parent) as tmp:
        stage = Path(tmp)
        queue_snapshot = stage / "review_input.json"
        annotation_snapshot = stage / "annotation_input.json"
        summary["review_input_sha256"] = _stage_input(queue, queue_snapshot)
        summary["annotation_input_sha256"] = _stage_input(annotation, annotation_snapshot)
        handoff_path = stage / "handoff.json"
        candidate_path = stage / "candidate.json"
        math_path = stage / "math.json"
        handoff = handoff_export(queue_snapshot, handoff_path, candidate_path)
        summary["table_id"] = handoff["table_id"]
        summary["hand_label"] = handoff["hand_label"]
        summary["variant"] = handoff["variant"]
        summary["handoff_status"] = handoff["status"]
        if handoff["blocked_reasons"]:
            summary["status"] = "blocked_review"
            summary["blocked_reasons"] = handoff["blocked_reasons"]
        else:
            require(candidate_path.is_file(), "Handoff candidate missing")
            math = _bridge_export(candidate_path, math_path)
            require(math_path.is_file() and type(math) is dict and
                    type(math.get("monte_carlo_recomputed")) is bool,
                    "Invalid Monte Carlo report")
            summary["monte_carlo_recomputed"] = math["monte_carlo_recomputed"]
            if math.get("blocked_reasons") or not math["monte_carlo_recomputed"]:
                summary["status"] = "blocked_math"
                summary["blocked_reasons"] = math.get("blocked_reasons") or ["math_not_recomputed"]
            else:
                clip = _clip_export(video, handoff_path, candidate_path, math_path,
                                    annotation_snapshot, stage / "clip")
                require((stage / "clip.mp4").is_file() and
                        (stage / "clip.json").is_file() and
                        (stage / "clip.srt").is_file(), "Clip output incomplete")
                require(clip.get("clip_sha256") == _sha(stage / "clip.mp4") and
                        clip.get("clip_explanation_is_conditional") is True,
                        "Clip provenance mismatch")
                summary["status"] = "offline_conditional_math_and_approved_clip_exported"
                summary["clip_exported"] = True
                summary["clip_sha256"] = clip["clip_sha256"]
                summary["source_recording_sha256_verified_bytes"] = clip[
                    "source_recording_sha256_verified_bytes"]
        _publish(stage, destination, summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording")
    parser.add_argument("reviewed_queue_input_json")
    parser.add_argument("manual_clip_annotation_json")
    parser.add_argument("new_output_directory")
    args = parser.parse_args(argv)
    result = run(args.recording, args.reviewed_queue_input_json,
                 args.manual_clip_annotation_json, args.new_output_directory)
    print(json.dumps({"status": result["status"],
                      "blocked_reasons": result["blocked_reasons"],
                      "clip_exported": result["clip_exported"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
