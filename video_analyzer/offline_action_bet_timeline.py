"""Offline *evidence-only* timeline of PLO5/PLO6 actions, bets and pot OCR.

Usage: python offline_action_bet_timeline.py HAND_DRAFTS_JSON NEW_REPORT_JSON

Observations are timestamped OCR assertions, NOT an ordered betting history.
No actor/seat, contribution, legality, equity or EV is inferred.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

SHA = re.compile(r'[a-f0-9]{64}\Z')
IDENT = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
AMOUNT = re.compile(r'(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?\Z')
CARD = re.compile(r'[2-9TJQKA][cdhs]\Z')
FIELDS = {'hero_cards', 'board', 'pot', 'bet', 'stack', 'action'}
ACTIONS = {'fold', 'check', 'call', 'bet', 'raise', 'all-in'}
MAX_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 4000


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'duplicate JSON key')
        out[key] = value
    return out


def valid_time(t):
    return type(t) in (int, float) and math.isfinite(t) and 0 <= t <= 86400


def valid_int(i):
    return type(i) is int and i >= 0


def validate_value(field, value, variant):
    require(type(value) is str and 0 < len(value) <= 128 and value == value.strip(),
            'invalid reviewed value')
    if field in ('pot', 'bet', 'stack'):
        require(AMOUNT.fullmatch(value) is not None, 'invalid amount')
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValueError('invalid amount') from exc
    if field == 'action':
        require(value in ACTIONS, 'invalid action')
        return value
    cards = value.split(' ')
    require(all(CARD.fullmatch(c) for c in cards) and len(set(cards)) == len(cards),
            'invalid cards')
    if field == 'hero_cards':
        require(len(cards) == (5 if variant == 'PLO5' else 6), 'invalid hero card count')
    else:
        require(1 <= len(cards) <= 5, 'invalid board count')
    return cards


def inspect(doc):
    require(type(doc) is dict and type(doc.get('schema_version')) is int
            and doc['schema_version'] == 1
            and doc.get('analysis_status') == 'offline_reviewed_hand_drafts_only'
            and doc.get('hands_reconstructed') is False
            and doc.get('ready_for_equity_or_ev') is False
            and type(doc.get('hands')) is list and 1 <= len(doc['hands']) <= 200,
            'invalid draft provenance')
    for name in ('source_reviewed_report_sha256', 'source_boundaries_sha256',
                 'source_roi_ocr_report_sha256'):
        require(type(doc.get(name)) is str and SHA.fullmatch(doc[name]),
                'missing source provenance')
    results, seen_hands, globally_used_indices, intervals = [], set(), set(), {i: [] for i in range(1, 5)}
    total = 0
    for hand in doc['hands']:
        require(type(hand) is dict and type(hand.get('hand_id')) is str
                and IDENT.fullmatch(hand['hand_id']) is not None
                and hand['hand_id'] not in seen_hands
                and type(hand.get('table_id')) is int and 1 <= hand['table_id'] <= 4
                and hand.get('variant') in ('PLO5', 'PLO6')
                and hand.get('boundary_origin') == 'manual_unverified'
                and hand.get('ready_for_equity_or_ev') is False
                and hand.get('status') == 'draft_requires_human_reconstruction'
                and valid_time(hand.get('start_seconds')) and valid_time(hand.get('end_seconds'))
                and hand['start_seconds'] < hand['end_seconds']
                and type(hand.get('reviewed_fields')) is dict
                and set(hand['reviewed_fields']) <= FIELDS
                and type(hand.get('observation_indices')) is list
                and type(hand.get('unresolved_indices')) is list,
                'invalid draft hand')
        seen_hands.add(hand['hand_id'])
        table = hand['table_id']
        intervals[table].append((hand['start_seconds'], hand['end_seconds']))
        indices = hand['observation_indices']
        unresolved = hand['unresolved_indices']
        require(len(indices) <= MAX_ENTRIES and all(valid_int(i) for i in indices)
                and len(indices) == len(set(indices))
                and not (set(indices) & globally_used_indices)
                and all(valid_int(i) for i in unresolved)
                and len(unresolved) == len(set(unresolved))
                and set(unresolved) <= set(indices), 'invalid observation index provenance')
        globally_used_indices.update(indices)
        events, seen_entries = [], set()
        for field, entries in hand['reviewed_fields'].items():
            require(type(entries) is list, 'invalid field observations')
            total += len(entries)
            require(total <= MAX_ENTRIES, 'too many observations')
            for entry in entries:
                require(type(entry) is dict
                        and entry.get('review') in ('confirmed', 'corrected')
                        and valid_int(entry.get('proposal_index'))
                        and entry['proposal_index'] in indices
                        and entry['proposal_index'] not in unresolved
                        and entry['proposal_index'] not in seen_entries
                        and valid_time(entry.get('timestamp_seconds'))
                        and hand['start_seconds'] <= entry['timestamp_seconds'] < hand['end_seconds'],
                        'invalid reviewed event provenance')
                seen_entries.add(entry['proposal_index'])
                parsed = validate_value(field, entry.get('value'), hand['variant'])
                events.append({'timestamp_seconds': entry['timestamp_seconds'],
                               'proposal_index': entry['proposal_index'], 'field': field,
                               'value': entry['value'], 'review': entry['review'], '_parsed': parsed})
        require(set(indices) == seen_entries | set(unresolved),
                'missing reviewed or unresolved observation')
        events.sort(key=lambda x: (x['timestamp_seconds'], x['proposal_index']))
        warnings = set()
        board = [e for e in events if e['field'] == 'board']
        pots = [e for e in events if e['field'] == 'pot']
        bets = [e for e in events if e['field'] == 'bet']
        actions = [e for e in events if e['field'] == 'action']
        if not actions:
            warnings.add('no_visible_action')
        if not board:
            warnings.add('no_visible_board')
        if unresolved:
            warnings.add('unresolved_ocr')
        for a, b in zip(board, board[1:]):
            if len(b['_parsed']) < len(a['_parsed']):
                warnings.add('board_regressed')
            elif b['_parsed'][:len(a['_parsed'])] != a['_parsed']:
                warnings.add('board_changed_nonprefix')
        for a, b in zip(pots, pots[1:]):
            if b['_parsed'] < a['_parsed']:
                warnings.add('pot_decreased_between_observations')
            if b['timestamp_seconds'] == a['timestamp_seconds'] and b['_parsed'] != a['_parsed']:
                warnings.add('conflicting_simultaneous_pot_values')
        if any(len(b['_parsed']) in (1, 2) for b in board):
            warnings.add('partial_board_snapshot')
        by_timestamp = {}
        for a in actions:
            by_timestamp.setdefault(a['timestamp_seconds'], set()).add(a['value'])
        if any(len(s) > 1 for s in by_timestamp.values()):
            warnings.add('conflicting_simultaneous_actions')
        event_out = []
        paired_bets = {}
        for e in events:
            phase = 'street_unknown'
            if e['field'] != 'board':
                prior = [b for b in board if b['timestamp_seconds'] <= e['timestamp_seconds']]
                if prior:
                    count = len(prior[-1]['_parsed'])
                    phase = {3: 'flop_board_observed', 4: 'turn_board_observed',
                             5: 'river_board_observed'}.get(count, 'partial_board_observed')
            elif len(e['_parsed']) in (3, 4, 5):
                phase = {3: 'flop_board_observed', 4: 'turn_board_observed',
                         5: 'river_board_observed'}[len(e['_parsed'])]
            record = {'timestamp_seconds': e['timestamp_seconds'],
                      'proposal_index': e['proposal_index'], 'field': e['field'],
                      'value': e['value'], 'review': e['review'],
                      'board_phase_evidence': phase}
            if e['field'] == 'action':
                nearby = sorted((b for b in bets if abs(b['timestamp_seconds'] - e['timestamp_seconds']) <= 2),
                                key=lambda b: (abs(b['timestamp_seconds'] - e['timestamp_seconds']),
                                               b['proposal_index']))
                record['nearby_bet_proposal_indices'] = [b['proposal_index'] for b in nearby]
                record['actor_identified'] = False
                record['action_legality_verified'] = False
                if not nearby and e['value'] in ('bet', 'raise', 'call', 'all-in'):
                    warnings.add('action_without_nearby_bet_ocr')
                for b in nearby:
                    paired_bets[b['proposal_index']] = paired_bets.get(b['proposal_index'], 0) + 1
            event_out.append(record)
        if any(count > 1 for count in paired_bets.values()):
            warnings.add('bet_observation_near_multiple_actions')
        results.append({'hand_id': hand['hand_id'], 'table_id': table,
                        'variant': hand['variant'], 'start_seconds': hand['start_seconds'],
                        'end_seconds': hand['end_seconds'], 'events': event_out,
                        'unresolved_indices': sorted(unresolved), 'warnings': sorted(warnings),
                        'actor_and_betting_sequence_verified': False,
                        'ready_for_equity_or_ev': False,
                        'status': 'requires_manual_action_and_bet_reconstruction'})
    for table_intervals in intervals.values():
        table_intervals.sort()
        require(all(a[1] <= b[0] for a, b in zip(table_intervals, table_intervals[1:])),
                'overlapping hand boundaries')
    results.sort(key=lambda h: (h['table_id'], h['start_seconds'], h['hand_id']))
    return {'schema_version': 1, 'analysis_status': 'offline_action_bet_evidence_only',
            'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
            'confidence': 'uncalibrated_ocr_review_not_probability',
            'source_reviewed_report_sha256': doc['source_reviewed_report_sha256'],
            'source_boundaries_sha256': doc['source_boundaries_sha256'],
            'hands': results,
            'warning': ('Board phase reflects last visible board snapshot only; no actor, '
                        'betting legality, range, equity or EV is inferred.')}


def run(source, destination):
    source, destination = Path(source), Path(destination)
    require(source.is_file() and not source.is_symlink()
            and 0 < source.stat().st_size <= MAX_BYTES
            and destination.parent.is_dir() and not destination.parent.is_symlink()
            and not destination.exists() and not destination.is_symlink(),
            'unsafe source or output')
    raw = source.read_bytes()
    require(len(raw) <= MAX_BYTES, 'source too large')
    doc = json.loads(raw, object_pairs_hook=unique,
                     parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    result = inspect(doc)
    result['source_hand_drafts_sha256'] = hashlib.sha256(raw).hexdigest()
    encoded = (json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf8')
    require(hashlib.sha256(source.read_bytes()).hexdigest() == result['source_hand_drafts_sha256'],
            'source changed')
    # Exclusive creation prevents accidental overwrites, including a symlink at the output path.
    with destination.open('xb') as stream:
        stream.write(encoded)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('hand_drafts_json'); p.add_argument('new_report_json')
    args = p.parse_args(argv)
    result = run(args.hand_drafts_json, args.new_report_json)
    print(json.dumps({'hands': len(result['hands']), 'ready_for_equity_or_ev': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
