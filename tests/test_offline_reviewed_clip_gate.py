import pytest
from video_analyzer.offline_reviewed_clip_gate import build_reviewed_clip_plan

BASE = dict(hand_id="hand-1", table_id=2, start_pts=12.5, end_pts=31.0,
            video_sha256="a"*64, human_reviewed=True, hand_boundary_confirmed=True,
            explanation_verified=True, explanation="Conditional scenario; assumed ranges.")


def test_ready_and_deterministic():
    a = build_reviewed_clip_plan(BASE, 60)
    assert a == build_reviewed_clip_plan(dict(BASE), 60)
    assert a["status"] == "READY_FOR_OFFLINE_EXPORT"
    assert a["not_gto"] and a["requires_source_hash_check"]


@pytest.mark.parametrize("field,value", [
    ("table_id", 5), ("table_id", True), ("start_pts", -1),
    ("end_pts", 61), ("end_pts", 12.5), ("start_pts", float("nan")),
    ("video_sha256", "b"*63), ("hand_id", ""), ("explanation", "")])
def test_reject_invalid(field, value):
    with pytest.raises(ValueError):
        build_reviewed_clip_plan({**BASE, field: value}, 60)


@pytest.mark.parametrize("field", [
    "human_reviewed", "hand_boundary_confirmed", "explanation_verified"])
def test_review_gate(field):
    assert build_reviewed_clip_plan({**BASE, field: False}, 60)["status"] == "REVIEW_REQUIRED"


def test_duration_invalid():
    with pytest.raises(ValueError):
        build_reviewed_clip_plan(BASE, float("inf"))
