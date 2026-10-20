"""Plan explainable cuts from human-reviewed events; no unverified mistake claims."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ReviewCandidate:
    table_id: int
    hand_id: str
    decision_time: float
    impact_estimate: float
    confidence: float
    explanation: str
    hypotheses: str


def select_clips(candidates, *, min_confidence=.75, max_clips=10,
                 seconds_before=12., seconds_after=18., video_duration=None):
    """Rank by modeled impact*confidence and return proposed clip boundaries.

    These are review candidates, not established mistakes; inputs may be manual.
    """
    if not isinstance(max_clips, int) or isinstance(max_clips, bool) or not 0 <= min_confidence <= 1 or max_clips < 0 or seconds_before < 0 or seconds_after <= 0:
        raise ValueError('Invalid clip parameters')
    if video_duration is not None and (not math.isfinite(video_duration) or video_duration <= 0):
        raise ValueError('Invalid duration')
    valid = []
    for c in candidates:
        if not isinstance(c, ReviewCandidate) or not 1 <= c.table_id <= 4:
            raise ValueError('Invalid candidate')
        if not all(math.isfinite(x) for x in (c.decision_time, c.impact_estimate, c.confidence)):
            raise ValueError('Non-finite candidate values')
        if c.decision_time < 0 or not 0 <= c.confidence <= 1 or c.impact_estimate < 0:
            raise ValueError('Invalid candidate values')
        if video_duration is not None and c.decision_time > video_duration:
            raise ValueError('Candidate beyond video duration')
        if c.confidence >= min_confidence:
            valid.append(c)
    valid.sort(key=lambda c: (-c.impact_estimate * c.confidence, c.decision_time, c.table_id))
    clips = []
    for c in valid[:max_clips]:
        start = max(0., c.decision_time - seconds_before)
        end = c.decision_time + seconds_after
        if video_duration is not None:
            end = min(end, video_duration)
        if end <= start:
            continue
        clips.append({'table_id': c.table_id, 'hand_id': c.hand_id,
                      'start': start, 'end': end, 'confidence': c.confidence,
                      'modeled_impact': c.impact_estimate,
                      'explanation': c.explanation, 'hypotheses': c.hypotheses,
                      'status': 'needs_review'})
    return clips
