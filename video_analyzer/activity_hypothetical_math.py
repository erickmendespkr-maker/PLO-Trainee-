"""Explicit, *unverified* PLO5/PLO6 what-if calculations from review worksheets.

This is NOT the video evidence gate: output cannot authorize EV-based clip ranking,
label a played decision as an error, or authenticate OCR. The user must provide
an opponent range and explicitly acknowledge the simplified all-in model.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from equity import simplified_call_ev
from range_ev import WeightedHand, estimate_weighted_range_equity

MODEL = 'hypothetical_heads_up_all_in_no_rake_no_future_betting'


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _nonnegative(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Expected finite nonnegative amount')
    return value


def _key(entry):
    if not isinstance(entry, dict):
        raise ValueError('Scenario must be an object')
    table, event, hand = (entry.get(k) for k in ('table_id', 'event_index', 'hand_id'))
    if type(table) is not int or not 1 <= table <= 4 or type(event) is not int or event < 0:
        raise ValueError('Invalid table/event')
    if not isinstance(hand, str) or not hand or len(hand) > 256:
        raise ValueError('Invalid hand identity')
    return table, event, hand


def build_hypothetical_report(worksheet, request):
    """Compute only conditional model arithmetic, never decision correctness."""
    if (not isinstance(worksheet, dict) or worksheet.get('schema_version') != 1
            or worksheet.get('analysis_status') != 'scenario_worksheet_unverified_no_ev'
            or worksheet.get('ready_for_equity_or_ev') is not False):
        raise ValueError('Requires an unverified scenario worksheet')
    scenarios = worksheet.get('scenarios')
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError('Missing scenarios')
    by_key = {}
    for scenario in scenarios:
        key = _key(scenario)
        if key in by_key or scenario.get('ready_for_equity_or_ev') is not False:
            raise ValueError('Duplicate or preapproved scenario')
        by_key[key] = scenario
    if (not isinstance(request, dict) or set(request) != {'schema_version', 'worksheet_sha256', 'scenarios'}
            or request['schema_version'] != 1 or request['worksheet_sha256'] != digest(worksheet)):
        raise ValueError('Request is not bound to this worksheet')
    requests = request['scenarios']
    if not isinstance(requests, list) or not requests:
        raise ValueError('At least one explicit hypothetical request required')
    results, seen = [], set()
    for item in requests:
        if not isinstance(item, dict) or set(item) != {
                'table_id', 'event_index', 'hand_id', 'model_acknowledgement',
                'opponent_range', 'trials', 'seed'}:
            raise ValueError('Invalid hypothetical request fields')
        key = _key(item)
        if key not in by_key or key in seen:
            raise ValueError('Unknown or duplicate scenario identity')
        seen.add(key)
        scenario = by_key[key]
        if scenario.get('unconfirmed_fields') != []:
            raise ValueError('All visible inputs must be manually attested for this preview')
        if item['model_acknowledgement'] != MODEL:
            raise ValueError('Explicit simplified model acknowledgement required')
        inputs = scenario.get('reviewed_visible_inputs')
        if not isinstance(inputs, dict) or set(inputs) != {
                'hero_cards', 'board', 'observed_action', 'pot_before_action', 'call_amount'}:
            raise ValueError('Missing reviewed inputs')
        if inputs['observed_action'] != 'call':
            raise ValueError('Only call what-if supported, no raise/fold solver')
        pot = _nonnegative(inputs['pot_before_action'])
        call = _nonnegative(inputs['call_amount'])
        if call <= 0:
            raise ValueError('Call amount must be positive')
        raw_range = item['opponent_range']
        if not isinstance(raw_range, list) or not 1 <= len(raw_range) <= 1000:
            raise ValueError('Explicit opponent range must contain 1..1000 hands')
        weighted = []
        for entry in raw_range:
            if not isinstance(entry, dict) or set(entry) != {'cards', 'weight'}:
                raise ValueError('Invalid weighted opponent hand')
            if not isinstance(entry['cards'], list):
                raise ValueError('Opponent cards must be a list')
            weighted.append(WeightedHand(tuple(entry['cards']), entry['weight']))
        equity = estimate_weighted_range_equity(inputs['hero_cards'], inputs['board'], weighted,
                                                trials=item['trials'], seed=item['seed'])
        results.append({
            'table_id': key[0], 'event_index': key[1], 'hand_id': key[2],
            'variant': equity.variant, 'opponent_model': equity.opponent_model,
            'opponent_range': raw_range, 'trials': equity.trials, 'seed': equity.seed,
            'wins': equity.wins, 'ties': equity.ties, 'losses': equity.losses,
            'equity': equity.equity, 'equity_sampling_ci95': [equity.ci95_low, equity.ci95_high],
            'call_ev_vs_fold': simplified_call_ev(equity.equity, pot, call),
            'call_ev_sampling_ci95': [simplified_call_ev(equity.ci95_low, pot, call),
                                      simplified_call_ev(equity.ci95_high, pot, call)],
            'pot_before_call': pot, 'call_amount': call,
            'model_acknowledgement': MODEL,
            'ready_for_equity_or_ev': False,
            'authorized_for_clips': False,
        })
    return {
        'schema_version': 1, 'analysis_status': 'hypothetical_math_only_not_video_verified',
        'source_worksheet_sha256': digest(worksheet), 'source_request_sha256': digest(request),
        'ready_for_equity_or_ev': False, 'authorized_for_clips': False,
        'results': results,
        'warning': ('These are user-assumed heads-up all-in, no-rake, no-future-betting '
                    'what-if calculations. CI covers sampling only, not opponent range '
                    'uncertainty. No video accuracy, strategic error, or real EV is established.'),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('worksheet_json'); parser.add_argument('request_json'); parser.add_argument('output_json')
    args = parser.parse_args(argv)
    paths = [Path(p) for p in (args.worksheet_json, args.request_json, args.output_json)]
    if len({p.resolve() for p in paths}) != 3 or paths[-1].exists():
        raise ValueError('Output must be new and distinct from inputs')
    report = build_hypothetical_report(json.loads(paths[0].read_text(encoding='utf-8')),
                                       json.loads(paths[1].read_text(encoding='utf-8')))
    paths[-1].parent.mkdir(parents=True, exist_ok=True)
    with paths[-1].open('x', encoding='utf-8') as out:
        json.dump(report, out, indent=2, ensure_ascii=False, allow_nan=False)
        out.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
