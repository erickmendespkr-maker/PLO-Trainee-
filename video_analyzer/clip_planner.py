"""Plan explainable, non-duplicative cuts from reviewed events only.

These are candidate review clips, not objectively established poker mistakes.
"""
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


def _finite_number(value):
    return (isinstance(value, (float, int)) and not isinstance(value, bool)
            and math.isfinite(value))


def select_clips(candidates, *, min_confidence=.75, max_clips=10,
                 seconds_before=12., seconds_after=18., video_duration=None,
                 deduplicate_same_hand=True, overlap_threshold=.8,
                 max_total_seconds=None, min_modeled_impact=0.):
    """Rank by impact*confidence; avoid redundant cuts from the same hand.

    Overlap fraction uses intersection divided by the *shorter* clip duration.
    Deduplication only compares clips from the same table and hand, never
    independent tables. Ranking remains deterministic. All clips need review.
    An optional aggregate duration budget skips clips that do not fit without
    trimming context; later, shorter candidates may still fit.
    """
    if (not _finite_number(min_confidence) or not 0 <= min_confidence <= 1
            or isinstance(max_clips, bool) or not isinstance(max_clips, int) or max_clips < 0
            or not _finite_number(seconds_before) or seconds_before < 0
            or not _finite_number(seconds_after) or seconds_after <= 0
            or not isinstance(deduplicate_same_hand, bool)
            or not _finite_number(overlap_threshold) or not 0 < overlap_threshold <= 1
            or not _finite_number(min_modeled_impact) or min_modeled_impact < 0
            or (max_total_seconds is not None and
                (not _finite_number(max_total_seconds) or max_total_seconds < 0))):
        raise ValueError('Invalid clip parameters')
    if video_duration is not None and (not _finite_number(video_duration) or video_duration <= 0):
        raise ValueError('Invalid duration')
    valid = []
    for c in candidates:
        if (not isinstance(c, ReviewCandidate) or isinstance(c.table_id, bool)
                or not 1 <= c.table_id <= 4 or not isinstance(c.hand_id, str)
                or not c.hand_id.strip()):
            raise ValueError('Invalid candidate')
        if not all(_finite_number(x) for x in (c.decision_time, c.impact_estimate, c.confidence)):
            raise ValueError('Non-finite candidate values')
        if c.decision_time < 0 or not 0 <= c.confidence <= 1 or c.impact_estimate < 0:
            raise ValueError('Invalid candidate values')
        if video_duration is not None and c.decision_time > video_duration:
            raise ValueError('Candidate beyond video duration')
        if c.confidence >= min_confidence and c.impact_estimate >= min_modeled_impact:
            valid.append(c)
    valid.sort(key=lambda c: (-c.impact_estimate * c.confidence,
                              c.decision_time, c.table_id, c.hand_id))
    clips = []
    total_seconds = 0.
    for c in valid:
        if len(clips) >= max_clips:
            break
        start = max(0., c.decision_time - seconds_before)
        end = c.decision_time + seconds_after
        if video_duration is not None:
            end = min(end, video_duration)
        if end <= start:
            continue
        if max_total_seconds is not None and total_seconds + (end - start) > max_total_seconds + 1e-9:
            continue
        if deduplicate_same_hand:
            redundant = False
            for old in clips:
                if old['table_id'] != c.table_id or old['hand_id'] != c.hand_id:
                    continue
                overlap = max(0., min(end, old['end']) - max(start, old['start']))
                fraction = overlap / min(end - start, old['end'] - old['start'])
                if fraction >= overlap_threshold:
                    redundant = True
                    break
            if redundant:
                continue
        total_seconds += end - start
        clips.append({'table_id': c.table_id, 'hand_id': c.hand_id,
                      'start': start, 'end': end, 'confidence': c.confidence,
                      'modeled_impact': c.impact_estimate,
                      'explanation': c.explanation, 'hypotheses': c.hypotheses,
                      'status': 'needs_review'})
    return clips
