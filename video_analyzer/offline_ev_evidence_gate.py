"""Fail-closed consistency gate for offline conditional EV reports.

Does not authenticate a reviewer or inspect video pixels. Caller must first
validate the review ledger/checkpoint and source video independently.
"""
import math
import re

_HASH = re.compile(r"[0-9a-f]{64}\Z")


def gate_ev_report(report, review, *, trusted_video_sha256):
    """Check model metadata against a separately trusted review record."""
    reasons = []
    if not isinstance(report, dict) or not isinstance(review, dict):
        return {'approved': False, 'status': 'INSUFFICIENT_DATA',
                'reasons': ['invalid_report_or_review'], 'gto_solution': False}
    if not isinstance(trusted_video_sha256, str) or not _HASH.fullmatch(trusted_video_sha256):
        reasons.append('invalid_trusted_video_hash')
    if review.get('video_sha256') != trusted_video_sha256:
        reasons.append('recording_hash_mismatch')
    if review.get('review_status') != 'CONFIRMED':
        reasons.append('hand_not_confirmed')
    if type(review.get('table_id')) is not int or not 1 <= review['table_id'] <= 4:
        reasons.append('invalid_table_id')
    if not isinstance(review.get('hand_id'), str) or not review['hand_id'].strip():
        reasons.append('invalid_hand_id')
    start, end = review.get('start_seconds'), review.get('end_seconds')
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)) or not (0 <= start < end):
        reasons.append('invalid_time_range')
    if report.get('gto_solution') is not False or report.get('visual_hand_verified_by_this_module') is not False:
        reasons.append('unsupported_verification_claim')
    if report.get('publication_requires_external_review_binding') is not True:
        reasons.append('missing_review_binding_requirement')
    if report.get('status') not in ('CONDITIONAL_MODEL_ONLY', 'RANGE_SENSITIVE'):
        reasons.append('invalid_model_status')
    if report.get('unit') not in ('bb', 'chips') or not isinstance(report.get('assumptions'), dict) or not report['assumptions']:
        reasons.append('missing_model_context')
    if not isinstance(report.get('scenario_ids'), list) or not report['scenario_ids'] or any(not isinstance(s, str) or not s.strip() for s in report['scenario_ids']):
        reasons.append('missing_scenarios')
    if report.get('interval_type') != 'hypothetical_model_bounds_not_statistical_confidence':
        reasons.append('invalid_interval_type')
    if report.get('chosen_action') not in ('fold', 'call', 'raise'):
        reasons.append('invalid_chosen_action')
    if report.get('reviewed_hand_claimed_by_caller') is not True:
        reasons.append('caller_has_not_claimed_review')
    return {'approved': not reasons,
            'status': 'CONDITIONAL_MODEL_ONLY' if not reasons else 'INSUFFICIENT_DATA',
            'reasons': reasons, 'gto_solution': False,
            'warning': 'Consistency only; ledger authenticity and video evidence require independent verification.'}
