"""Combine human review and local file integrity without claiming frame provenance.

Hashes do not establish that frames came from a claimed PTS.
"""
from .offline_evidence_file_audit import audit_local_evidence
from .offline_review_evidence_gate import review_gate


def verified_review_gate(hand, source_video, frame_directory):
    """Fail closed: only conditional analysis, never GTO/blunder labels."""
    try:
        review = review_gate(hand)
    except (ValueError, TypeError, KeyError, OverflowError):
        review = {"status": "INSUFFICIENT_DATA", "reasons": ["review_record_invalid"]}
    try:
        files = audit_local_evidence(hand, source_video, frame_directory)
    except (OSError, ValueError, TypeError, RuntimeError):
        files = {"status": "INSUFFICIENT_DATA", "reasons": ["file_audit_failed"],
                 "verified_file_count": 0, "proves_frame_origin": False}
    permitted = (review.get("status") == "CONDITIONAL_ANALYSIS_PERMITTED"
                 and files.get("status") == "LOCAL_BYTES_VERIFIED")
    return {
        "status": "CONDITIONAL_ANALYSIS_PERMITTED" if permitted else "INSUFFICIENT_DATA",
        "reasons": sorted(set(review.get("reasons", []) + files.get("reasons", []))),
        "review_status": review.get("status"),
        "file_audit_status": files.get("status"),
        "verified_file_count": files.get("verified_file_count", 0),
        "proves_frame_origin": False,
        "gto_claim_permitted": False,
        "automatic_blunder_label_permitted": False,
    }
