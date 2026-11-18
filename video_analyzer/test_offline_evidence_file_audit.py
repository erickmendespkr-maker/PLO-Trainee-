import hashlib
from offline_evidence_file_audit import audit_local_evidence

def sha(data):
    return hashlib.sha256(data).hexdigest()

def setup(tmp_path):
    root = tmp_path / "frames"
    root.mkdir()
    (root / "f.png").write_bytes(b"frame sample")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video sample")
    hand = {"source_video_sha256": sha(b"video sample"), "evidence": [
        {"frame_file": "f.png", "frame_sha256": sha(b"frame sample")}]}
    return hand, source, root

def test_valid_bytes_do_not_prove_origin(tmp_path):
    h, s, r = setup(tmp_path)
    out = audit_local_evidence(h, s, r)
    assert out["status"] == "LOCAL_BYTES_VERIFIED"
    assert out["verified_file_count"] == 1
    assert out["proves_frame_origin"] is False

def test_source_tampered(tmp_path):
    h, s, r = setup(tmp_path)
    s.write_bytes(b"tampered")
    assert "source_hash_mismatch" in audit_local_evidence(h, s, r)["reasons"]

def test_frame_tampered(tmp_path):
    h, s, r = setup(tmp_path)
    (r / "f.png").write_bytes(b"tampered")
    assert "frame_0_hash_mismatch" in audit_local_evidence(h, s, r)["reasons"]

def test_traversal_rejected(tmp_path):
    h, s, r = setup(tmp_path)
    h["evidence"][0]["frame_file"] = "../source.mp4"
    assert "frame_0_unsafe_path" in audit_local_evidence(h, s, r)["reasons"]

def test_absolute_rejected(tmp_path):
    h, s, r = setup(tmp_path)
    h["evidence"][0]["frame_file"] = str(s)
    assert "frame_0_unsafe_path" in audit_local_evidence(h, s, r)["reasons"]

def test_missing_file(tmp_path):
    h, s, r = setup(tmp_path)
    (r / "f.png").unlink()
    assert "frame_0_file_missing_or_unsafe" in audit_local_evidence(h, s, r)["reasons"]

def test_empty_evidence(tmp_path):
    h, s, r = setup(tmp_path)
    h["evidence"] = []
    assert "frame_evidence_missing" in audit_local_evidence(h, s, r)["reasons"]

def test_bad_hash(tmp_path):
    h, s, r = setup(tmp_path)
    h["evidence"][0]["frame_sha256"] = "A" * 64
    assert "frame_0_hash_invalid" in audit_local_evidence(h, s, r)["reasons"]

def test_symlink_escape(tmp_path):
    h, s, r = setup(tmp_path)
    (r / "link.png").symlink_to(s)
    h["evidence"][0]["frame_file"] = "link.png"
    assert "frame_0_file_missing_or_unsafe" in audit_local_evidence(h, s, r)["reasons"]

def test_invalid_hand(tmp_path):
    assert audit_local_evidence(None, tmp_path, tmp_path)["status"] == "INSUFFICIENT_DATA"
