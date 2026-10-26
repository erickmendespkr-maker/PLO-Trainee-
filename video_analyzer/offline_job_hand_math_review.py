"""Offline PLO5/PLO6 *hypothetical* math review of unverified hand drafts.

Two-step flow: make an EMPTY, source-bound worksheet, then accept only an
independently re-entered and explicitly attested scenario. Reuse the existing
Monte Carlo/EV engine. This does NOT verify OCR, video PTS, hidden cards,
ranges, hand reconstruction, strategic errors, or authorize automatic clips.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from offline_job_hand_history_draft import validate_hand, number
from hand_math_scenario_run import _validated_scenario
from range_ev import estimate_weighted_range_equity, heads_up_all_in_raise_ev
from equity import simplified_call_ev

SHA = re.compile(r'[0-9a-f]{64}\Z')
JOB = re.compile(r'[0-9a-f]{32}\Z')
MAX_BYTES = 16 * 1024 * 1024
MAX_HANDS = 2000
MAX_SCENARIOS = 8
STATUS = 'manual_hypothetical_math_review_not_video_verified'
FIELDS = ('hero_cards', 'board', 'observed_action', 'pot_before_action', 'call_amount')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def check_sha(value):
    require(type(value) is str and SHA.fullmatch(value), 'Invalid SHA-256')


def validate_drafts(source):
    require(type(source) is dict and type(source.get('schema_version')) is int and
            source['schema_version'] == 1 and
            source.get('analysis_status') == 'human_entered_hand_history_drafts_no_math' and
            source.get('timestamp_semantics') == 'human_claimed_pts_not_independently_verified' and
            source.get('requires_source_video_reaudit') is True, 'Invalid source draft')
    require(type(source.get('job_id')) is str and JOB.fullmatch(source['job_id']), 'Invalid job')
    for key in ('source_sha256', 'source_checklist_sha256'):
        check_sha(source.get(key))
    for flag in ('hand_start_or_end_pts_verified', 'hand_reconstruction_verified',
                 'ready_for_equity_or_ev', 'automatic_clip_selection_authorized'):
        require(source.get(flag) is False, 'Upstream draft cannot authorize math')
    hands = source.get('hands')
    require(type(hands) is list and len(hands) <= MAX_HANDS, 'Invalid hand count')
    counts = source.get('counts')
    require(type(counts) is dict and type(counts.get('hands')) is int and
            counts['hands'] == len(hands) and type(counts.get('math_ready')) is int and
            counts['math_ready'] == 0, 'Invalid source counts')
    seen, complete = set(), 0
    for row in hands:
        require(type(row) is dict and type(row.get('table_id')) is int and
                1 <= row['table_id'] <= 4 and
                type(row.get('hand_label_human_assigned')) is str and
                0 < len(row['hand_label_human_assigned']) <= 64,
                'Invalid hand identity')
        ident = (row['table_id'], row['hand_label_human_assigned'])
        require(ident not in seen, 'Duplicate hand')
        seen.add(ident)
        for flag in ('hand_reconstruction_verified', 'ready_for_equity_or_ev',
                     'automatic_clip_selection_authorized'):
            require(row.get(flag) is False, 'Hand cannot authorize math')
        interval = row.get('source_nominal_interval_seconds')
        require(type(interval) is list and len(interval) == 2 and
                all(number(x) and x <= 86400 for x in interval) and interval[0] < interval[1],
                'Invalid nominal interval')
        imgs = row.get('source_image_sha256s')
        require(type(imgs) is list and len(imgs) <= 10000, 'Invalid source image list')
        for sha in imgs:
            check_sha(sha)
        hand = row.get('human_entry')
        require(type(hand) is dict, 'Missing human entry')
        is_complete = validate_hand(hand, row)
        expected = ('structurally_complete_human_draft_unverified' if is_complete
                    else 'incomplete_human_draft_unverified')
        require(row.get('status') == expected, 'Contradictory draft status')
        complete += is_complete
    require(type(counts.get('structurally_complete_unverified')) is int and
            counts['structurally_complete_unverified'] == complete, 'Incorrect complete count')
    return seen


def blank_scenario():
    return {
        'timestamp': None, 'human_confirmed': False,
        'observation_confidence': None,
        'reviewed_fields': {name: {'value': None, 'confidence': None,
                                  'source_timestamp': None, 'source': None,
                                  'human_confirmed': False} for name in FIELDS},
        'call_range': [], 'fold_probability': None,
        'monte_carlo_trials': None, 'monte_carlo_seed': None,
        'model_notes': '',
        'model_assumptions': {
            'heads_up': False, 'all_in_no_future_betting': False,
            'no_rake': False, 'no_side_pots': False, 'no_icm': False,
            'hero_extra_chips': None, 'villain_extra_chips_if_called': None,
        },
    }


def make_worksheet(source, source_sha256):
    validate_drafts(source)
    check_sha(source_sha256)
    tasks = []
    for row in source['hands']:
        entry = row['human_entry']
        tasks.append({
            'table_id': row['table_id'],
            'hand_label_human_assigned': row['hand_label_human_assigned'],
            'source_human_entry_sha256': digest(entry),
            'source_nominal_interval_seconds': row['source_nominal_interval_seconds'],
            'source_status': row['status'],
            'manual_scenario_draft': blank_scenario(),
            'hand_reconstruction_verified': False,
            'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
        })
    return {
        'schema_version': 1, 'analysis_status': STATUS,
        'job_id': source['job_id'], 'recording_sha256_unverified': source['source_sha256'],
        'source_draft_sha256': source_sha256,
        'tasks': tasks, 'counts': {'hands': len(tasks), 'hypothetical_calculations': 0},
        'ready_for_equity_or_ev': False, 'hand_reconstruction_verified': False,
        'automatic_clip_selection_authorized': False,
        'warning': 'Empty worksheet: independently re-review the video; math remains hypothetical.',
    }


def _cross_check(sc, entry):
    """Prevent silently computing a *different* decision from the typed draft."""
    hero = entry['hero_cards']
    require(hero is not None and set(sc['hero']) == set(hero),
            'Scenario hero cards contradict reviewed hand draft')
    board = entry['board_by_street']
    known = (board['flop'] or []) + ([board['turn']] if board['turn'] else []) + (
        [board['river']] if board['river'] else [])
    require(len(sc['board']) in (0, 3, 4, 5) and
            len(sc['board']) <= len(known) and list(sc['board']) == known[:len(sc['board'])],
            'Scenario board contradicts hand draft')
    require(sc['pot'] == float(entry['pot_before_decision']) and
            sc['call'] == float(entry['call_amount']),
            'Scenario chip amounts contradict hand draft')
    # _validated_scenario does not return timestamp; the caller validates it.


def run_review(source, worksheet, filled, source_sha256):
    validate_drafts(source)
    check_sha(source_sha256)
    require(type(worksheet) is dict and worksheet == make_worksheet(source, source_sha256),
            'Worksheet source mismatch or tampering')
    require(type(filled) is dict and set(filled) == set(worksheet) and
            type(filled.get('tasks')) is list and len(filled['tasks']) == len(worksheet['tasks']),
            'Invalid filled worksheet')
    clean = copy.deepcopy(filled)
    for idx, original in enumerate(worksheet['tasks']):
        require(type(clean['tasks'][idx]) is dict and
                'manual_scenario_draft' in clean['tasks'][idx], 'Invalid filled task')
        clean['tasks'][idx]['manual_scenario_draft'] = copy.deepcopy(original['manual_scenario_draft'])
    require(clean == worksheet, 'Protected worksheet metadata changed')
    by_hand = {(r['table_id'], r['hand_label_human_assigned']): r for r in source['hands']}
    results, scenarios = [], []
    for task in filled['tasks']:
        key = (task['table_id'], task['hand_label_human_assigned'])
        row = by_hand[key]
        form = task['manual_scenario_draft']
        result = {'table_id': key[0], 'hand_label_human_assigned': key[1],
                  'source_human_entry_sha256': task['source_human_entry_sha256']}
        if form == blank_scenario():
            result['status'] = 'skipped_empty_manual_scenario'
        elif row['status'] != 'structurally_complete_human_draft_unverified':
            result.update(status='blocked_incomplete_hand_draft', reason='Human draft incomplete')
        else:
            try:
                entry = row['human_entry']
                require(entry['source_pts_checked_by_human'] is True and
                        entry['reviewer_attestation'] is True, 'Missing human PTS/review attestations')
                start, end = entry['source_pts_start_seconds'], entry['source_pts_end_seconds']
                require(start is not None and end is not None, 'Missing claimed source PTS')
                scenario = _validated_scenario(form, [start, end])
                _cross_check(scenario, entry)
                stamp = form['timestamp']
                matching = [a for a in entry['actions'] if a['actor'] == 'hero' and
                            a['action'] == scenario['action'] and
                            abs(a['source_pts_seconds'] - stamp) <= 0.05 and
                            (scenario['action'] != 'call' or a['amount'] == scenario['call'])]
                require(bool(matching), 'Scenario decision does not match a documented hero action')
                require(len(scenario['board']) == (0 if matching[0]['street'] == 'preflop' else
                                                   {'flop': 3, 'turn': 4, 'river': 5}[matching[0]['street']]),
                        'Scenario board and action street disagree')
            except (ValueError, KeyError, TypeError) as exc:
                result.update(status='blocked_invalid_manual_scenario', reason=str(exc))
            else:
                result['status'] = 'pending_hypothetical_calculation'
                scenarios.append((len(results), scenario))
        results.append(result)
    require(len(scenarios) <= MAX_SCENARIOS, 'Too many bounded Monte Carlo scenarios')
    for idx, sc in scenarios:
        eq = estimate_weighted_range_equity(sc['hero'], sc['board'], sc['range'],
                                            trials=sc['trials'], seed=sc['seed'])
        def ev(p):
            if sc['action'] == 'call':
                return simplified_call_ev(p, sc['pot'], sc['call'])
            return heads_up_all_in_raise_ev(p, sc['pot'], sc['model']['hero_extra_chips'],
                                            sc['model']['villain_extra_chips_if_called'], sc['fold'])
        results[idx].update({
            'status': 'hypothetical_only_not_video_verified', 'variant': eq.variant,
            'observed_action_assumed': sc['action'], 'equity': eq.equity,
            'equity_sampling_ci95': [eq.ci95_low, eq.ci95_high],
            'ev_vs_fold_zero': ev(eq.equity),
            'ev_sampling_ci95': [ev(eq.ci95_low), ev(eq.ci95_high)],
            'trials': eq.trials, 'seed': eq.seed, 'wins': eq.wins,
            'ties': eq.ties, 'losses': eq.losses,
            'opponent_range_combinations': len(sc['range']),
            'model_notes': sc['notes'], 'human_confidence_subjective': sc['confidence'],
            'model_limitations': ('Heads-up all-in without rake, side pots, ICM or future betting. '
                                  'Range and fold equity are assumptions. CI covers Monte Carlo '
                                  'sampling only; not OCR, range or model uncertainty.'),
            'hand_reconstruction_verified': False,
            'strategic_error_established': False,
            'automatic_clip_selection_authorized': False,
        })
    return {
        'schema_version': 1, 'analysis_status': 'hypothetical_math_from_unverified_hand_drafts',
        'job_id': source['job_id'], 'source_draft_sha256': source_sha256,
        'source_worksheet_sha256': digest(worksheet),
        'source_filled_worksheet_sha256': digest(filled),
        'results': results,
        'counts': {'total': len(results), 'hypothetical': len(scenarios),
                   'blocked': sum(r['status'].startswith('blocked_') for r in results),
                   'skipped': sum(r['status'].startswith('skipped_') for r in results)},
        'ready_for_equity_or_ev': False, 'hand_reconstruction_verified': False,
        'strategic_error_established': False, 'automatic_clip_selection_authorized': False,
        'warning': ('Human-entered hypotheses only; video evidence and source PTS not independently '
                    'verified. No strategic error established and no automatic clips.'),
    }


def _unique(pairs):
    out = {}
    for key, val in pairs:
        require(key not in out, 'Duplicate JSON key')
        out[key] = val
    return out


def load(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and p.stat().st_size <= MAX_BYTES,
            'Unsafe or oversized input')
    raw = p.read_bytes()
    require(len(raw) <= MAX_BYTES, 'Oversized input')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique,
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s))), raw


def write_new(target, obj):
    target = Path(target)
    require(target.parent.is_dir() and not target.parent.is_symlink(), 'Unsafe output directory')
    payload = json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8') + b'\n'
    require(len(payload) <= MAX_BYTES, 'Oversized output')
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            require(stat.S_ISREG(os.fstat(f.fileno()).st_mode), 'Unsafe output file')
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def export_template(draft_path, output_path):
    src, target = Path(draft_path), Path(output_path)
    require(src.resolve() != target.resolve(), 'Overlapping paths')
    source, raw = load(src)
    worksheet = make_worksheet(source, hashlib.sha256(raw).hexdigest())
    require(src.read_bytes() == raw, 'Input changed during processing')
    write_new(target, worksheet)
    return worksheet


def export_math(draft_path, worksheet_path, filled_path, output_path):
    paths = list(map(Path, (draft_path, worksheet_path, filled_path)))
    target = Path(output_path)
    require(len({p.resolve() for p in paths + [target]}) == 4, 'Overlapping paths')
    loaded = [load(p) for p in paths]
    source, worksheet, filled = (x[0] for x in loaded)
    result = run_review(source, worksheet, filled, hashlib.sha256(loaded[0][1]).hexdigest())
    require(all(p.read_bytes() == raw for p, (_, raw) in zip(paths, loaded)),
            'Input changed during processing')
    write_new(target, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    t = sub.add_parser('template')
    t.add_argument('draft_json')
    t.add_argument('new_worksheet_json')
    r = sub.add_parser('calculate')
    r.add_argument('draft_json')
    r.add_argument('worksheet_json')
    r.add_argument('independently_completed_worksheet_json')
    r.add_argument('new_results_json')
    args = parser.parse_args(argv)
    if args.command == 'template':
        result = export_template(args.draft_json, args.new_worksheet_json)
        print(json.dumps(result['counts']))
    else:
        result = export_math(args.draft_json, args.worksheet_json,
                             args.independently_completed_worksheet_json, args.new_results_json)
        print(json.dumps(result['counts']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
