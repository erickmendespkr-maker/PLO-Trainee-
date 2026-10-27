"""Offline, explicitly approved PLO5/PLO6 MP4 clip with embedded explanatory subtitles.

Binds a reviewed handoff, exact Monte Carlo input bytes, math report and local
recording hash. Timestamps and ranges are *declared*, never inferred from video.
No live integration, automatic clip selection or claim of strategic certainty.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

MAX_JSON = 2 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{64}\Z")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and not path.parent.is_symlink(), "Unsafe JSON path")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as f:
        s = os.fstat(f.fileno())
        require(stat.S_ISREG(s.st_mode) and 0 < s.st_size <= MAX_JSON, "Invalid JSON size")
        raw = f.read(MAX_JSON + 1)
        require(0 < len(raw) <= MAX_JSON and os.fstat(f.fileno()).st_size == s.st_size,
                "JSON changed or too large")
    def pairs(values):
        out = {}
        for k, v in values:
            require(k not in out, "Duplicate JSON key")
            out[k] = v
        return out
    def nonfinite(value):
        raise ValueError("Nonfinite JSON number")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                      parse_constant=nonfinite), digest(raw)


def finite(value, name):
    require(type(value) in (int, float) and math.isfinite(value), "Invalid " + name)
    return float(value)


def sha_claim(value):
    require(type(value) is str and SHA.fullmatch(value), "Invalid SHA256 claim")
    return value


def source_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def probe(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration:stream=codec_type,codec_name", "-of", "json", str(path)],
                       capture_output=True, text=True, timeout=30, check=True)
    data = json.loads(p.stdout)
    duration = finite(float(data["format"]["duration"]), "duration")
    require(0 < duration <= 3900 and any(s.get("codec_type") == "video"
                                          for s in data.get("streams", [])), "Invalid source video")
    return duration, data


def inspect(handoff, candidate, candidate_hash, math_report, annotation,
            recording_hash, duration):
    require(handoff.get("schema_version") == 1 and
            handoff.get("status") == "handoff_candidate_requires_bridge_validation" and
            handoff.get("blocked_reasons") == [] and
            handoff.get("monte_carlo_executed") is False and
            handoff.get("video_evidence_verified") is False, "Unapproved handoff")
    require(candidate.get("schema_version") == 1 and
            candidate.get("review_gate", {}).get("status") in
            ("synthetic_fixture", "human_confirmed_claim"), "Unreviewed candidate")
    hand = candidate.get("reviewed_hand", {})
    gate = candidate["review_gate"]
    require(math_report.get("schema_version") == 1 and
            math_report.get("status") == "offline_conditional_math_from_declared_review_and_range" and
            math_report.get("blocked_reasons") == [] and
            math_report.get("monte_carlo_recomputed") is True and
            math_report.get("video_evidence_verified") is False and
            math_report.get("strategic_error_proven") is False and
            math_report.get("automatic_clip_selection_authorized") is False and
            math_report.get("input_sha256") == candidate_hash,
            "Math report not bound to exact candidate bytes")
    variant, table, label = hand.get("variant"), hand.get("table_id"), hand.get("hand_label")
    require(variant in ("PLO5", "PLO6") and type(table) is int and 1 <= table <= 4 and
            type(label) is str and 0 < len(label) <= 64, "Invalid hand identity")
    require(all(handoff.get(k) == v for k, v in
                (("variant", variant), ("table_id", table), ("hand_label", label))) and
            all(math_report.get(k) == v for k, v in
                (("variant", variant), ("table_id", table), ("hand_label", label))),
            "Hand identity mismatch")
    require(all(sha_claim(x) == recording_hash for x in
                (handoff.get("source_recording_sha256_claim_unverified"),
                 hand.get("source_recording_sha256_claim"),
                 math_report.get("recording_sha256_claim_unverified"))),
            "Recording hash mismatch")
    require(math_report.get("review_gate_claim") == gate and
            handoff.get("events_reviewed_claim") == handoff.get("events_total") and
            handoff.get("events_total", 0) >= 0, "Review provenance mismatch")
    entries = candidate.get("weighted_range")
    require(type(entries) is list and entries, "Missing declared range")
    range_bytes = json.dumps(entries, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()
    mc = candidate.get("monte_carlo", {})
    trials, seed = mc.get("trials"), mc.get("seed")
    require(math_report.get("range_sha256") == digest(range_bytes) and
            type(trials) is int and 100 <= trials <= 50000 and
            type(seed) is int and 0 <= seed < 2**64 and
            math_report.get("trials_requested") == trials and
            math_report.get("seed") == seed and
            math_report.get("range_combos_supplied") == len(entries),
            "Monte Carlo input mismatch")
    wins, ties, losses = (math_report.get(x) for x in ("wins", "ties", "losses"))
    require(all(type(x) is int and x >= 0 for x in (wins, ties, losses)) and
            wins + ties + losses == trials, "Invalid Monte Carlo outcome counts")
    eq = finite(math_report.get("equity"), "equity")
    # Monte Carlo equity is determined by its integer outcomes, not by a
    # separately editable decimal in the report. This is a consistency check,
    # not an independent recomputation of the underlying poker simulation.
    require(0 <= eq <= 1 and
            abs(eq - (wins + 0.5 * ties) / trials) <= 1e-10,
            "Equity inconsistent with Monte Carlo outcome counts")
    bounds = math_report.get("equity_ci95_hoeffding")
    require(type(bounds) is list and len(bounds) == 2, "Missing equity interval")
    lo, hi = [finite(x, "equity bound") for x in bounds]
    require(0 <= lo <= eq <= hi <= 1, "Invalid equity interval")
    decision = hand.get("decision", {})
    require(decision.get("action") == "call" and
            decision.get("no_future_betting") is True and
            decision.get("no_side_pots") is True, "Unsupported EV decision")
    pot, cost, rake = (finite(decision.get(x), x) for x in
                       ("pot_before_call", "call_cost", "expected_rake"))
    require(pot > 0 and cost > 0 and 0 <= rake <= pot + cost, "Invalid pot/cost/rake")
    ev = lambda e: e * (pot + cost) - cost - rake
    require(abs(finite(math_report.get("ev_call_chips"), "EV") - ev(eq)) < 1e-5 and
            math_report.get("ev_fold_chips") == 0 and
            type(math_report.get("ev_call_interval_chips")) is list and
            len(math_report["ev_call_interval_chips"]) == 2 and
            all(abs(finite(a, "EV interval") - ev(b)) < 1e-5 for a, b in
                zip(math_report["ev_call_interval_chips"], (lo, hi))),
            "Inconsistent EV values")
    require(type(annotation) is dict and set(annotation) ==
            {"schema_version", "source_kind", "table_id", "hand_label", "reviewer_label",
             "start_seconds", "decision_seconds", "end_seconds", "approved_for_export", "notes"},
            "Invalid manual clip annotation")
    require(annotation["schema_version"] == 1 and annotation["approved_for_export"] is True and
            annotation["source_kind"] == gate["status"] and
            annotation["reviewer_label"] == gate["reviewer_label"] and
            type(annotation["table_id"]) is int and annotation["table_id"] == table and
            annotation["hand_label"] == label, "Clip not explicitly approved for same hand")
    require(type(annotation["notes"]) is str and len(annotation["notes"]) <= 300 and
            all(ord(c) >= 32 for c in annotation["notes"]), "Invalid notes")
    start, moment, end = (finite(annotation[k], k) for k in
                          ("start_seconds", "decision_seconds", "end_seconds"))
    require(0 <= start <= moment <= end <= duration + 0.002 and
            1 <= end - start <= 180, "Invalid manual clip time window")
    return {"schema_version": 1, "status": "offline_manually_approved_clip_not_video_content_verified",
            "variant": variant, "table_id": table, "hand_label": label,
            "source_recording_sha256_verified_bytes": recording_hash,
            "bridge_input_sha256_verified_bytes": candidate_hash,
            "handoff_queue_sha256_claim": handoff.get("queue_canonical_sha256"),
            "review_source_claim": gate["status"], "reviewer_label": gate["reviewer_label"],
            "start_seconds": start, "decision_seconds": moment, "end_seconds": end,
            "equity": eq, "equity_ci95_hoeffding": [lo, hi],
            "ev_call_chips": math_report["ev_call_chips"],
            "ev_call_interval_chips": math_report["ev_call_interval_chips"],
            "pot_before_call": pot, "call_cost": cost, "expected_rake": rake,
            "trials": trials, "seed": seed, "range_sha256": math_report["range_sha256"],
            "range_label_claim": math_report.get("range_label_claim"),
            "notes": annotation["notes"],
            "limitations": ["Timestamps, cards, review and opponent range are declared, not visually verified.",
                            "Monte Carlo result is bound to its input report, not independently recomputed here.",
                            "Hoeffding interval measures Monte Carlo sampling uncertainty only.",
                            "Conditional heads-up call versus fold, no future betting or side pots.",
                            "This clip does not establish a strategic error or select hands automatically."]}


def subtitle(report, length):
    # SRT is also muxed as mov_text inside MP4; avoid markup or user-controlled newlines.
    title = f"{report['variant']} mesa {report['table_id']} | call: pote {report['pot_before_call']:g}, custo {report['call_cost']:g}"
    line = (f"Equity {100*report['equity']:.1f}% (IC amostral {100*report['equity_ci95_hoeffding'][0]:.1f}–"
            f"{100*report['equity_ci95_hoeffding'][1]:.1f}%) | EV {report['ev_call_chips']:+.2f} fichas")
    caution = "Range hipotético; OCR/cartas não verificados. Não comprova erro."
    def clock(t):
        ms = int(round(t * 1000))
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, ms = divmod(rem, 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"
    chunks = ([(0, length, title + "\n" + line + "\n" + caution)] if length < 12 else
              [(0, 5, title), (5, 11, line), (11, length, caution)])
    return "\n".join(f"{i}\n{clock(a)} --> {clock(b)}\n{text}\n" for i, (a, b, text)
                     in enumerate((x for x in chunks if x[1] - x[0] > .05), 1))


def export(recording, handoff_path, candidate_path, math_path, annotation_path, output_stem):
    video, stem = Path(recording), Path(output_stem)
    require(video.is_file() and not video.is_symlink() and not video.parent.is_symlink() and
            video.suffix.lower() in (".mp4", ".webm") and
            0 < video.stat().st_size <= 10 * 1024**3, "Unsafe recording")
    require(stem.parent.is_dir() and not stem.parent.is_symlink() and
            re.fullmatch(r"[A-Za-z0-9_-]{1,80}", stem.name), "Unsafe output stem")
    outputs = [stem.with_suffix(ext) for ext in (".mp4", ".json", ".srt")]
    require(all(not p.exists() and not p.is_symlink() for p in outputs) and
            video not in outputs, "Output exists")
    handoff, _ = read_json(handoff_path)
    candidate, candidate_hash = read_json(candidate_path)
    math_report, _ = read_json(math_path)
    annotation, _ = read_json(annotation_path)
    video_hash = source_sha(video)
    duration, _ = probe(video)
    report = inspect(handoff, candidate, candidate_hash, math_report, annotation, video_hash, duration)
    length = report["end_seconds"] - report["start_seconds"]
    with tempfile.TemporaryDirectory(prefix=".plo_clip_", dir=stem.parent) as tmp:
        tmp = Path(tmp)
        srt = tmp / "clip.srt"
        srt.write_text(subtitle(report, length), encoding="utf-8")
        mp4 = tmp / "clip.mp4"
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-ss",
               str(report["start_seconds"]), "-i", str(video), "-i", str(srt),
               "-t", str(length), "-map", "0:v:0", "-map", "0:a?", "-map", "1:s:0",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-c:s", "mov_text",
               "-metadata:s:s:0", "language=por", "-movflags", "+faststart",
               "-f", "mp4", str(mp4)]
        subprocess.run(cmd, capture_output=True, text=True, timeout=240, check=True)
        actual_duration, meta = probe(mp4)
        require(actual_duration > 0 and abs(actual_duration - length) <= 0.3 and
                any(s.get("codec_name") == "mov_text" for s in meta["streams"]),
                "MP4 missing expected duration or explanatory subtitle track")
        require(source_sha(video) == video_hash, "Recording changed during export")
        report["clip_sha256"] = source_sha(mp4)
        report["clip_duration_seconds_probed"] = actual_duration
        report["embedded_subtitle_codec"] = "mov_text"
        report["clip_explanation_is_conditional"] = True
        report_json = tmp / "clip.json"
        report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                          allow_nan=False) + "\n", encoding="utf-8")
        linked = []
        try:
            for src, dst in zip((mp4, report_json, srt), outputs):
                os.link(src, dst)  # Atomic, fails rather than overwriting an existing path.
                linked.append(dst)
        except BaseException:
            for path in linked:
                path.unlink(missing_ok=True)
            raise
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("recording", "handoff_report", "bridge_candidate", "math_report",
                 "manual_clip_annotation", "new_output_stem"):
        p.add_argument(name)
    a = p.parse_args(argv)
    result = export(a.recording, a.handoff_report, a.bridge_candidate,
                    a.math_report, a.manual_clip_annotation, a.new_output_stem)
    print(json.dumps({"status": result["status"], "clip_sha256": result["clip_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
