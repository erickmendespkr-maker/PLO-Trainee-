"""Offline hand-review history. No automatic promotion of OCR into verified facts."""
import hashlib
import json
import math
from pathlib import Path

try:
    from .offline_evidence_card_gate import assess_reviewed_hand
except ImportError:
    from offline_evidence_card_gate import assess_reviewed_hand


def build_review_history(video_sha256, hands, *, minimum_confidence=0.90):
    """Build a JSON-compatible review ledger, retaining only safe audit metadata.

    Each hand has `evidence` (the reviewed field mapping) and `variant` (PLO5/PLO6).
    The ledger does not claim that a hand was reconstructed correctly or EV solved.
    """
    if not isinstance(video_sha256, str) or len(video_sha256) != 64 or any(c not in '0123456789abcdef' for c in video_sha256):
        raise ValueError('video_sha256 must be a lowercase SHA-256 hex digest')
    if not isinstance(hands, list):
        raise ValueError('hands must be a list')
    results = []
    for index, item in enumerate(hands):
        if not isinstance(item, dict) or not isinstance(item.get('evidence'), dict):
            raise ValueError(f'hand {index}: missing evidence mapping')
        variant = item.get('variant')
        if variant not in ('PLO5', 'PLO6'):
            raise ValueError(f'hand {index}: invalid variant')
        gate = assess_reviewed_hand(item['evidence'], variant, minimum_confidence=minimum_confidence)
        fields = item['evidence']
        def val(name):
            field = fields.get(name)
            return field.get('value') if isinstance(field, dict) else None
        start, end = val('hand_start_s'), val('hand_end_s')
        def safe_time(x):
            return x if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0 else None
        results.append({
            'index': index, 'variant': variant, 'table_id': val('table_id') if isinstance(val('table_id'), (str, int)) and not isinstance(val('table_id'), bool) else None,
            'start_s': safe_time(start), 'end_s': safe_time(end),
            'status': gate['status'], 'conditional_analysis_allowed': gate['conditional_analysis_allowed'],
            'evidence_review': gate['evidence'], 'card_review': gate['cards'],
            'equity': None, 'ev': None, 'strategic_verification': False,
            'clip_status': 'NOT_EXPORTED',
        })
    return {'schema_version': 1, 'source_video_sha256': video_sha256,
            'analysis_type': 'OFFLINE_REVIEW_ONLY', 'hands': results,
            'summary': {'total': len(results), 'ready_for_conditional_analysis': sum(x['conditional_analysis_allowed'] for x in results),
                        'insufficient_data': sum(not x['conditional_analysis_allowed'] for x in results)},
            'equity_or_ev_computed': False, 'video_visual_accuracy_verified': False}


def write_review_history(path, history):
    """Write a new report exclusively; never overwrite an existing file."""
    data = (json.dumps(history, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')
    with Path(path).open('xb') as f:
        f.write(data)
    return hashlib.sha256(data).hexdigest()
