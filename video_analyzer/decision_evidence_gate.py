"""Validate *human-attested* field provenance for offline PLO video reviews.

This validates annotation consistency, not whether a video frame really shows
those cards or chips. It must never convert OCR into confirmed evidence.
"""
import math

REQUIRED_FIELDS = ('hero_cards', 'board', 'observed_action',
                   'pot_before_action', 'call_amount')
SOURCES = frozenset({'video_frame_review', 'manual_correction'})


def _number(value, name, *, maximum=None):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0
            or (maximum is not None and value > maximum)):
        raise ValueError(f'{name} must be a finite nonnegative number within bounds')
    return float(value)


def validate_decision_evidence(scenario, duration_seconds):
    """Check five required, explicitly reviewed fields against scenario values.

    Each reviewed_fields entry has value, confidence, source_timestamp,
    source, human_confirmed. The minimum field confidence upper-bounds the
    decision confidence. Source timestamps must lie within the recording.
    No file, video frame, or identity is authenticated by this function.
    """
    duration = _number(duration_seconds, 'duration_seconds')
    if duration <= 0 or not isinstance(scenario, dict) or scenario.get('human_confirmed') is not True:
        raise ValueError('Positive video duration and explicit human confirmation required')
    reviewed = scenario.get('reviewed_fields')
    if not isinstance(reviewed, dict) or set(reviewed) != set(REQUIRED_FIELDS):
        raise ValueError('reviewed_fields must contain exactly the required fields')
    decision_time = _number(scenario.get('timestamp'), 'timestamp', maximum=duration)
    confidences = {}
    for field in REQUIRED_FIELDS:
        item = reviewed[field]
        if not isinstance(item, dict) or item.get('human_confirmed') is not True:
            raise ValueError(f'{field} requires explicit human confirmation')
        if item.get('source') not in SOURCES:
            raise ValueError(f'{field} requires a supported evidence source')
        source_time = _number(item.get('source_timestamp'),
                              f'{field}.source_timestamp', maximum=duration)
        # A later video frame must never be used to justify an earlier action.
        # This is a video-timeline timestamp, not the wall-clock review time.
        if source_time > decision_time + 1e-9:
            raise ValueError(f'{field} source_timestamp is after decision timestamp')
        confidence = _number(item.get('confidence'), f'{field}.confidence', maximum=1)
        if field not in scenario or item.get('value') != scenario[field]:
            raise ValueError(f'{field} reviewed value differs from scenario')
        confidences[field] = confidence
    declared = _number(scenario.get('observation_confidence'), 'observation_confidence', maximum=1)
    minimum = min(confidences.values())
    if declared > minimum + 1e-12:
        raise ValueError('Decision confidence cannot exceed weakest reviewed field')
    return {
        'status': 'human_attested_not_video_verified',
        'decision_timestamp': decision_time,
        'minimum_field_confidence': minimum,
        'declared_decision_confidence': declared,
        'field_confidences': confidences,
        'warning': 'Human attestation only; frame authenticity and OCR accuracy not verified.',
    }
