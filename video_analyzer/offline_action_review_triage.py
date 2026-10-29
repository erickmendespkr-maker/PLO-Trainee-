"""Rank recorded PLO5/PLO6 OCR actions for *human review*, never for EV.

Usage: python offline_action_review_triage.py TIMELINE_JSON NEW_QUEUE_JSON
No actor, hand legality, ranges, equity, EV or clip authorization is inferred.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

SHA = re.compile(r'[a-f0-9]{64}\Z')
ACTIONS = {'check': 1, 'fold': 2, 'call': 3, 'bet': 4, 'raise': 5, 'all-in': 6}


def check(ok, message):
    if not ok:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for k, v in pairs:
        check(k not in result, 'duplicate JSON key')
        result[k] = v
    return result


def valid_time(t):
    return type(t) in (int, float) and math.isfinite(t) and 0 <= t <= 86400


def build(doc):
    check(type(doc) is dict and doc.get('schema_version') == 1
          and type(doc['schema_version']) is int
          and doc.get('analysis_status') == 'offline_action_bet_evidence_only'
          and doc.get('hands_reconstructed') is False
          and doc.get('ready_for_equity_or_ev') is False
          and doc.get('confidence') == 'uncalibrated_ocr_review_not_probability'
          and type(doc.get('hands')) is list and 1 <= len(doc['hands']) <= 200,
          'untrusted timeline')
    for name in ('source_reviewed_report_sha256', 'source_boundaries_sha256'):
        check(type(doc.get(name)) is str and SHA.fullmatch(doc[name]), 'invalid source hash')
    candidates, seen, count, intervals = [], set(), 0, {i: [] for i in range(1, 5)}
    for hand in doc['hands']:
        check(type(hand) is dict and type(hand.get('hand_id')) is str
              and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', hand['hand_id'])
              and hand['hand_id'] not in seen
              and type(hand.get('table_id')) is int and 1 <= hand['table_id'] <= 4
              and hand.get('variant') in ('PLO5', 'PLO6')
              and valid_time(hand.get('start_seconds'))
              and valid_time(hand.get('end_seconds'))
              and hand['start_seconds'] < hand['end_seconds']
              and hand.get('ready_for_equity_or_ev') is False
              and hand.get('actor_and_betting_sequence_verified') is False
              and type(hand.get('events')) is list
              and type(hand.get('warnings')) is list
              and all(type(w) is str for w in hand['warnings'])
              and type(hand.get('unresolved_indices')) is list,
              'untrusted hand')
        seen.add(hand['hand_id'])
        intervals[hand['table_id']].append((hand['start_seconds'], hand['end_seconds']))
        check(all(type(i) is int and i >= 0 for i in hand['unresolved_indices']),
              'invalid unresolved index')
        count += len(hand['events'])
        check(count <= 4000, 'too many events')
        used, last = set(), (-1, -1)
        for event in hand['events']:
            check(type(event) is dict and valid_time(event.get('timestamp_seconds'))
                  and hand['start_seconds'] <= event['timestamp_seconds'] < hand['end_seconds']
                  and type(event.get('proposal_index')) is int and event['proposal_index'] >= 0
                  and event['proposal_index'] not in used
                  and type(event.get('field')) is str
                  and type(event.get('value')) is str
                  and event.get('review') in ('confirmed', 'corrected'), 'untrusted event')
            key = (event['timestamp_seconds'], event['proposal_index'])
            check(key >= last, 'events not sorted')
            used.add(event['proposal_index'])
            last = key
            if event['field'] != 'action':
                continue
            check(event['value'] in ACTIONS and event.get('actor_identified') is False
                  and event.get('action_legality_verified') is False
                  and type(event.get('nearby_bet_proposal_indices')) is list
                  and all(type(i) is int and i >= 0
                          for i in event['nearby_bet_proposal_indices']), 'untrusted action')
            t = event['timestamp_seconds']
            pots = [e for e in hand['events'] if type(e) is dict
                    and e.get('field') == 'pot' and valid_time(e.get('timestamp_seconds'))
                    and abs(e['timestamp_seconds'] - t) <= 3]
            points = ACTIONS[event['value']] + (2 if hand['warnings'] else 0) + \
                     (2 if hand['unresolved_indices'] else 0) + (0 if pots else 1)
            candidates.append({
                'hand_id': hand['hand_id'], 'table_id': hand['table_id'],
                'variant': hand['variant'], 'proposal_index': event['proposal_index'],
                'timestamp_seconds': t, 'action_ocr': event['value'],
                'nearby_bet_ocr_indices': event['nearby_bet_proposal_indices'],
                'nearby_pot_ocr_indices': [p['proposal_index'] for p in pots[:3]],
                'review_priority_points': points,
                'warnings': hand['warnings'],
                'unresolved_ocr_count': len(hand['unresolved_indices']),
                'preview_start_seconds': max(t - 3, hand['start_seconds']),
                'preview_end_seconds': min(t + 3, hand['end_seconds']),
                'actor_identified': False, 'ready_for_equity_or_ev': False,
                'clip_export_authorized': False})
        for event in hand['events']:
            if event['field'] == 'action':
                expected = sorted((e for e in hand['events'] if e['field'] == 'bet'
                                   and abs(e['timestamp_seconds'] - event['timestamp_seconds']) <= 2),
                                  key=lambda e: (abs(e['timestamp_seconds'] - event['timestamp_seconds']),
                                                 e['proposal_index']))
                check(event['nearby_bet_proposal_indices'] ==
                      [e['proposal_index'] for e in expected], 'forged bet proximity')
    for spans in intervals.values():
        spans.sort()
        check(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), 'overlapping hands')
    candidates.sort(key=lambda c: (-c['review_priority_points'], c['table_id'],
                                   c['timestamp_seconds'], c['hand_id'], c['proposal_index']))
    return {'schema_version': 1, 'analysis_status': 'offline_human_review_triage_only',
            'ranking': 'heuristic_not_equity_or_ev', 'total_candidates': len(candidates),
            'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
            'clip_export_authorized': False, 'candidates': candidates,
            'warning': 'OCR actions have unknown actors; ranking is not poker quality or EV.'}


def run(source, destination):
    source, destination = Path(source), Path(destination)
    check(source.is_file() and not source.is_symlink() and 0 < source.stat().st_size <= 8*1024*1024
          and destination.parent.is_dir() and not destination.parent.is_symlink()
          and not destination.exists() and not destination.is_symlink(), 'unsafe paths')
    raw = source.read_bytes()
    result = build(json.loads(raw, object_pairs_hook=unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NaN'))))
    result['source_timeline_sha256'] = hashlib.sha256(raw).hexdigest()
    check(hashlib.sha256(source.read_bytes()).hexdigest() == result['source_timeline_sha256'],
          'source changed')
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w', encoding='utf8') as out:
        json.dump(result, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write('\n')
    return result


if __name__ == '__main__':
    check(len(sys.argv) == 3, 'usage: TIMELINE_JSON NEW_QUEUE_JSON')
    print(json.dumps({'candidates': run(sys.argv[1], sys.argv[2])['total_candidates']}))
