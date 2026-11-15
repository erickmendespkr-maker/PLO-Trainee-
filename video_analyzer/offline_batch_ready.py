"""Fail-closed orchestration of provisional clip preflight and destination audit.

No export occurs. The returned plan is not a reservation and must be checked
again by the exporter immediately before creating artifacts.
"""
from pathlib import Path
try:
    from .offline_batch_preflight import preflight_batch
    from .offline_batch_destination_audit import audit_destinations
except ImportError:
    from offline_batch_preflight import preflight_batch
    from offline_batch_destination_audit import audit_destinations


def prepare_batch(plan, source_duration, output_root, *, max_clips=200, max_total_seconds=1800):
    """Validate the entire batch before any clip is written."""
    checked = preflight_batch(plan, source_duration, max_clips=max_clips,
                              max_total_seconds=max_total_seconds)
    audited = audit_destinations(plan, output_root)
    if len(checked['clips']) != len(audited):
        raise ValueError('audit and preflight counts differ')
    ready = []
    for candidate, destination in zip(checked['clips'], audited):
        if Path(candidate['destination']).resolve(strict=False) != Path(destination['destination']):
            raise ValueError('audit and preflight destination mismatch')
        ready.append({**candidate, 'destination': destination['destination'],
                      'manifest': destination['manifest'],
                      'status': 'READY_NOT_RESERVED_NOT_EXPORTED',
                      'human_review_required': True})
    return {'clips': ready, 'total_seconds': checked['total_seconds'],
            'status': 'READY_NOT_RESERVED_NOT_EXPORTED',
            'human_review_required': True}
