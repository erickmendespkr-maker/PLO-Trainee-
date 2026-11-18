"""Audit local offline frame artifacts; matching hashes do not prove visual truth."""
from pathlib import Path
import hashlib
import hmac
import re

_SHA = re.compile(r"[0-9a-f]{64}\Z")

def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def _has_symlink_component(path):
    """Inspect lexical ancestors before resolve() can hide symlinks."""
    return any(part.is_symlink() for part in (path, *path.parents))

def audit_local_evidence(hand, source_video, frame_directory):
    """Fail closed on local bytes. Does not establish PTS, table or frame origin."""
    reasons = []
    if not isinstance(hand, dict):
        return {"status": "INSUFFICIENT_DATA", "reasons": ["invalid_hand"],
                "verified_file_count": 0, "proves_frame_origin": False}
    root_input = Path(frame_directory).absolute()
    root = root_input.resolve()
    if _has_symlink_component(root_input) or not root.is_dir():
        return {"status": "INSUFFICIENT_DATA", "reasons": ["frame_directory_invalid"],
                "verified_file_count": 0, "proves_frame_origin": False}
    source_input = Path(source_video).absolute()
    source_unsafe = _has_symlink_component(source_input)
    source = source_input.resolve()
    declared = hand.get("source_video_sha256")
    if not isinstance(declared, str) or not _SHA.fullmatch(declared):
        reasons.append("source_hash_invalid")
    if not source.is_file() or source_unsafe:
        reasons.append("source_file_missing_or_symlink")
    elif isinstance(declared, str) and _SHA.fullmatch(declared) and not hmac.compare_digest(_sha256(source), declared):
        reasons.append("source_hash_mismatch")
    frames = hand.get("evidence")
    verified = 0
    if not isinstance(frames, list) or not frames:
        reasons.append("frame_evidence_missing")
    else:
        for index, frame in enumerate(frames):
            prefix = f"frame_{index}_"
            if not isinstance(frame, dict):
                reasons.append(prefix + "invalid_record")
                continue
            name = frame.get("frame_file")
            expected = frame.get("frame_sha256")
            if not isinstance(name, str) or not name or Path(name).is_absolute() or "\\" in name or ".." in Path(name).parts:
                reasons.append(prefix + "unsafe_path")
                continue
            candidate = root / name
            # resolve() hides symlink components; inspect the original path first.
            if any(part.is_symlink() for part in (candidate, *candidate.parents)
                   if part != root and root in part.parents):
                reasons.append(prefix + "file_missing_or_unsafe")
                continue
            target = candidate.resolve()
            if not target.is_relative_to(root) or target == root or not target.is_file():
                reasons.append(prefix + "file_missing_or_unsafe")
                continue
            if not isinstance(expected, str) or not _SHA.fullmatch(expected):
                reasons.append(prefix + "hash_invalid")
                continue
            if not hmac.compare_digest(_sha256(target), expected):
                reasons.append(prefix + "hash_mismatch")
                continue
            verified += 1
    return {"status": "INSUFFICIENT_DATA" if reasons else "LOCAL_BYTES_VERIFIED",
            "reasons": reasons, "verified_file_count": verified, "proves_frame_origin": False}
