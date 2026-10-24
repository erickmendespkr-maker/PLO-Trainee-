"""Manual-review windows between human-assigned hands in offline PLO recordings.

Only decoded PTS observations are used. A window is NOT an exact hand boundary,
a playable hand, an automatically approved clip, or permission for equity/EV.
Unverified OCR boundary hints may be attached as context, never confirmation.
"""
import argparse
import json
import math
from pathlib import Path
import re

from activity_snapshot_chain import canonical_sha256

_SHA = re.compile(r'[0-9a-f]{64}\Z')
_STATUS = 'human_reviewed_visible_timeline_not_verified_hand_reconstruction'
_HINT_STATUS = 'unverified_boundary_hints_only'
_HINT_REASONS = {'changed_private_cards', 'board_reset_or_conflict'}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _digest(value, label):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError(f'Invalid {label}')


def _timeline(timeline, expected_sha):
    if (not isinstance(timeline, dict) or timeline.get('schema_version') != 1
            or timeline.get('analysis_status') != _STATUS
            or timeline.get('ready_for_equity_or_ev') is not False
            or timeline.get('automatic_hand_boundaries_authorized') is not False
            or timeline.get('automatic_clip_selection_authorized') is not False):
        raise ValueError('Expected EV-blocked reviewed timeline')
    _digest(timeline.get('recording_sha256'), 'recording SHA-256')
    _digest(timeline.get('source_review_sha256'), 'review SHA-256')
    if 'decoded' not in str(timeline.get('timestamp_semantics', '')).lower():
        raise ValueError('Decoded PTS required')
    if expected_sha is not None:
        _digest(expected_sha, 'expected timeline SHA-256')
        if canonical_sha256(timeline) != expected_sha:
            raise ValueError('Timeline SHA-256 mismatch')
    hands = timeline.get('hands')
    unassigned = timeline.get('unassigned_observations')
    if (not isinstance(hands, list) or not isinstance(unassigned, list)
            or len(hands) > 10000 or len(unassigned) > 10000):
        raise ValueError('Invalid timeline size')
    seen, indices = set(), set()
    for hand in hands:
        if not isinstance(hand, dict):
            raise ValueError('Invalid hand')
        table, hand_id = hand.get('table_id'), hand.get('hand_id_human_assigned')
        if (type(table) is not int or not 1 <= table <= 4 or not isinstance(hand_id, str)
                or not hand_id.strip() or len(hand_id) > 100 or (table, hand_id) in seen):
            raise ValueError('Invalid or duplicate hand identity')
        seen.add((table, hand_id))
        events, flags = hand.get('events'), hand.get('review_flags')
        if (not isinstance(events, list) or not events or len(events) > 10000
                or not isinstance(flags, list) or any(not isinstance(x, str) for x in flags)):
            raise ValueError('Invalid hand events or review flags')
        times = []
        for event in events:
            if not isinstance(event, dict) or not _number(event.get('timestamp')):
                raise ValueError('Invalid event timestamp')
            idx = event.get('observation_index')
            if type(idx) is not int or idx < 0 or idx in indices:
                raise ValueError('Duplicate/invalid observation index')
            indices.add(idx)
            times.append(event['timestamp'])
        if (times != sorted(times) or hand.get('first_observed_pts') != times[0]
                or hand.get('last_observed_pts') != times[-1]
                or hand.get('observation_count') != len(events)):
            raise ValueError('Inconsistent observed hand span')
    for item in unassigned:
        if (not isinstance(item, dict) or type(item.get('table_id')) is not int
                or not 1 <= item['table_id'] <= 4 or not _number(item.get('timestamp'))):
            raise ValueError('Invalid unassigned observation')
        idx = item.get('observation_index')
        if type(idx) is not int or idx < 0 or idx in indices:
            raise ValueError('Duplicate/invalid unassigned observation index')
        indices.add(idx)
    if len(indices) > 10000:
        raise ValueError('Too many observations')
    return hands, unassigned


def _hints(hints, recording_sha):
    if hints is None:
        return []
    if (not isinstance(hints, dict) or hints.get('schema_version') != 1
            or hints.get('analysis_status') != _HINT_STATUS
            or hints.get('requires_manual_review') is not True
            or not isinstance(hints.get('boundary_hints'), list)
            or len(hints['boundary_hints']) > 10000):
        raise ValueError('Invalid unverified boundary hints')
    # If a producer includes a recording identity, it must match the timeline.
    if 'recording_sha256' in hints:
        _digest(hints['recording_sha256'], 'hint recording SHA-256')
        if hints['recording_sha256'] != recording_sha:
            raise ValueError('Hint recording SHA-256 mismatch')
    for hint in hints['boundary_hints']:
        if (not isinstance(hint, dict) or type(hint.get('table_id')) is not int
                or not 1 <= hint['table_id'] <= 4
                or not _number(hint.get('timestamp'))
                or hint.get('reason') not in _HINT_REASONS
                or hint.get('status') != 'needs_manual_review'
                or hint.get('human_confirmed') is not False
                or hint.get('field') not in ('hero_cards', 'board')
                or (hint.get('field') == 'hero_cards') != (hint.get('reason') == 'changed_private_cards')):
            raise ValueError('Invalid unverified boundary hint')
    return hints['boundary_hints']


