"""Evidence-only handoff between sparse PTS proposals and human review."""
import hashlib
import json
import math

try:
    from .offline_pts_evidence_intervals import propose_transition_windows
    from .offline_pts_window_audit import audit_transition_windows
except ImportError:
    from offline_pts_evidence_intervals import propose_transition_windows
    from offline_pts_window_audit import audit_transition_windows


def build_pts_review_handoff(observations, *, video_sha256, video_duration_seconds,
                             max_gap_seconds=30.0, max_tables=4):
    """Return deterministic pending review tasks, never confirmed poker hands."""
    if not isinstance(video_sha256, str) or len(video_sha256) != 64 or any(
            c not in '0123456789abcdef' for c in video_sha256):
        raise ValueError('invalid video SHA-256')
    if type(video_duration_seconds) not in (int, float) or not math.isfinite(video_duration_seconds) or video_duration_seconds <= 0:
        raise ValueError('invalid video duration')
    if not isinstance(observations, list):
        raise ValueError('observations must be a list')
    for observation in observations:
        if not isinstance(observation, dict):
            raise ValueError('invalid observation')
        pts = observation.get('pts')
        if type(pts) not in (int, float) or not math.isfinite(pts) or pts > video_duration_seconds:
            raise ValueError('observation outside video')
    windows = propose_transition_windows(observations, max_gap_seconds=max_gap_seconds)
    audit = audit_transition_windows(windows, video_duration_seconds=video_duration_seconds,
                                     max_tables=max_tables)
    tables = {row['table_id'] for row in observations}
    if len(tables) > max_tables:
        raise ValueError('too many observed tables')
    tasks = []
    for window in windows:
        evidence = {key: window[key] for key in ('table_id', 'earliest_pts', 'latest_pts',
                    'start_frame_sha256', 'end_frame_sha256', 'from_state', 'to_state',
                    'status', 'gap_seconds')}
        canonical = json.dumps({'video_sha256': video_sha256, **evidence},
                               sort_keys=True, separators=(',', ':'), allow_nan=False)
        tasks.append({'review_id': hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
                      'evidence': evidence, 'review_status': 'PENDING',
                      'verified_hand_id': None, 'verified_action': None,
                      'strategic_commentary_allowed': False,
                      'requires_human_review': True})
    return {'schema_version': 1, 'source': 'offline_recorded_video',
            'video_sha256': video_sha256, 'video_duration_seconds': video_duration_seconds,
            'audit': {k: v for k, v in audit.items() if k != 'review_queue'},
            'observed_tables': len(tables), 'tasks': tasks,
            'equity_or_ev_computed': False, 'mp4_exported': False}
