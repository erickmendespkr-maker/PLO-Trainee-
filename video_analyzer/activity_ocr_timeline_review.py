"""Conservative offline OCR-to-reviewed-timeline comparison.

Matches are *review suggestions*, never reconstructed hands or poker facts.
No implicit clock alignment, approximate matching, or OCR confidence calibration.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re

from activity_snapshot_chain import canonical_sha256
from ocr_candidates import FIELDS

_SHA = re.compile(r'[0-9a-f]{64}\Z')
_BLOCKED = ('ready_for_equity_or_ev', 'automatic_hand_boundaries_authorized',
            'automatic_clip_selection_authorized', 'strategic_error_established')
_FIELD_MAP = {'board': 'board_visible', 'hero_cards': 'hero_cards_visible',
              'pot': 'pot_observed', 'bet': 'amount_observed'}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _digest(value):
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _validate(ocr, timeline, expected_ocr_sha256, expected_timeline_sha256):
    if (not isinstance(ocr, dict) or not isinstance(timeline, dict)
            or ocr.get('schema_version') != 1 or timeline.get('schema_version') != 1
            or ocr.get('analysis_status') != 'unverified_ocr_candidates_only'
            or timeline.get('analysis_status') != 'human_reviewed_visible_timeline_not_verified_hand_reconstruction'
            or ocr.get('requires_manual_review') is not True
            or not _digest(ocr.get('recording_sha256'))
            or ocr['recording_sha256'] != timeline.get('recording_sha256')
            or not _digest(ocr.get('evidence_manifest_sha256'))
            or not _digest(timeline.get('source_review_sha256'))
            or not isinstance(ocr.get('timestamp_semantics'), str)
            or not isinstance(timeline.get('timestamp_semantics'), str)
            or 'decoded' not in ocr['timestamp_semantics']
            or 'decoded' not in timeline['timestamp_semantics']
            or any(timeline.get(flag) is not False for flag in _BLOCKED)
            or ocr.get('ready_for_equity_or_ev') is not False):
        raise ValueError('Invalid upstream status, provenance, or recording identity')
    for obj, expected in ((ocr, expected_ocr_sha256), (timeline, expected_timeline_sha256)):
        if expected is not None and (not _digest(expected) or canonical_sha256(obj) != expected):
            raise ValueError('Upstream SHA-256 mismatch')
    candidates = ocr.get('candidates')
    hands = timeline.get('hands')
    if (not isinstance(candidates, list) or len(candidates) > 2400
            or not isinstance(hands, list) or len(hands) > 10000
            or not isinstance(timeline.get('counts'), dict)
            or timeline['counts'].get('hands_human_assigned') != len(hands)):
        raise ValueError('Invalid OCR/timeline counts')
    for row in candidates:
        if (not isinstance(row, dict) or type(row.get('table_id')) is not int
                or not 1 <= row['table_id'] <= 4 or row.get('field') not in FIELDS
                or not _number(row.get('timestamp')) or row['timestamp'] < 0
                or not _digest(row.get('source_sha256'))
                or not isinstance(row.get('source_image'), str)
                or not re.fullmatch(r'(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_.-]+\.png', row['source_image'])
                or type(row.get('source_pts_ticks')) is not int
                or row['source_pts_ticks'] < 0
                or row.get('timestamp_semantics') != ocr['timestamp_semantics']
                or row.get('evidence_manifest_sha256') != ocr['evidence_manifest_sha256']
                or row.get('status') not in ('candidate_unverified', 'needs_manual_review')
                or row.get('source') != 'tesseract_manually_selected_roi'
                or not isinstance(row.get('raw_text'), str)
                or not _number(row.get('mean_engine_confidence'))
                or not 0 <= row['mean_engine_confidence'] <= 1):
            raise ValueError('Malformed OCR candidate')
        value = row.get('parsed_candidate')
        if row['field'] in ('board', 'hero_cards'):
            allowed = (3, 4, 5) if row['field'] == 'board' else (5, 6)
            if value is not None and (not isinstance(value, list) or len(value) not in allowed
                                      or len(set(map(str, value))) != len(value)
                                      or any(not isinstance(c, str) or not re.fullmatch(r'[2-9TJQKA][cdhs]', c) for c in value)):
                raise ValueError('Invalid OCR card candidate')
        elif value is not None and (not _number(value) or value < 0):
            raise ValueError('Invalid OCR amount candidate')
    seen = set()
    for hand in hands:
        if (not isinstance(hand, dict) or type(hand.get('table_id')) is not int
                or not 1 <= hand['table_id'] <= 4
                or not isinstance(hand.get('hand_id_human_assigned'), str)
                or not hand['hand_id_human_assigned']
                or not isinstance(hand.get('events'), list)
                or not hand['events'] or hand.get('human_review_required') is not True):
            raise ValueError('Invalid reviewed hand')
        identity = (hand['table_id'], hand['hand_id_human_assigned'])
        if identity in seen:
            raise ValueError('Duplicate hand identity')
        seen.add(identity)
        for event in hand['events']:
            if (not isinstance(event, dict) or not _number(event.get('timestamp'))
                    or not _number(hand.get('first_observed_pts'))
                    or not _number(hand.get('last_observed_pts'))
                    or not hand['first_observed_pts'] <= event['timestamp'] <= hand['last_observed_pts']
                    or event.get('not_authorized_for_equity_or_ev') is not True):
                raise ValueError('Invalid reviewed event')
    return candidates, hands


def _alignment(declaration, ocr, timeline):
    if declaration is None:
        return None
    if (not isinstance(declaration, dict) or declaration.get('schema_version') != 1
            or declaration.get('recording_sha256') != ocr['recording_sha256']
            or declaration.get('ocr_timestamp_semantics') != ocr['timestamp_semantics']
            or declaration.get('timeline_timestamp_semantics') != timeline['timestamp_semantics']
            or declaration.get('reviewer_confirmed_same_recording_pts_origin') is not True
            or not _number(declaration.get('ocr_pts_minus_timeline_pts_seconds'))
            or abs(declaration['ocr_pts_minus_timeline_pts_seconds']) > 3600
            or not isinstance(declaration.get('reviewer_note'), str)
            or not 1 <= len(declaration['reviewer_note'].strip()) <= 2000):
        raise ValueError('Explicit reviewer alignment required for matching')
    return float(declaration['ocr_pts_minus_timeline_pts_seconds'])


def build_ocr_timeline_review(ocr, timeline, *, alignment=None,
                              expected_ocr_sha256=None, expected_timeline_sha256=None):
    """Compare exact PTS/field matches only; conflicts are review hints."""
    candidates, hands = _validate(ocr, timeline, expected_ocr_sha256,
                                  expected_timeline_sha256)
    offset = _alignment(alignment, ocr, timeline)
    observed = defaultdict(list)
    if offset is not None:
        for hand in hands:
            for event in hand['events']:
                for field, target in _FIELD_MAP.items():
                    if event.get(target) is not None:
                        key = (hand['table_id'], round(event['timestamp'] + offset, 6), field)
                        observed[key].append((hand, event, event[target]))
    candidate_groups = defaultdict(list)
    for i, row in enumerate(candidates):
        candidate_groups[(row['table_id'], round(row['timestamp'], 6), row['field'])].append(i)
    entries = []
    for i, row in enumerate(candidates):
        key = (row['table_id'], round(row['timestamp'], 6), row['field'])
        group = candidate_groups[key]
        distinct = {json.dumps(candidates[j].get('parsed_candidate'), sort_keys=True)
                    for j in group if candidates[j].get('parsed_candidate') is not None}
        conflicting_ocr = len(distinct) > 1
        matches = observed.get(key, [])
        comparable = len(matches) == 1 and row.get('parsed_candidate') is not None
        agreement = None
        if comparable:
            expected = matches[0][2]
            candidate_value = row['parsed_candidate']
            agreement = (set(expected) == set(candidate_value) if row['field'] == 'hero_cards'
                         else expected == candidate_value)
        status = ('clock_alignment_not_declared' if offset is None else
                  'no_exact_reviewed_field_at_pts' if not matches else
                  'ambiguous_reviewed_field_matches' if len(matches) > 1 else
                  'ocr_unparseable_manual_review' if row.get('parsed_candidate') is None else
                  'ocr_candidate_agrees_with_reviewed_label_not_verified' if agreement else
                  'ocr_candidate_disagrees_with_reviewed_label_not_verified')
        entries.append({'candidate_index': i, 'table_id': row['table_id'],
                        'ocr_pts_seconds': row['timestamp'], 'field': row['field'],
                        'source_image': row['source_image'], 'source_sha256': row['source_sha256'],
                        'ocr_engine_confidence_uncalibrated': row['mean_engine_confidence'],
                        'status': status, 'same_pts_conflicting_ocr_candidates': conflicting_ocr,
                        'possible_human_assigned_hands_not_verified': [
                            {'hand_id': h['hand_id_human_assigned'],
                             'observation_index': e['observation_index']} for h, e, _ in matches],
                        'poker_event_recognized': False, 'requires_manual_review': True})
    return {'schema_version': 1,
            'analysis_status': 'review_only_ocr_to_human_timeline_exact_pts_comparison',
            'recording_sha256': ocr['recording_sha256'],
            'source_ocr_report_sha256': canonical_sha256(ocr),
            'source_reviewed_timeline_sha256': canonical_sha256(timeline),
            'source_pts_alignment_declaration_sha256': (canonical_sha256(alignment)
                                                        if alignment is not None else None),
            'pts_alignment_declared_not_verified': offset is not None,
            'timestamp_match_method': 'rounded_six_decimals_exact_only_not_fuzzy',
            'candidates': entries,
            'counts': {'total': len(entries), 'conflicting_ocr_candidates': sum(
                x['same_pts_conflicting_ocr_candidates'] for x in entries),
                'reviewed_label_disagreements': sum('disagrees' in x['status'] for x in entries)},
            'requires_manual_review': True, 'ready_for_equity_or_ev': False,
            'automatic_hand_boundaries_authorized': False,
            'automatic_clip_selection_authorized': False,
            'strategic_error_established': False,
            'warning': 'OCR/label agreement is not ground truth. Clock offset is reviewer-declared. '
                       'No inferred hands, card truth, actions, EV, or errors.'}


def write_ocr_timeline_review(ocr_json, timeline_json, output_json, *, alignment_json=None,
                              **kwargs):
    source, timeline_path, destination = map(Path, (ocr_json, timeline_json, output_json))
    paths = [source, timeline_path] + ([Path(alignment_json)] if alignment_json else [])
    if (any(p.is_symlink() or not p.is_file() for p in paths)
            or destination.is_symlink() or destination.exists()
            or any(destination.resolve() == p.resolve() for p in paths)):
        raise ValueError('Require regular inputs and a new output path')
    reports = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
    result = build_ocr_timeline_review(reports[0], reports[1],
                                      alignment=reports[2] if len(reports) == 3 else None,
                                      **kwargs)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8') as fp:
        json.dump(result, fp, indent=2, ensure_ascii=False, allow_nan=False)
        fp.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ocr_candidates_json')
    parser.add_argument('reviewed_timeline_json')
    parser.add_argument('output_json')
    parser.add_argument('--alignment-json')
    args = parser.parse_args()
    result = write_ocr_timeline_review(args.ocr_candidates_json, args.reviewed_timeline_json,
                                       args.output_json, alignment_json=args.alignment_json)
    print(json.dumps(result['counts']))
