"""Fail-closed binding between a reviewed hand record and an audited offline clip.

The caller must supply a separately stored, trusted review record; the MP4 sidecar
alone cannot establish that a hand was reviewed. No poker strategy is inferred.
"""
import re
from pathlib import Path

from offline_clip_audit import audit_export


def audit_against_review(mp4_path, review_record):
    if type(review_record) is not dict:
        raise ValueError('trusted review record required')
    required = {'source_sha256', 'hand_id', 'table_id', 'start_seconds',
                'end_seconds', 'review_status'}
    if not required.issubset(review_record):
        raise ValueError('incomplete trusted review record')
    source = review_record['source_sha256']
    if type(source) is not str or re.fullmatch('[0-9a-f]{64}', source) is None:
        raise ValueError('invalid trusted source hash')
    if type(review_record['review_status']) is not str or review_record['review_status'] not in ('confirmed', 'insufficient_data'):
        raise ValueError('invalid trusted review status')
    result = audit_export(
        Path(mp4_path),
        expected_source_sha256=source,
        expected_hand_id=review_record['hand_id'],
        expected_table_id=review_record['table_id'],
        expected_interval=(review_record['start_seconds'], review_record['end_seconds']),
        expected_review_status=review_record['review_status'],
    )
    return {**result, 'trusted_review_binding_verified': True,
            'strategic_error_established': False, 'hand_reconstruction_verified': False}
