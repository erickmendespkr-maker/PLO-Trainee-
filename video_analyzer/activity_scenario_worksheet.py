"""Prepare offline *unapproved* equity/EV worksheets from human-review handoffs.

A filled OCR draft is not an authenticated hand history. This module does not
calculate equity, choose ranges, approve decisions, or trigger clip export.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

_HEX64 = re.compile(r'[0-9a-f]{64}\Z')
_FIELDS = ('hero_cards', 'board', 'observed_action', 'pot_before_action', 'call_amount')


def _sha(value):
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise ValueError('Invalid SHA-256 identity')
    return value


def build_scenario_worksheet(handoff):
    """Produce review-only model forms; never authorize equity or EV."""
    if not isinstance(handoff, dict) or handoff.get('schema_version') != 1:
        raise ValueError('Unsupported handoff')
    if (handoff.get('analysis_status') != 'human_review_handoff_not_video_verified_no_ev'
            or handoff.get('ready_for_equity_or_ev') is not False
            or handoff.get('source_visual_content_verified') is not False):
        raise ValueError('Handoff is not in the unverified state')
    recording = _sha(handoff.get('recording_sha256'))
    queue = _sha(handoff.get('source_queue_sha256'))
    draft = _sha(handoff.get('source_draft_sha256'))
    decisions = handoff.get('decisions')
    if not isinstance(decisions, list) or not decisions:
        raise ValueError('Expected nonempty decisions list')
    result, seen = [], set()
    for decision in decisions:
        if not isinstance(decision, dict) or decision.get('ready_for_equity_or_ev') is not False:
            raise ValueError('Decision cannot be pre-approved')
        if decision.get('opponent_range') is not None or decision.get('model_assumptions') is not None:
            raise ValueError('No prefilled range or assumptions allowed')
        if decision.get('fold_probability') is not None:
            raise ValueError('No inferred fold equity allowed')
        table = decision.get('table_id')
        event = decision.get('event_index')
        hand = decision.get('hand_id')
        if type(table) is not int or not 1 <= table <= 4 or type(event) is not int or event < 0:
            raise ValueError('Invalid table or event identity')
        if not isinstance(hand, str) or not hand or len(hand) > 256:
            raise ValueError('Invalid hand identity')
        key = (table, event)
        if key in seen:
            raise ValueError('Duplicate table/event identity')
        seen.add(key)
        inputs = decision.get('model_inputs')
        attested = decision.get('human_attested_fields')
        if not isinstance(inputs, dict) or set(inputs) != set(_FIELDS) or not isinstance(attested, dict):
            raise ValueError('Invalid reviewed inputs')
        if not set(attested).issubset(_FIELDS):
            raise ValueError('Unexpected attested field')
        for field in _FIELDS:
            if field in attested:
                if not isinstance(attested[field], dict) or attested[field].get('human_attested') is not True:
                    raise ValueError('Unattested field promoted')
                if attested[field].get('video_verified') is not False:
                    raise ValueError('Visual verification cannot be inferred')
                if inputs[field] != attested[field].get('value'):
                    raise ValueError('Attested value mismatch')
            elif inputs[field] is not None:
                raise ValueError('Unconfirmed model input')
        if decision.get('confirmed_field_count') != len(attested):
            raise ValueError('Incorrect confirmed field count')
        blockers = decision.get('blockers')
        if not isinstance(blockers, list) or not all(isinstance(x, str) for x in blockers):
            raise ValueError('Invalid blockers')
        result.append({
            'table_id': table, 'hand_id': hand, 'event_index': event,
            'decision_timestamp': decision.get('decision_timestamp'),
            'reviewed_visible_inputs': inputs,
            'unconfirmed_fields': [field for field in _FIELDS if field not in attested],
            'opponent_range': None, 'range_alternatives': None,
            'fold_probability': None, 'future_betting_model': None,
            'rake_model': None, 'trials': None, 'seed': None,
            'independent_frame_audit': None,
            'review_blockers': blockers,
            'ready_for_equity_or_ev': False,
            'note': 'Scenario hypotheses must be supplied and audited separately; no model has run.',
        })
    return {
        'schema_version': 1,
        'analysis_status': 'scenario_worksheet_unverified_no_ev',
        'recording_sha256': recording,
        'source_queue_sha256': queue,
        'source_draft_sha256': draft,
        'source_handoff_sha256': hashlib.sha256(json.dumps(
            handoff, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
            allow_nan=False).encode('utf-8')).hexdigest(),
        'ready_for_equity_or_ev': False,
        'scenarios': result,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('handoff_json')
    parser.add_argument('output_json')
    args = parser.parse_args(argv)
    source, output = Path(args.handoff_json), Path(args.output_json)
    if source.resolve() == output.resolve() or output.exists():
        raise ValueError('Output must be new and distinct from input')
    worksheet = build_scenario_worksheet(json.loads(source.read_text(encoding='utf-8')))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as fp:
        json.dump(worksheet, fp, ensure_ascii=False, indent=2, allow_nan=False)
        fp.write('\n')
    print(json.dumps({'scenarios': len(worksheet['scenarios']), 'ev_authorized': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
