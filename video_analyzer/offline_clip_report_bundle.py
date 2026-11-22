"""Bind conservative timestamp audit to an offline conditional decision report.

Temporal alignment alone never establishes visual verification or strategic truth.
"""
from collections.abc import Mapping

try:
    from .offline_clip_alignment import audit_clip_alignment
    from .offline_decision_report import decision_report
except ImportError:
    from offline_clip_alignment import audit_clip_alignment
    from offline_decision_report import decision_report


def build_clip_report_bundle(analysis: Mapping, *, video_sha256: str,
                             clip_start_s: float, clip_end_s: float,
                             video_duration_s: float, tolerance_s: float = 0.05) -> dict:
    """Suppress conditional EV in a report when clip coverage is insufficient."""
    alignment = audit_clip_alignment(analysis, clip_start_s=clip_start_s,
                                     clip_end_s=clip_end_s,
                                     video_duration_s=video_duration_s,
                                     tolerance_s=tolerance_s)
    if alignment['status'] == 'TEMPORALLY_ALIGNED_ONLY':
        report_input = analysis
    else:
        report_input = {'status': 'INSUFFICIENT_DATA',
                        'evidence': {'status': 'INSUFFICIENT_DATA',
                                     'missing_fields': ['clip_alignment'],
                                     'invalid_fields': [], 'unverified_fields': []}}
    report = decision_report(report_input, video_sha256=video_sha256,
                             clip_start_s=clip_start_s, clip_end_s=clip_end_s)
    report['clip']['alignment_status'] = alignment['status']
    report['clip']['alignment_reason'] = alignment['reason']
    report['clip']['visually_verified'] = False
    return {'alignment': alignment, 'report': report}
