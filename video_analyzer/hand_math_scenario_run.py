"""Offline, explicitly *hypothetical* PLO5/PLO6 range equity and all-in EV.

Consumes a pristine hand_math_intake worksheet and a separately completed copy.
Only manual scenario fields may change. A result NEVER verifies the source video,
hand boundaries, OCR, opponent ranges or strategic correctness. This is not a
real-time poker assistant, and it does not select clips automatically.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

from equity import simplified_call_ev
from hand_history import validate_cards
from range_ev import WeightedHand, estimate_weighted_range_equity, heads_up_all_in_raise_ev

MAX_BYTES = 16 * 1024 * 1024
MAX_TASKS = 2048
MAX_RUNS = 8
MAX_RANGE_HANDS = 128
MAX_TRIALS = 5000
FIELDS = ('hero_cards', 'board', 'observed_action', 'pot_before_action', 'call_amount')
SHA_FIELDS = ('recording_sha256', 'source_visual_history_sha256', 'source_visual_verdicts_sha256')


def _sha(value):
    if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Invalid SHA-256')
    return value


def _finite(value, name, *, min_value=0, max_value=None):
    if type(value) not in (int, float) or not math.isfinite(value) or value < min_value:
        raise ValueError(f'Invalid {name}')
    if max_value is not None and value > max_value:
        raise ValueError(f'Invalid {name}')
    return float(value)


def _cards(value, count, name):
    if type(value) is not list or len(value) not in count or any(type(x) is not str for x in value):
        raise ValueError(f'Invalid {name} card count')
    validate_cards(value)
    return tuple(value)


def _validate_template(intake):
    if (type(intake) is not dict or intake.get('schema_version') != 1 or
            intake.get('analysis_status') != 'manual_math_scenario_intake_blocked_no_calculation' or
            intake.get('ready_for_equity_or_ev') is not False or
            intake.get('automatic_clip_selection_authorized') is not False or
            intake.get('requires_independent_evidence_revalidation') is not True):
        raise ValueError('Not a blocked mathematical intake worksheet')
    for key in SHA_FIELDS:
        _sha(intake.get(key))
    tasks = intake.get('tasks')
    if type(tasks) is not list or not 1 <= len(tasks) <= MAX_TASKS:
        raise ValueError('Invalid task count')
    if (type(intake.get('counts')) is not dict or
            intake['counts'].get('spans') != len(tasks) or intake['counts'].get('math_ready') != 0):
        raise ValueError('Invalid intake counts')
    seen = set()
    for task in tasks:
        if type(task) is not dict:
            raise ValueError('Invalid task')
        ident = task.get('entry_id')
        if type(ident) is not str or not ident or len(ident) > 128 or ident in seen:
            raise ValueError('Invalid/duplicate task ID')
        seen.add(ident)
        if type(task.get('table_id')) is not int or not 1 <= task['table_id'] <= 4:
            raise ValueError('Invalid table')
        span = task.get('span_seconds')
        if type(span) is not list or len(span) != 2:
            raise ValueError('Invalid span')
        if _finite(span[0], 'start') >= _finite(span[1], 'end'):
            raise ValueError('Invalid span order')
        if (task.get('hand_reconstruction_verified') is not False or
                task.get('ready_for_equity_or_ev') is not False or
                task.get('automatic_clip_selection_authorized') is not False or
                type(task.get('blocking_reasons')) is not list or
                'independent_complete_hand_and_decision_attestation_required' not in task['blocking_reasons']):
            raise ValueError('Intake task claims unwarranted authority')
        draft = task.get('manual_scenario_draft')
        if type(draft) is not dict or type(draft.get('reviewed_fields')) is not dict or set(draft['reviewed_fields']) != set(FIELDS):
            raise ValueError('Invalid scenario draft')
        if (draft.get('human_confirmed') is not False or draft.get('timestamp') is not None or
                draft.get('observation_confidence') is not None or draft.get('call_range') != [] or
                draft.get('fold_probability') is not None or draft.get('monte_carlo_trials') is not None or
                draft.get('monte_carlo_seed') is not None):
            raise ValueError('Intake draft must be empty')
        for field in FIELDS:
            value = draft['reviewed_fields'][field]
            if type(value) is not dict or set(value) != {'value', 'confidence', 'source_timestamp', 'source', 'human_confirmed'} or any(x is not None for x in (value['value'], value['confidence'], value['source_timestamp'], value['source'])) or value['human_confirmed'] is not False:
                raise ValueError('Intake fields must be empty')


def _validated_scenario(draft, span):
    """Validate user-entered hypothetical inputs; never claim video provenance."""
    allowed = {'timestamp', 'human_confirmed', 'observation_confidence', 'reviewed_fields',
               'call_range', 'fold_probability', 'monte_carlo_trials', 'monte_carlo_seed',
               'model_notes', 'model_assumptions'}
    if (type(draft) is not dict or set(draft) != allowed or
            type(draft.get('reviewed_fields')) is not dict or
            set(draft['reviewed_fields']) != set(FIELDS)):
        raise ValueError('Unexpected scenario fields or missing reviewed fields')
    if draft.get('human_confirmed') is not True:
        raise ValueError('Manual scenario not attested')
    stamp = _finite(draft.get('timestamp'), 'scenario timestamp')
    if not span[0] <= stamp <= span[1]:
        raise ValueError('Scenario timestamp outside span')
    confidence = _finite(draft.get('observation_confidence'), 'confidence', max_value=1)
    fields = {}
    for name in FIELDS:
        field = draft['reviewed_fields'][name]
        if type(field) is not dict or set(field) != {'value', 'confidence', 'source_timestamp', 'source', 'human_confirmed'}:
            raise ValueError('Unexpected field structure')
        if field['human_confirmed'] is not True or field['source'] != 'independent_manual_video_review':
            raise ValueError('Independent manual attestation required for each field')
        _finite(field['confidence'], name + ' confidence', max_value=1)
        timestamp = _finite(field['source_timestamp'], name + ' timestamp')
        if not span[0] <= timestamp <= span[1]:
            raise ValueError('Field timestamp outside span')
        fields[name] = field['value']
    hero = _cards(fields['hero_cards'], (5, 6), 'hero')
    board = _cards(fields['board'], tuple(range(6)), 'board')
    validate_cards(hero + board)
    action = fields['observed_action']
    if type(action) is not str or action not in ('call', 'raise'):
        raise ValueError('Only call and raise hypothetical models are implemented')
    pot = _finite(fields['pot_before_action'], 'pot')
    call = _finite(fields['call_amount'], 'call amount')
    if call <= 0:
        raise ValueError('Call amount must be positive')
    trials = draft.get('monte_carlo_trials')
    seed = draft.get('monte_carlo_seed')
    if type(trials) is not int or not 1 <= trials <= MAX_TRIALS:
        raise ValueError('Invalid Monte Carlo trial count')
    if type(seed) is not int or not -(2**63) <= seed < 2**63:
        raise ValueError('Invalid Monte Carlo seed')
    notes = draft.get('model_notes')
    if type(notes) is not str or not 5 <= len(notes.strip()) <= 2000:
        raise ValueError('Explicit range/model notes required')
    model = draft.get('model_assumptions')
    if type(model) is not dict or not all(model.get(k) is True for k in ('heads_up', 'all_in_no_future_betting', 'no_rake', 'no_side_pots', 'no_icm')):
        raise ValueError('Explicit simplified heads-up all-in assumptions required')
    if set(model) != {'heads_up', 'all_in_no_future_betting', 'no_rake', 'no_side_pots', 'no_icm', 'hero_extra_chips', 'villain_extra_chips_if_called'}:
        raise ValueError('Unexpected model assumptions')
    if action == 'call':
        if model['hero_extra_chips'] is not None or model['villain_extra_chips_if_called'] is not None or draft.get('fold_probability') is not None:
            raise ValueError('Call model cannot include raise assumptions')
        fold = None
    else:
        fold = _finite(draft.get('fold_probability'), 'fold probability', max_value=1)
        extra = _finite(model['hero_extra_chips'], 'hero raise chips')
        villain_extra = _finite(model['villain_extra_chips_if_called'], 'villain call chips')
        if extra < call or villain_extra < 0:
            raise ValueError('Inconsistent raise amounts')
    raw_range = draft.get('call_range')
    if type(raw_range) is not list or not 1 <= len(raw_range) <= MAX_RANGE_HANDS:
        raise ValueError('Explicit opponent range required')
    seen, range_entries = set(), []
    for item in raw_range:
        if type(item) is not dict or set(item) != {'cards', 'weight'}:
            raise ValueError('Invalid opponent range entry')
        cards = _cards(item['cards'], (len(hero),), 'opponent')
        validate_cards(hero + board + cards)
        key = tuple(sorted(cards))
        if key in seen:
            raise ValueError('Duplicate opponent range combination')
        seen.add(key)
        weight = _finite(item['weight'], 'opponent range weight')
        if weight <= 0 or weight > 1e6:
            raise ValueError('Range weights must be positive and bounded')
        range_entries.append(WeightedHand(cards, weight))
    return {'hero': hero, 'board': board, 'action': action, 'pot': pot, 'call': call,
            'range': range_entries, 'trials': trials, 'seed': seed, 'notes': notes,
            'fold': fold, 'model': model, 'confidence': confidence}


def run(intake, filled, intake_sha256):
    """Compute explicitly hypothetical math for manually completed worksheets.

    A skipped/invalid task does not authorize math. Tampering with protected
    worksheet metadata aborts the entire batch before any calculations.
    """
    _sha(intake_sha256)
    _validate_template(intake)
    if type(filled) is not dict or set(filled) != set(intake):
        raise ValueError('Worksheet top-level metadata changed')
    if type(filled.get('tasks')) is not list or len(filled['tasks']) != len(intake['tasks']):
        raise ValueError('Worksheet task list changed')
    protected = copy.deepcopy(filled)
    for idx, original in enumerate(intake['tasks']):
        if type(protected['tasks'][idx]) is not dict:
            raise ValueError('Invalid completed task')
        protected['tasks'][idx]['manual_scenario_draft'] = copy.deepcopy(original['manual_scenario_draft'])
    if protected != intake:
        raise ValueError('Protected intake data changed')
    results = []
    valid = []
    for original, task in zip(intake['tasks'], filled['tasks']):
        draft = task['manual_scenario_draft']
        if draft == original['manual_scenario_draft']:
            results.append({'entry_id': task['entry_id'], 'table_id': task['table_id'],
                            'status': 'skipped_empty_manual_scenario'})
            continue
        try:
            scenario = _validated_scenario(draft, task['span_seconds'])
        except (ValueError, TypeError, KeyError) as exc:
            results.append({'entry_id': task['entry_id'], 'table_id': task['table_id'],
                            'status': 'blocked_invalid_manual_scenario', 'reason': str(exc)})
            continue
        valid.append((len(results), scenario))
        results.append({'entry_id': task['entry_id'], 'table_id': task['table_id'],
                        'status': 'pending_hypothetical_calculation'})
    if len(valid) > MAX_RUNS:
        raise ValueError('Too many scenarios for one bounded batch')
    for idx, sc in valid:
        eq = estimate_weighted_range_equity(sc['hero'], sc['board'], sc['range'],
                                            trials=sc['trials'], seed=sc['seed'])
        def ev(p):
            if sc['action'] == 'call':
                return simplified_call_ev(p, sc['pot'], sc['call'])
            return heads_up_all_in_raise_ev(p, sc['pot'], sc['model']['hero_extra_chips'],
                                             sc['model']['villain_extra_chips_if_called'], sc['fold'])
        results[idx].update({
            'status': 'hypothetical_only_not_video_verified',
            'variant': eq.variant, 'observed_action_assumed': sc['action'],
            'equity': eq.equity, 'equity_sampling_ci95': [eq.ci95_low, eq.ci95_high],
            'ev_vs_fold_zero': ev(eq.equity),
            'ev_sampling_ci95': [ev(eq.ci95_low), ev(eq.ci95_high)],
            'trials': eq.trials, 'seed': eq.seed, 'wins': eq.wins,
            'ties': eq.ties, 'losses': eq.losses,
            'opponent_model': eq.opponent_model,
            'opponent_range_combinations': len(sc['range']),
            'observation_confidence_human_estimate': sc['confidence'],
            'model_notes': sc['notes'],
            'model_limitations': ('Heads-up all-in, no later betting, rake, side pots or ICM. '
                                  'Ranges/fold probability are manually supplied hypotheses. '
                                  'CI covers Monte Carlo sampling only, not model or OCR error.'),
            'source_hand_reconstruction_verified': False,
            'strategic_error_established': False,
            'automatic_clip_selection_authorized': False,
        })
    return {
        'schema_version': 1,
        'analysis_status': 'hypothetical_math_only_no_video_hand_verification',
        'source_intake_sha256': intake_sha256,
        'recording_sha256_unverified_provenance': intake['recording_sha256'],
        'results': results,
        'counts': {'total': len(results), 'hypothetical': len(valid),
                   'blocked': sum(r['status'] == 'blocked_invalid_manual_scenario' for r in results),
                   'skipped': sum(r['status'] == 'skipped_empty_manual_scenario' for r in results)},
        'ready_for_equity_or_ev': False,
        'hand_reconstruction_verified': False,
        'strategic_error_established': False,
        'automatic_clip_selection_authorized': False,
        'warning': ('Hypothetical calculations from independently entered human assumptions only. '
                    'Do not treat as reconstructed video hands or verified strategic errors.'),
    }


def _load(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Invalid input file')
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError('Input too large')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError('Invalid JSON constant'))), raw


def export(intake_path, filled_path, output_path):
    intake_path, filled_path, output_path = map(Path, (intake_path, filled_path, output_path))
    if (output_path.exists() or output_path.is_symlink() or
            output_path.resolve() in (intake_path.resolve(), filled_path.resolve())):
        raise ValueError('Output must be new')
    intake, original = _load(intake_path)
    filled, edited = _load(filled_path)
    result = run(intake, filled, hashlib.sha256(original).hexdigest())
    if intake_path.read_bytes() != original or filled_path.read_bytes() != edited:
        raise ValueError('Source changed during processing')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2, ensure_ascii=False, allow_nan=False)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original_intake_json')
    parser.add_argument('manually_completed_json')
    parser.add_argument('new_output_json')
    args = parser.parse_args(argv)
    result = export(args.original_intake_json, args.manually_completed_json, args.new_output_json)
    print(json.dumps({'analysis_status': result['analysis_status'], 'counts': result['counts']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
