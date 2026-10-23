"""Offline, fail-closed handoff of reviewed OCR drafts to mathematical scenario review.

This is NOT an EV authorization gate: a human checkbox does not authenticate
video frames or establish opponent ranges, future betting, rake, or fold equity.
No calculations or clips are launched by this module.
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from activity_review_packet import build_review_packet
from activity_review_draft_binding import check_draft_binding

FIELDS = ("hero_cards", "board", "observed_action", "pot_before_action", "call_amount")
CARD = re.compile(r"[2-9TJQKA][shdc]\Z")


def _canonical_digest(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def _validate_draft(queue, draft):
    template = build_review_packet(queue)['template']
    check_draft_binding(template, draft)
    for entry in draft['entries']:
        notes = entry['reviewer_notes']
        if not isinstance(notes, str) or len(notes) > 2000:
            raise ValueError('Invalid reviewer notes')
        fields = entry['reviewed_fields']
        if not isinstance(fields, dict) or set(fields) != set(FIELDS):
            raise ValueError('Invalid reviewed field map')
        seen_cards = []
        for field in FIELDS:
            item = fields[field]
            if not isinstance(item, dict) or set(item) != {
                    'value', 'confidence', 'source_timestamp', 'source', 'human_confirmed'}:
                raise ValueError('Invalid reviewed field record')
            value, confidence, timestamp, source, confirmed = (
                item[k] for k in ('value', 'confidence', 'source_timestamp', 'source', 'human_confirmed'))
            if type(confirmed) is not bool:
                raise ValueError('Invalid confirmation')
            if value is not None:
                if field in ('hero_cards', 'board'):
                    lengths = (5, 6) if field == 'hero_cards' else (0, 3, 4, 5)
                    if (not isinstance(value, list) or len(value) not in lengths
                            or any(not isinstance(card, str) or not CARD.fullmatch(card)
                                   for card in value)):
                        raise ValueError('Invalid cards')
                    seen_cards.extend(value)
                elif field == 'observed_action':
                    if type(value) is not str or value not in ('fold', 'call', 'raise'):
                        raise ValueError('Invalid action')
                elif type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError('Invalid amount')
            for number, maximum in ((confidence, 1), (timestamp, None)):
                if number is not None and (type(number) not in (int, float)
                        or not math.isfinite(number) or number < 0
                        or (maximum is not None and number > maximum)):
                    raise ValueError('Invalid confidence or timestamp')
            if timestamp is not None and (timestamp > entry['decision_timestamp']
                    or (field in ('hero_cards', 'board', 'pot_before_action')
                        and timestamp >= entry['decision_timestamp'])):
                raise ValueError('Future or simultaneous source timestamp')
            if source is not None and (not isinstance(source, str)
                    or not source.strip() or len(source) > 256):
                raise ValueError('Invalid source')
            if confirmed and (value is None or confidence is None
                              or timestamp is None or source is None):
                raise ValueError('Incomplete confirmed field')
        if len(set(seen_cards)) != len(seen_cards):
            raise ValueError('Duplicate cards')
    return draft


def build_handoff(queue, draft):
    """Return provenance-linked, EV-blocked review records from a valid draft.

    Unconfirmed values are deliberately omitted from model_inputs. Even with
    all five fields attested, independent image audit and model assumptions
    remain mandatory. No default opponent range or fold probability is set.
    """
    checked = _validate_draft(queue, draft)
    decisions = []
    for entry in checked['entries']:
        confirmed = {}
        missing = []
        for field in FIELDS:
            record = entry['reviewed_fields'][field]
            if record['human_confirmed']:
                confirmed[field] = {
                    'value': record['value'],
                    'confidence': record['confidence'],
                    'source_timestamp': record['source_timestamp'],
                    'source': record['source'],
                    'human_attested': True,
                    'video_verified': False,
                }
            else:
                missing.append(field)
        minimum = min((r['confidence'] for r in confirmed.values()), default=None)
        blockers = [f'field_not_human_confirmed:{name}' for name in missing]
        blockers.extend([
            'original_frame_bytes_and_pts_not_independently_audited',
            'opponent_range_not_supplied_or_validated',
            'ev_model_assumptions_not_supplied_or_validated',
            'decision_scenario_not_approved',
        ])
        decisions.append({
            'table_id': entry['table_id'],
            'hand_id': entry['hand_id'],
            'event_index': entry['event_index'],
            'decision_timestamp': entry['decision_timestamp'],
            'human_attested_fields': confirmed,
            'model_inputs': {name: confirmed[name]['value'] if name in confirmed else None
                             for name in FIELDS},
            'minimum_attested_field_confidence': minimum,
            'confirmed_field_count': len(confirmed),
            'blockers': blockers,
            'ready_for_equity_or_ev': False,
            'model_assumptions': None,
            'opponent_range': None,
            'fold_probability': None,
        })
    return {
        'schema_version': 1,
        'analysis_status': 'human_review_handoff_not_video_verified_no_ev',
        'recording_sha256': checked['recording_sha256'],
        'source_queue_sha256': checked['source_queue_sha256'],
        'source_draft_sha256': _canonical_digest(checked),
        'ready_for_equity_or_ev': False,
        'source_visual_content_verified': False,
        'decisions': decisions,
        'summary': {
            'total_decisions': len(decisions),
            'all_fields_human_attested': sum(d['confirmed_field_count'] == len(FIELDS)
                                             for d in decisions),
            'ev_authorized': 0,
        },
        'warning': ('Human attestation is not video verification. Model equity/EV '
                    'requires independent evidence audit and explicit ranges and assumptions.'),
    }


def write_handoff(queue_path, draft_path, output_path):
    paths = [Path(p) for p in (queue_path, draft_path, output_path)]
    if len({p.resolve() for p in paths}) != 3 or paths[2].exists():
        raise ValueError('Output must be a new path distinct from inputs')
    queue = json.loads(paths[0].read_text(encoding='utf-8'))
    draft = json.loads(paths[1].read_text(encoding='utf-8'))
    result = build_handoff(queue, draft)
    paths[2].parent.mkdir(parents=True, exist_ok=True)
    with paths[2].open('x', encoding='utf-8') as out:
        json.dump(result, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write('\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('queue_json')
    parser.add_argument('validated_draft_json')
    parser.add_argument('output_json')
    args = parser.parse_args(argv)
    result = write_handoff(args.queue_json, args.validated_draft_json, args.output_json)
    print(json.dumps(result['summary'], ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
