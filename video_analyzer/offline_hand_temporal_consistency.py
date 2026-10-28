"""Validate chronological board observations in offline PLO5/PLO6 hand drafts.

This produces review warnings, never verified hands or permission to calculate EV.
Usage: python offline_hand_temporal_consistency.py HAND_DRAFTS_JSON OUTPUT_JSON
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def _unique(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError('duplicate JSON key')
        d[k] = v
    return d


def inspect(data):
    if (type(data) is not dict or data.get('schema_version') != 1
        or data.get('analysis_status') != 'offline_reviewed_hand_drafts_only'
        or data.get('ready_for_equity_or_ev') is not False
        or data.get('hands_reconstructed') is not False
        or type(data.get('hands')) is not list or not 1 <= len(data['hands']) <= 200):
        raise ValueError('invalid draft provenance')
    output, seen = [], set()
    for hand in data['hands']:
        if (type(hand) is not dict or type(hand.get('hand_id')) is not str
            or not 1 <= len(hand['hand_id']) <= 64 or hand['hand_id'] in seen
            or type(hand.get('table_id')) is not int or not 1 <= hand['table_id'] <= 4
            or hand.get('variant') not in ('PLO5', 'PLO6')
            or hand.get('boundary_origin') != 'manual_unverified'
            or hand.get('ready_for_equity_or_ev') is not False
            or type(hand.get('reviewed_fields')) is not dict
            or type(hand.get('unresolved_indices')) is not list):
            raise ValueError('invalid hand')
        seen.add(hand['hand_id'])
        start, end = hand.get('start_seconds'), hand.get('end_seconds')
        if (type(start) not in (int, float) or type(end) not in (int, float)
            or not math.isfinite(start) or not math.isfinite(end)
            or not 0 <= start < end <= 86400):
            raise ValueError('invalid timestamps')
        warnings = set()
        events = []
        for field in ('board', 'hero_cards'):
            entries = hand['reviewed_fields'].get(field, [])
            if type(entries) is not list or len(entries) > 2000:
                raise ValueError('invalid field entries')
            for entry in entries:
                if (type(entry) is not dict or entry.get('review') not in ('confirmed', 'corrected')
                    or type(entry.get('value')) is not str
                    or type(entry.get('timestamp_seconds')) not in (int, float)
                    or not math.isfinite(entry['timestamp_seconds'])
                    or not start <= entry['timestamp_seconds'] < end):
                    raise ValueError('invalid reviewed event')
                cards = entry['value'].split(' ')
                if (not cards or len(cards) != len(set(cards))
                    or any(len(c) != 2 or c[0] not in '23456789TJQKA'
                           or c[1] not in 'cdhs' for c in cards)
                    or (field == 'hero_cards' and len(cards) != (5 if hand['variant'] == 'PLO5' else 6))
                    or (field == 'board' and not 1 <= len(cards) <= 5)):
                    raise ValueError('invalid cards')
                events.append((entry['timestamp_seconds'], field, cards))
        events.sort(key=lambda e: (e[0], e[1]))
        boards = [e[2] for e in events if e[1] == 'board']
        heroes = [e[2] for e in events if e[1] == 'hero_cards']
        if len({frozenset(x) for x in heroes}) > 1:
            warnings.add('hero_cards_changed')
        if any(set(h) & set(b) for h in heroes for b in boards):
            warnings.add('hero_board_collision')
        for a, b in zip(boards, boards[1:]):
            if len(b) < len(a):
                warnings.add('board_regressed')
            elif b[:len(a)] != a:
                warnings.add('board_nonprefix_change')
            if len(b) > len(a) + 1:
                warnings.add('missing_intermediate_street')
        if any(len(b) in (1, 2) for b in boards):
            warnings.add('partial_board')
        if hand['unresolved_indices']:
            warnings.add('unresolved_ocr')
        output.append({'hand_id': hand['hand_id'], 'table_id': hand['table_id'],
                       'warnings': sorted(warnings), 'board_snapshots': len(boards),
                       'status': 'requires_manual_review', 'ready_for_equity_or_ev': False})
    return {'schema_version': 1, 'analysis_status': 'offline_temporal_checks_only',
            'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
            'hands': output}


def run(source, destination):
    source, destination = Path(source), Path(destination)
    if (not source.is_file() or source.is_symlink() or source.stat().st_size > 8*1024*1024
        or destination.exists() or not destination.parent.is_dir()):
        raise ValueError('unsafe input or destination')
    raw = source.read_bytes()
    data = json.loads(raw, object_pairs_hook=_unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    result = inspect(data)
    result['source_hand_drafts_sha256'] = hashlib.sha256(raw).hexdigest()
    destination.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf8')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('drafts'); p.add_argument('output')
    a = p.parse_args()
    print(json.dumps({'hands': len(run(a.drafts, a.output)['hands'])}))
