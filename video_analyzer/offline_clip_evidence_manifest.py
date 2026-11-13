"""Validate a clip's source-timeline interval and bind it to an unapproved EV report."""
import hashlib
import math
from pathlib import Path


def clip_sha256(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("clip must be a regular non-symlink file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clip_manifest(clip_path, identity, source_duration, clip_start, clip_end, binding=None):
    if not isinstance(identity, dict):
        raise ValueError("identity required")
    try:
        hand, table, video = (identity[k] for k in ("hand_id", "table_id", "video_sha256"))
        hs, he = (identity[k] for k in ("start_seconds", "end_seconds"))
    except KeyError as exc:
        raise ValueError("incomplete identity") from exc
    if not isinstance(hand, str) or not hand.strip() or type(table) is not int or not 1 <= table <= 4:
        raise ValueError("invalid hand/table")
    if not isinstance(video, str) or len(video) != 64 or any(c not in "0123456789abcdef" for c in video):
        raise ValueError("invalid source hash")
    times = (hs, he, source_duration, clip_start, clip_end)
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in times):
        raise ValueError("invalid times")
    if not 0 <= clip_start <= hs < he <= clip_end <= source_duration:
        raise ValueError("clip must enclose hand within source")
    canonical = dict(hand_id=hand, table_id=table, video_sha256=video,
                     start_seconds=float(hs), end_seconds=float(he))
    report_hash = None
    if binding is not None:
        if not isinstance(binding, dict) or binding.get("hand_identity") != canonical:
            raise ValueError("report identity mismatch")
        if binding.get("status") != "IDENTITY_MATCH_ONLY" or binding.get("approved_for_publication") is not False:
            raise ValueError("report binding is not trustworthy")
        report_hash = binding.get("report_sha256")
        if not isinstance(report_hash, str) or len(report_hash) != 64 or any(c not in "0123456789abcdef" for c in report_hash):
            raise ValueError("invalid report hash")
    return dict(schema_version=1, hand_identity=canonical,
                clip=dict(sha256=clip_sha256(clip_path), start_seconds=float(clip_start),
                          end_seconds=float(clip_end), source_duration_seconds=float(source_duration)),
                report_sha256=report_hash, status="PENDING_INDEPENDENT_AUDIT",
                approved_for_publication=False,
                required_next_checks=["ffprobe_output_audit", "independent_ledger_authentication",
                                      "visual_hand_review", "ev_evidence_gate"])
