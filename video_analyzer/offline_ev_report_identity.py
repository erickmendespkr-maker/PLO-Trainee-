"""Bind a conditional EV report to a specific reviewed hand without asserting visual truth.

The trusted review must be independently obtained from a verified ledger. This
module checks identity only; it does not authenticate a ledger or inspect pixels.
"""
import hashlib
import json
import math
import re

_SHA = re.compile(r'[0-9a-f]{64}\Z')


def _identity(record):
    if not isinstance(record, dict):
        raise ValueError('record must be an object')
    hand = record.get('hand_id')
    table = record.get('table_id')
    video = record.get('video_sha256')
    start = record.get('start_seconds')
    end = record.get('end_seconds')
    if not isinstance(hand, str) or not hand.strip():
        raise ValueError('invalid hand id')
    if type(table) is not int or not 1 <= table <= 4:
        raise ValueError('invalid table id')
    if not isinstance(video, str) or not _SHA.fullmatch(video):
        raise ValueError('invalid video hash')
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)):
        raise ValueError('invalid timestamps')
    if not 0 <= start < end:
        raise ValueError('invalid interval')
    return {'hand_id': hand, 'table_id': table, 'video_sha256': video,
            'start_seconds': float(start), 'end_seconds': float(end)}


def bind_report(report, trusted_review):
    """Return a non-approved manifest; fail closed on mismatched identity.

    Report identity must be supplied by the upstream pipeline, not copied here
    from the review. A separate evidence gate and ledger audit remain required.
    """
    if not isinstance(report, dict):
        raise ValueError('report must be an object')
    expected = _identity(trusted_review)
    actual = _identity(report.get('hand_identity'))
    if actual != expected:
        raise ValueError('report/review hand identity mismatch')
    if trusted_review.get('review_status') != 'CONFIRMED':
        raise ValueError('review is not confirmed')
    if report.get('gto_solution') is not False:
        raise ValueError('unsupported GTO claim')
    if report.get('visual_hand_verified_by_this_module') is not False:
        raise ValueError('unsupported visual verification claim')
    if report.get('status') not in ('CONDITIONAL_MODEL_ONLY', 'RANGE_SENSITIVE'):
        raise ValueError('invalid model status')
    try:
        canonical = json.dumps(report, sort_keys=True, separators=(',', ':'),
                               ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError) as exc:
        raise ValueError('report must be finite JSON') from exc
    return {'hand_identity': expected, 'report_sha256': hashlib.sha256(canonical).hexdigest(),
            'status': 'IDENTITY_MATCH_ONLY', 'approved_for_publication': False,
            'required_next_checks': ['independent_ledger_authentication',
                                     'video_evidence_audit', 'ev_evidence_gate']}