def build_hand_boundary_review(timeline, hints=None, *, expected_timeline_sha256=None,
                               max_gap_seconds=120):
    """Produce bounded *review* intervals only between consecutive human hand IDs.

    An interval [last seen in A, first seen in B] is not a precise hand change.
    Gaps, unassigned observations and conflicts remain explicit; no inferred
    hand IDs or automatic cuts are emitted.
    """
    if not _number(max_gap_seconds) or max_gap_seconds == 0 or max_gap_seconds > 3600:
        raise ValueError('Invalid max gap')
    hands, unassigned = _timeline(timeline, expected_timeline_sha256)
    candidates = _hints(hints, timeline['recording_sha256'])
    groups = {table: [] for table in range(1, 5)}
    spans = []
    for hand in hands:
        table = hand['table_id']
        groups[table].append(hand)
        spans.append({'table_id': table, 'hand_id_human_assigned': hand['hand_id_human_assigned'],
                      'first_observed_pts': hand['first_observed_pts'],
                      'last_observed_pts': hand['last_observed_pts'],
                      'observed_start_action_pts': hand.get('hand_start_observed_pts'),
                      'observed_end_action_pts': hand.get('hand_end_observed_pts'),
                      'review_flags': list(hand['review_flags']),
                      'status': 'observed_span_not_exact_hand_boundaries'})
    windows = []
    for table, items in groups.items():
        items.sort(key=lambda h: (h['first_observed_pts'], h['last_observed_pts'],
                                  h['hand_id_human_assigned']))
        for left, right in zip(items, items[1:]):
            start, end = left['last_observed_pts'], right['first_observed_pts']
            reasons = []
            if end < start:
                reasons.append('overlapping_human_hand_assignments')
            elif end == start:
                reasons.append('same_pts_different_hands')
            elif end - start > max_gap_seconds:
                reasons.append('gap_exceeds_review_window_limit')
            if left['review_flags'] or right['review_flags']:
                reasons.append('adjacent_hands_have_review_flags')
            between = sorted((o['observation_index'] for o in unassigned
                              if o['table_id'] == table and min(start, end) <= o['timestamp'] <= max(start, end)))
            if between:
                reasons.append('unassigned_observations_in_interval')
            supporting = sorted(({'timestamp': h['timestamp'], 'field': h['field'],
                                  'reason': h['reason'], 'status': 'unverified_not_confirmation',
                                  'recording_identity_bound': 'recording_sha256' in hints}
                                 for h in candidates if h['table_id'] == table
                                 and min(start, end) <= h['timestamp'] <= max(start, end)),
                                key=lambda x: (x['timestamp'], x['field'], x['reason']))
            windows.append({
                'table_id': table, 'previous_hand_id_human_assigned': left['hand_id_human_assigned'],
                'next_hand_id_human_assigned': right['hand_id_human_assigned'],
                'previous_last_observed_pts': start, 'next_first_observed_pts': end,
                'candidate_interval_pts': [start, end] if end > start else None,
                'gap_seconds': end - start if end >= start else None,
                'unassigned_observation_indices': between,
                'unverified_ocr_hints': supporting,
                'review_reasons': reasons,
                'status': ('review_interval_available_not_confirmed' if not reasons
                           else 'manual_resolution_required'),
                'exact_boundary_known': False, 'hand_assignment_automated': False,
            })
    windows.sort(key=lambda w: (w['table_id'], w['previous_last_observed_pts'],
                                w['next_first_observed_pts']))
    spans.sort(key=lambda h: (h['table_id'], h['first_observed_pts'], h['hand_id_human_assigned']))
    return {
        'schema_version': 1,
        'analysis_status': 'review_only_candidate_inter_hand_windows',
        'source_timeline_sha256': canonical_sha256(timeline),
        'source_review_sha256': timeline['source_review_sha256'],
        'source_boundary_hints_sha256': canonical_sha256(hints) if hints is not None else None,
        'hints_recording_identity_bound': hints is not None and 'recording_sha256' in hints,
        'recording_sha256': timeline['recording_sha256'],
        'timestamp_semantics': timeline['timestamp_semantics'],
        'observed_hand_spans': spans, 'inter_hand_review_windows': windows,
        'counts': {'observed_human_assigned_hands': len(spans),
                   'inter_hand_windows': len(windows),
                   'windows_needing_manual_resolution': sum(w['status'] == 'manual_resolution_required' for w in windows)},
        'ready_for_equity_or_ev': False,
        'automatic_hand_boundaries_authorized': False,
        'automatic_clip_selection_authorized': False,
        'strategic_error_established': False,
        'warning': ('Intervals bound two human-assigned observed hands, not the actual change time. '
                    'Unverified OCR hints are not independent confirmation. '
                    'No missing cards/actions inferred and no clips/equity/EV authorized.'),
    }


def write_hand_boundary_review(timeline_path, output_path, *, hints_path=None,
                               expected_timeline_sha256=None, max_gap_seconds=120):
    inputs = [Path(timeline_path)] + ([Path(hints_path)] if hints_path is not None else [])
    output = Path(output_path)
    if (any(not p.is_file() or p.is_symlink() for p in inputs)
            or output.exists() or output.is_symlink()
            or any(p.resolve() == output.resolve() for p in inputs)):
        raise ValueError('Require regular input files and a new distinct output')
    timeline = json.loads(inputs[0].read_text(encoding='utf-8'))
    hints = json.loads(inputs[1].read_text(encoding='utf-8')) if len(inputs) > 1 else None
    result = build_hand_boundary_review(timeline, hints,
                    expected_timeline_sha256=expected_timeline_sha256,
                    max_gap_seconds=max_gap_seconds)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reviewed_timeline_json')
    parser.add_argument('output_json')
    parser.add_argument('--hints-json')
    parser.add_argument('--expected-timeline-sha256')
    parser.add_argument('--max-gap-seconds', type=float, default=120)
    args = parser.parse_args()
    result = write_hand_boundary_review(args.reviewed_timeline_json, args.output_json,
               hints_path=args.hints_json,
               expected_timeline_sha256=args.expected_timeline_sha256,
               max_gap_seconds=args.max_gap_seconds)
    print(json.dumps(result['counts']))
