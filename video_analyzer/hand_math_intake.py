"""Offline, fail-closed worksheet from visually reviewed *unverified* hand spans.

This module never executes equity/EV or promotes a still verdict to a verified
hand. All mathematical scenario values must be entered and independently
attested by a human in a separate, evidence-checked workflow.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from hand_action_pts_evidence import FALSE_FLAGS

VERDICTS = ('pending', 'confirmed_visual', 'rejected_visual', 'uncertain', 'unreviewable')
REQUIRED_REVIEWED_FIELDS = ('hero_cards', 'board', 'observed_action',
                            'pot_before_action', 'call_amount')
MAX_SPANS = 2048
MAX_ANNOTATIONS = 3000
MAX_BYTES = 16 * 1024 * 1024


def _digest(value):
    if (type(value) is not str or len(value) != 64
            or any(c not in '0123456789abcdef' for c in value)):
        raise ValueError('Invalid SHA-256 digest')
    return value


def _time(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid nonnegative timestamp')
    return float(value)


def validate_history(history):
    """Check report structure and internal consistency, not source authenticity."""
    if (type(history) is not dict or history.get('schema_version') != 1
            or history.get('analysis_status') !=
            'visual_verdicts_linked_to_unverified_hand_history_no_math'
            or history.get('requires_manual_review') is not True
            or any(history.get(flag) is not False for flag in FALSE_FLAGS)):
        raise ValueError('Expected unverified, no-math visual history')
    for field in ('recording_sha256', 'source_navigation_sha256',
                  'source_review_sha256', 'source_gallery_sha256',
                  'source_visual_verdicts_sha256'):
        _digest(history.get(field))
    entries = history.get('entries')
    if type(entries) is not list or not 1 <= len(entries) <= MAX_SPANS:
        raise ValueError('Invalid hand span count')
    seen, tally, total = set(), {v: 0 for v in VERDICTS}, 0
    for entry in entries:
        if type(entry) is not dict or type(entry.get('entry_id')) is not str:
            raise ValueError('Invalid hand span')
        ident = entry['entry_id']
        if not ident or len(ident) > 128 or ident in seen:
            raise ValueError('Duplicate or invalid span ID')
        seen.add(ident)
        table = entry.get('table_id')
        if type(table) is not int or not 1 <= table <= 4:
            raise ValueError('Invalid table ID')
        start, end = _time(entry.get('start_human_seconds')), _time(entry.get('end_human_seconds'))
        if start >= end:
            raise ValueError('Invalid span interval')
        if (type(entry.get('contains_unresolved_interior_candidates')) is not bool
                or entry.get('hand_reconstruction_verified') is not False
                or entry.get('ready_for_equity_or_ev') is not False):
            raise ValueError('Span must remain unverified')
        annotations = entry.get('annotations')
        if type(annotations) is not list:
            raise ValueError('Invalid annotations')
        keys = set()
        for annotation in annotations:
            if type(annotation) is not dict:
                raise ValueError('Invalid annotation')
            kind, item = annotation.get('kind'), annotation.get('item')
            if not ((kind == 'field' and type(item) is str and 0 < len(item) <= 100)
                    or (kind == 'action' and type(item) is int and item >= 0)):
                raise ValueError('Invalid annotation key')
            key = (kind, item)
            if key in keys:
                raise ValueError('Duplicate annotation key')
            keys.add(key)
            verdict = annotation.get('visual_verdict')
            if verdict not in VERDICTS or type(verdict) is not str:
                raise ValueError('Invalid visual verdict')
            tally[verdict] += 1
            total += 1
            if total > MAX_ANNOTATIONS:
                raise ValueError('Too many annotations')
            if annotation.get('ready_for_equity_or_ev') is not False:
                raise ValueError('Annotation cannot authorize mathematics')
            if (annotation.get('evidence_status') !=
                    ('human_still_review_only_not_hand_verified' if verdict == 'confirmed_visual'
                     else 'not_visually_confirmed')):
                raise ValueError('Contradictory evidence status')
            frame = annotation.get('still_sha256')
            if frame is not None:
                _digest(frame)
            if verdict == 'confirmed_visual' and frame is None:
                raise ValueError('Confirmed still missing hash')
            stamp = annotation.get('requested_pts_seconds')
            if stamp is not None:
                _time(stamp)
    counts = history.get('counts')
    if (type(counts) is not dict or counts.get('spans') != len(entries)
            or counts.get('annotations') != total
            or any(counts.get(v) != tally[v] for v in VERDICTS)):
        raise ValueError('Visual history counts inconsistent')
    return tally


def build(history, history_sha256):
    """Create *empty* manual scenario forms bound to the source JSON digest."""
    _digest(history_sha256)
    validate_history(history)
    tasks = []
    for entry in history['entries']:
        counts = {v: sum(a['visual_verdict'] == v for a in entry['annotations'])
                  for v in VERDICTS}
        blockers = ['independent_complete_hand_and_decision_attestation_required',
                    'five_required_fields_not_manually_attested',
                    'opponent_range_and_model_parameters_not_supplied']
        if entry['contains_unresolved_interior_candidates']:
            blockers.append('possible_unresolved_hand_boundary')
        if counts['uncertain'] or counts['rejected_visual'] or counts['unreviewable'] or counts['pending']:
            blockers.append('incomplete_or_disputed_visual_annotations')
        tasks.append({
            'entry_id': entry['entry_id'], 'table_id': entry['table_id'],
            'span_seconds': [entry['start_human_seconds'], entry['end_human_seconds']],
            'source_annotations': [{
                'kind': a['kind'], 'item': a['item'],
                'visual_verdict': a['visual_verdict'],
                'still_sha256': a['still_sha256'],
                'source_kind': a.get('source_kind'),
            } for a in entry['annotations']],
            'verdict_counts': counts, 'blocking_reasons': blockers,
            'manual_scenario_draft': {
                'timestamp': None, 'human_confirmed': False,
                'observation_confidence': None,
                'reviewed_fields': {name: {'value': None, 'confidence': None,
                                          'source_timestamp': None,
                                          'source': None, 'human_confirmed': False}
                                    for name in REQUIRED_REVIEWED_FIELDS},
                'call_range': [], 'fold_probability': None,
                'monte_carlo_trials': None, 'monte_carlo_seed': None,
                'model_notes': '',
            },
            'hand_reconstruction_verified': False,
            'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
        })
    return {
        'schema_version': 1,
        'analysis_status': 'manual_math_scenario_intake_blocked_no_calculation',
        'recording_sha256': history['recording_sha256'],
        'source_visual_history_sha256': history_sha256,
        'source_visual_verdicts_sha256': history['source_visual_verdicts_sha256'],
        'tasks': tasks, 'counts': {'spans': len(tasks), 'math_ready': 0},
        'requires_independent_evidence_revalidation': True,
        'ready_for_equity_or_ev': False,
        'automatic_clip_selection_authorized': False,
        'warning': ('This is an untrusted preparation worksheet, not a mathematical '
                    'manifest. Do not feed it to an equity/EV engine. Re-audit the '
                    'original video and obtain independent human attestation.'),
    }


def export(history_path, output_path):
    source, target = Path(history_path), Path(output_path)
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_BYTES:
        raise ValueError('Invalid input file')
    if target.exists() or target.is_symlink() or source.resolve() == target.resolve():
        raise ValueError('Output must be new and different from input')
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        history = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid UTF-8 JSON') from exc
    result = build(history, digest)
    if source.read_bytes() != raw:
        raise ValueError('Source changed during validation')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as fp:
        json.dump(result, fp, indent=2, ensure_ascii=False, allow_nan=False)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('visual_history_json')
    parser.add_argument('output_json')
    args = parser.parse_args(argv)
    result = export(args.visual_history_json, args.output_json)
    print(json.dumps({'analysis_status': result['analysis_status'], 'counts': result['counts']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
