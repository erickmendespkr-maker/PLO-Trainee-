"""Regression tests for symlinked ancestors in offline evidence paths."""
import hashlib
from video_analyzer.offline_evidence_file_audit import audit_local_evidence

def fixture(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    frames = real / "frames"
    frames.mkdir()
    (frames / "frame.png").write_bytes(b"frame")
    video = real / "source.mp4"
    video.write_bytes(b"video")
    sha = lambda x: hashlib.sha256(x).hexdigest()
    hand = {"source_video_sha256": sha(b"video"), "evidence": [
        {"frame_file": "frame.png", "frame_sha256": sha(b"frame")}]}
    return real, frames, video, hand

def test_valid_files(tmp_path):
    _, frames, video, hand = fixture(tmp_path)
    assert audit_local_evidence(hand, video, frames)["status"] == "LOCAL_BYTES_VERIFIED"

def test_symlinked_source_ancestor(tmp_path):
    real, frames, _, hand = fixture(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    out = audit_local_evidence(hand, alias / "source.mp4", frames)
    assert "source_file_missing_or_symlink" in out["reasons"]

def test_symlinked_frame_root_ancestor(tmp_path):
    real, _, video, hand = fixture(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    out = audit_local_evidence(hand, video, alias / "frames")
    assert "frame_directory_invalid" in out["reasons"]

def test_symlinked_frame_child(tmp_path):
    _, frames, video, hand = fixture(tmp_path)
    (frames / "alias.png").symlink_to(frames / "frame.png")
    hand["evidence"][0]["frame_file"] = "alias.png"
    out = audit_local_evidence(hand, video, frames)
    assert "frame_0_file_missing_or_unsafe" in out["reasons"]
