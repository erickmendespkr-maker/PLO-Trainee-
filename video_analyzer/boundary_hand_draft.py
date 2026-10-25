"""Conservative, offline hand-review worksheet for navigation-only PLO spans.

Neither OCR hints nor human-entered fields authorize equity, EV or clips.
The original navigation report is required again when validating an edited draft.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from boundary_history_bridge import FALSE

FIELDS = ('variant', 'hero_cards_visible', 'board_visible', 'pot_observed',
          'effective_stack_observed')
ACTIONS = frozenset(('fold', 'check', 'call', 'bet', 'raise', 'showdown'))
RANKS = frozenset('23456789TJQKA')
SUITS = frozenset('cdhs')
MAX_SPANS = 2048
MAX_ACTIONS = 100


def _num(value, *, max_value=None):
    return (type(value) in (int, float) and math.isfinite(value) and value >= 0
            and (max_value is None or value <= max_value))


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _card_list(value, lengths):
    if (not isinstance(value, list) or len(value) not in lengths
            or any(not isinstance(c, str) or len(c) != 2 or c[0] not in RANKS
                   or c[1] not in SUITS for c in value)
            or len(set(value)) != len(value)):
        raise ValueError('Invalid visible cards')


def _field():
    return {'value': None, 'confidence': None, 'source_pts_seconds': None,
            'source_kind': 'unknown', 'human_confirmed': False}


def build_template(navigation, source_sha256):
    """Generate an editable worksheet without inventing a hand or any cards."""
    if (not isinstance(navigation, dict) or navigation.get('schema_version') != 2
            or navigation.get('analysis_status') != 'navigation_only_unverified_spans'
            or navigation.get('requires_manual_review') is not True
            or not _sha(source_sha256) or not _sha(navigation.get('recording_sha256'))
            or not _sha(navigation.get('source_packet_sha256'))
            or any(navigation.get(k) is not False for k in FALSE)):
        raise ValueError('Invalid navigation source or authority flags')
    spans = navigation.get('candidate_spans')
    if not isinstance(spans, list) or len(spans) > MAX_SPANS:
        raise ValueError('Invalid span budget')
    entries, seen, last_end = [], set(), {}
    for span in spans:
        if not isinstance(span, dict):
            raise ValueError('Invalid span')
        table, index = span.get('table_id'), span.get('span_index')
        start, end = span.get('start_human_seconds'), span.get('end_human_seconds')
        key = (table, index)
        if (type(table) is not int or not 1 <= table <= 4
                or type(index) is not int or index < 0 or key in seen
                or not _num(start) or not _num(end) or start >= end
                or start < last_end.get(table, -1)):
            raise ValueError('Invalid, duplicate or overlapping span')
        seen.add(key)
        last_end[table] = end
        ids = span.get('source_task_ids')
        interior = span.get('interior_candidates')
        if (not isinstance(ids, list) or len(ids) != 2 or any(
                not isinstance(x, str) or not x for x in ids)
                or ids[0] == ids[1] or not isinstance(interior, list)
                or type(span.get('contains_unresolved_interior_candidates')) is not bool
                or span.get('hand_id') is not None or span.get('cards') is not None
                or span.get('actions') != [] or span.get('equity') is not None
                or span.get('ev') is not None or span.get('requires_manual_review') is not True):
            raise ValueError('Span contains unsupported assertions')
        interior_ids = []
        unresolved = False
        for item in interior:
            if (not isinstance(item, dict) or not isinstance(item.get('task_id'), str)
                    or not item['task_id'] or item['task_id'] in ids
                    or item['task_id'] in interior_ids
                    or item.get('review_status') not in ('pending', 'uncertain', 'rejected_transition')
                    or type(item.get('could_hide_additional_transition')) is not bool):
                raise ValueError('Invalid interior candidate')
            interior_ids.append(item['task_id'])
            unresolved |= item['could_hide_additional_transition']
        if unresolved != span['contains_unresolved_interior_candidates']:
            raise ValueError('Unresolved boundary flags disagree')
        entries.append({
            'entry_id': f'table_{table:02d}_span_{index:04d}',
            'table_id': table, 'span_index': index,
            'start_human_seconds': start, 'end_human_seconds': end,
            'source_task_ids': list(ids), 'interior_candidate_ids': interior_ids,
            'contains_unresolved_interior_candidates': unresolved,
            'hand_id': None, 'hand_reconstruction_verified': False,
            'reviewer': '', 'reviewer_notes': '',
            'fields': {name: _field() for name in FIELDS}, 'actions': [],
            'ready_for_equity_or_ev': False})
    return {'schema_version': 1,
            'analysis_status': 'manual_hand_history_draft_unverified_no_math',
            'source_navigation_sha256': source_sha256,
            'recording_sha256': navigation['recording_sha256'],
            'entries': entries, 'requires_manual_review': True,
            **{k: False for k in FALSE}}


def _check_field(name, record, start, end):
    if not isinstance(record, dict) or set(record) != set(_field()):
        raise ValueError('Invalid field record')
    value = record['value']
    confidence, pts = record['confidence'], record['source_pts_seconds']
    kind, confirmed = record['source_kind'], record['human_confirmed']
    if type(confirmed) is not bool or kind not in ('unknown', 'hypothesis', 'manual_video_review'):
        raise ValueError('Invalid field provenance')
    if value is None:
        if record != _field():
            raise ValueError('Unknown fields must remain fully unknown')
        return
    if not _num(confidence, max_value=1):
        raise ValueError('Confidence required for supplied value')
    if pts is not None and (not _num(pts) or not start <= pts <= end):
        raise ValueError('Out-of-span field PTS')
    if kind == 'unknown' or (confirmed and (kind != 'manual_video_review' or pts is None)):
        raise ValueError('Human confirmation needs in-span manual video reference')
    if name == 'variant':
        if type(value) is not str or value not in ('PLO5', 'PLO6'):
            raise ValueError('Invalid PLO variant')
    elif name == 'hero_cards_visible':
        _card_list(value, (5, 6))
    elif name == 'board_visible':
        _card_list(value, (0, 3, 4, 5))
    elif not _num(value):
        raise ValueError('Invalid observed monetary amount')


def validate_review(navigation, source_sha256, edited):
    """Validate editable fields against re-derived immutable navigation metadata."""
    original = build_template(navigation, source_sha256)
    if not isinstance(edited, dict) or set(edited) != set(original):
        raise ValueError('Unexpected root fields')
    for key in original:
        if key != 'entries' and (type(edited[key]) is not type(original[key])
                                 or edited[key] != original[key]):
            raise ValueError('Protected root field changed: ' + key)
    entries = edited['entries']
    if not isinstance(entries, list) or len(entries) != len(original['entries']):
        raise ValueError('Entry count mismatch')
    confirmed_fields, action_count = 0, 0
    for row, expected in zip(entries, original['entries']):
        if not isinstance(row, dict) or set(row) != set(expected):
            raise ValueError('Unexpected entry fields')
        for key in expected:
            if key not in ('reviewer', 'reviewer_notes', 'fields', 'actions') and (
                    type(row[key]) is not type(expected[key]) or row[key] != expected[key]):
                raise ValueError('Protected entry field changed: ' + key)
        if (not isinstance(row['reviewer'], str) or len(row['reviewer']) > 80
                or not isinstance(row['reviewer_notes'], str) or len(row['reviewer_notes']) > 2000
                or not isinstance(row['fields'], dict) or set(row['fields']) != set(FIELDS)):
            raise ValueError('Invalid reviewer or field set')
        start, end = expected['start_human_seconds'], expected['end_human_seconds']
        row_has_annotations = False
        for name in FIELDS:
            record = row['fields'][name]
            _check_field(name, record, start, end)
            confirmed_fields += int(record['human_confirmed'])
            row_has_annotations |= record['value'] is not None
        variant = row['fields']['variant']['value']
        hero = row['fields']['hero_cards_visible']['value']
        board = row['fields']['board_visible']['value']
        if hero is not None and variant is not None and len(hero) != int(variant[-1]):
            raise ValueError('Visible private card count conflicts with variant')
        if hero is not None and board is not None and len(set(hero + board)) != len(hero + board):
            raise ValueError('Duplicate visible card across board and private cards')
        actions = row['actions']
        if not isinstance(actions, list) or len(actions) > MAX_ACTIONS:
            raise ValueError('Invalid action budget')
        last_pts = start
        for action in actions:
            if not isinstance(action, dict) or set(action) != {
                    'timestamp_seconds', 'actor', 'action', 'amount', 'confidence',
                    'source_kind', 'human_confirmed'}:
                raise ValueError('Invalid action structure')
            pts, name, amount = action['timestamp_seconds'], action['action'], action['amount']
            if (not _num(pts) or not last_pts <= pts <= end
                    or type(name) is not str or name not in ACTIONS
                    or not isinstance(action['actor'], str) or not 1 <= len(action['actor']) <= 80
                    or (amount is not None and not _num(amount))
                    or not _num(action['confidence'], max_value=1)
                    or type(action['human_confirmed']) is not bool
                    or action['source_kind'] not in ('hypothesis', 'manual_video_review')
                    or (action['human_confirmed'] and action['source_kind'] != 'manual_video_review')):
                raise ValueError('Invalid or unproven action')
            last_pts = pts
            action_count += 1
        if (row_has_annotations or actions) and not row['reviewer'].strip():
            raise ValueError('Reviewer identity required for annotated data')
    return {'schema_version': 1,
            'analysis_status': 'manual_hand_history_review_unverified_no_math',
            'source_navigation_sha256': source_sha256,
            'recording_sha256': original['recording_sha256'],
            'entries': entries,
            'counts': {'spans': len(entries), 'human_confirmed_fields': confirmed_fields,
                       'human_reported_actions': action_count},
            'requires_manual_review': True, **{k: False for k in FALSE}}


def _read(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8_000_000:
        raise ValueError('Unsafe input file')
    def no_duplicates(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('Duplicate JSON key')
            obj[key] = value
        return obj
    raw = path.read_bytes()
    return (json.loads(raw, object_pairs_hook=no_duplicates,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON'))),
            hashlib.sha256(raw).hexdigest())


def _write(path, obj):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError('Output already exists')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def export_template(navigation_path, output_path):
    nav, digest = _read(navigation_path)
    result = build_template(nav, digest)
    _write(output_path, result)
    return result


def export_review(navigation_path, edited_path, output_path):
    nav, digest = _read(navigation_path)
    edited, _ = _read(edited_path)
    result = validate_review(nav, digest, edited)
    _write(output_path, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('template', 'review'))
    parser.add_argument('navigation')
    parser.add_argument('edited_or_output')
    parser.add_argument('output', nargs='?')
    args = parser.parse_args()
    if args.mode == 'template':
        if args.output is not None:
            parser.error('template expects navigation and output')
        result = export_template(args.navigation, args.edited_or_output)
    else:
        if args.output is None:
            parser.error('review expects navigation, edited and output')
        result = export_review(args.navigation, args.edited_or_output, args.output)
    print(json.dumps({'analysis_status': result['analysis_status'],
                      'entries': len(result['entries'])}))


if __name__ == '__main__':
    main()
