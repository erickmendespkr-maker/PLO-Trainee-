"""Offline, non-authoritative manual hand-history drafts from Cycle 106 checklists.

Validates *structure*, not the accuracy of video/OCR, source PTS, human
attestations, ranges or strategic analysis. Never authorizes equity/EV/clips.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

SHA = re.compile(r'[0-9a-f]{64}\Z')
JOB = re.compile(r'[0-9a-f]{32}\Z')
CARD = re.compile(r'(?:[2-9TJQKA][cdhs])\Z')
STREETS = ('preflop', 'flop', 'turn', 'river')
ACTIONS = ('fold', 'check', 'call', 'bet', 'raise')
MAX_BYTES = 16 * 1024 * 1024
MAX_HANDS = 2000
MAX_ACTIONS = 200
MAX_SECONDS = 86400


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def number(value, *, zero=True):
    return type(value) in (int, float) and math.isfinite(value) and (0 <= value if zero else 0 < value) and value <= 1e9


def nullable_amount(value):
    require(value is None or number(value), 'Invalid chip amount')


def card_list(value, count):
    require(type(value) is list and len(value) == count and
            all(type(c) is str and CARD.fullmatch(c) for c in value) and
            len(set(value)) == count, 'Invalid card list')


def validate_checklist(checklist):
    require(type(checklist) is dict and type(checklist.get('schema_version')) is int and
            checklist['schema_version'] == 1 and
            checklist.get('analysis_status') == 'manual_reconstruction_checklist_no_math',
            'Invalid checklist schema')
    require(type(checklist.get('job_id')) is str and JOB.fullmatch(checklist['job_id']) and
            type(checklist.get('source_sha256')) is str and SHA.fullmatch(checklist['source_sha256']) and
            type(checklist.get('source_dossiers_sha256')) is str and SHA.fullmatch(checklist['source_dossiers_sha256']),
            'Invalid source identity')
    require(checklist.get('timestamp_semantics') == 'nominal_sampling_grid_not_exact_source_pts' and
            checklist.get('requires_source_video_reaudit') is True, 'Invalid source timestamp semantics')
    for gate in ('hand_start_or_end_pts_verified', 'hand_reconstruction_verified',
                 'ready_for_equity_or_ev', 'automatic_clip_selection_authorized'):
        require(checklist.get(gate) is False, 'Unexpected upstream authorization')
    tasks = checklist.get('tasks')
    require(type(tasks) is list and len(tasks) <= MAX_HANDS, 'Invalid task list')
    counts = checklist.get('counts')
    require(type(counts) is dict and type(counts.get('hands_to_review')) is int and
            counts['hands_to_review'] == len(tasks) and type(counts.get('math_ready')) is int and
            counts['math_ready'] == 0, 'Invalid checklist counts')
    identities = set()
    for task in tasks:
        require(type(task) is dict and type(task.get('table_id')) is int and
                1 <= task['table_id'] <= 4 and type(task.get('hand_label_human_assigned')) is str and
                0 < len(task['hand_label_human_assigned']) <= 64, 'Invalid hand identity')
        identity = (task['table_id'], task['hand_label_human_assigned'])
        require(identity not in identities, 'Duplicate checklist hand')
        identities.add(identity)
        interval = task.get('nominal_interval_seconds')
        require(type(interval) is list and len(interval) == 2 and
                all(number(t) and t <= MAX_SECONDS for t in interval) and interval[0] < interval[1],
                'Invalid nominal interval')
        require(type(task.get('source_image_sha256s')) is list and
                all(type(s) is str and SHA.fullmatch(s) for s in task['source_image_sha256s']),
                'Invalid image provenance')
        require(type(task.get('manual_reconstruction_template')) is dict and
                set(task['manual_reconstruction_template']) == {
                    'variant', 'hero_cards', 'board_by_street', 'pot_and_bet_sequence',
                    'effective_stacks', 'actions_with_actors_and_streets', 'decision_point',
                    'opponent_ranges_assumptions', 'source_pts_verified_against_video',
                    'independent_reviewer_attestation'} and
                all(v is None for v in task['manual_reconstruction_template'].values()),
                'Checklist unexpectedly populated')
        for gate in ('hand_reconstruction_verified', 'ready_for_equity_or_ev',
                     'automatic_clip_selection_authorized'):
            require(task.get(gate) is False, 'Unexpected hand authorization')
    return identities


def validate_hand(hand, task):
    require(type(hand) is dict, 'Malformed manual hand')
    required = {'table_id', 'hand_label_human_assigned', 'variant', 'hero_cards',
                'board_by_street', 'actions', 'pot_before_decision', 'call_amount',
                'effective_stack', 'source_pts_start_seconds', 'source_pts_end_seconds',
                'source_pts_checked_by_human', 'reviewer_attestation',
                'opponent_range_notes', 'notes', 'confidence_subjective'}
    require(set(hand) == required, 'Unexpected or missing hand fields')
    require(type(hand['table_id']) is int and hand['table_id'] == task['table_id'] and
            type(hand['hand_label_human_assigned']) is str and
            hand['hand_label_human_assigned'] == task['hand_label_human_assigned'],
            'Cross-table or mismatched hand')
    variant = hand['variant']
    require(variant in ('PLO5', 'PLO6') and type(variant) is str, 'Invalid PLO variant')
    cards = hand['hero_cards']
    if cards is not None:
        card_list(cards, 5 if variant == 'PLO5' else 6)
    board = hand['board_by_street']
    require(type(board) is dict and set(board) == {'flop', 'turn', 'river'}, 'Invalid board schema')
    flop, turn, river = board['flop'], board['turn'], board['river']
    require(flop is None or type(flop) is list, 'Invalid flop')
    if flop is not None:
        card_list(flop, 3)
    for c in (turn, river):
        require(c is None or (type(c) is str and CARD.fullmatch(c)), 'Invalid turn/river')
    require(turn is None or flop is not None, 'Turn without flop')
    require(river is None or turn is not None, 'River without turn')
    all_cards = (cards or []) + (flop or []) + ([turn] if turn else []) + ([river] if river else [])
    require(len(all_cards) == len(set(all_cards)), 'Duplicate visible cards')
    for field in ('pot_before_decision', 'call_amount', 'effective_stack'):
        nullable_amount(hand[field])
    start, end = hand['source_pts_start_seconds'], hand['source_pts_end_seconds']
    require((start is None and end is None) or
            (number(start) and number(end) and 0 <= start < end <= MAX_SECONDS),
            'Invalid claimed source PTS interval')
    for field in ('source_pts_checked_by_human', 'reviewer_attestation'):
        require(type(hand[field]) is bool, 'Invalid human attestation')
    require(not hand['source_pts_checked_by_human'] or start is not None,
            'PTS attestation without timestamps')
    for field in ('opponent_range_notes', 'notes'):
        require(type(hand[field]) is str and len(hand[field]) <= 2000, 'Invalid review notes')
    require(number(hand['confidence_subjective']) and hand['confidence_subjective'] <= 1,
            'Invalid subjective confidence')
    actions = hand['actions']
    require(type(actions) is list and len(actions) <= MAX_ACTIONS, 'Invalid action sequence')
    last_street, last_pts = -1, -1.0
    for action in actions:
        require(type(action) is dict and set(action) ==
                {'street', 'actor', 'action', 'amount', 'source_pts_seconds'},
                'Invalid action structure')
        street, kind, actor = action['street'], action['action'], action['actor']
        require(type(street) is str and street in STREETS and
                type(kind) is str and kind in ACTIONS and
                type(actor) is str and (actor in ('hero', 'unknown') or
                re.fullmatch(r'villain_[1-9][0-9]?', actor)), 'Invalid action label')
        pts = action['source_pts_seconds']
        require(number(pts) and pts <= MAX_SECONDS and (start is None or start <= pts <= end),
                'Invalid action PTS')
        require(STREETS.index(street) >= last_street and pts >= last_pts,
                'Nonmonotonic action sequence')
        last_street, last_pts = STREETS.index(street), pts
        amount = action['amount']
        require(number(amount) and ((kind in ('fold', 'check') and amount == 0) or
                (kind in ('call', 'bet', 'raise') and amount > 0)),
                'Invalid action amount')
        require(not (street in ('flop', 'turn', 'river') and board['flop'] is None),
                'Postflop action without visible flop')
        require(not (street in ('turn', 'river') and board['turn'] is None),
                'Turn/river action without visible turn')
        require(not (street == 'river' and board['river'] is None),
                'River action without visible river')
    complete = (cards is not None and flop is not None and
                all(hand[f] is not None for f in ('pot_before_decision', 'call_amount', 'effective_stack'))
                and bool(actions) and hand['source_pts_checked_by_human'] and
                hand['reviewer_attestation'] and bool(hand['opponent_range_notes'].strip()))
    return bool(complete)


def build_drafts(checklist, submission):
    identities = validate_checklist(checklist)
    require(type(submission) is dict and set(submission) == {
            'schema_version', 'job_id', 'source_checklist_sha256', 'hands'} and
            type(submission.get('schema_version')) is int and
            submission['schema_version'] == 1 and
            submission.get('job_id') == checklist['job_id'] and
            type(submission.get('source_checklist_sha256')) is str and
            submission['source_checklist_sha256'] == digest(checklist),
            'Submission does not match source checklist')
    hands = submission.get('hands')
    require(type(hands) is list and len(hands) == len(identities), 'Invalid submitted hand count')
    lookup = {(t['table_id'], t['hand_label_human_assigned']): t for t in checklist['tasks']}
    seen, rows = set(), []
    for hand in hands:
        require(type(hand) is dict, 'Malformed submitted hand')
        ident = (hand.get('table_id'), hand.get('hand_label_human_assigned'))
        require(ident in lookup and ident not in seen, 'Unknown or duplicate submitted hand')
        seen.add(ident)
        complete = validate_hand(hand, lookup[ident])
        rows.append({
            'table_id': ident[0], 'hand_label_human_assigned': ident[1],
            'source_nominal_interval_seconds': lookup[ident]['nominal_interval_seconds'],
            'source_image_sha256s': lookup[ident]['source_image_sha256s'],
            'human_entry': hand,
            'status': ('structurally_complete_human_draft_unverified' if complete
                       else 'incomplete_human_draft_unverified'),
            'hand_reconstruction_verified': False,
            'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
        })
    rows.sort(key=lambda r: (r['table_id'], r['source_nominal_interval_seconds'][0],
                             r['hand_label_human_assigned']))
    return {
        'schema_version': 1,
        'analysis_status': 'human_entered_hand_history_drafts_no_math',
        'job_id': checklist['job_id'], 'source_sha256': checklist['source_sha256'],
        'source_checklist_sha256': digest(checklist),
        'timestamp_semantics': 'human_claimed_pts_not_independently_verified',
        'hands': rows,
        'counts': {'hands': len(rows), 'structurally_complete_unverified': sum(
            r['status'] == 'structurally_complete_human_draft_unverified' for r in rows),
                   'math_ready': 0},
        'requires_source_video_reaudit': True,
        'hand_start_or_end_pts_verified': False,
        'hand_reconstruction_verified': False,
        'ready_for_equity_or_ev': False,
        'automatic_clip_selection_authorized': False,
        'limitations': [
            'Typed human values are claims, not independently verified video facts.',
            'Source PTS claims are not authenticated against the original recording.',
            'Action chronology and chips are structurally checked, not strategically proven.',
            'Ranges are reviewer notes, not validated probability distributions.',
            'No hidden cards inferred; no equity, EV, strategic verdict or automatic clips.',
        ],
    }


def _no_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def load_json(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_BYTES,
            'Unsafe or oversized input')
    raw = path.read_bytes()
    require(len(raw) <= MAX_BYTES, 'Oversized input')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_no_duplicate_pairs,
                           parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid UTF-8 JSON') from exc
    return value, raw


def export_drafts(checklist_path, submission_path, output_path):
    paths = [Path(checklist_path), Path(submission_path)]
    target = Path(output_path)
    require(paths[0].resolve() != paths[1].resolve() and
            all(target.resolve() != p.resolve() for p in paths), 'Input/output paths overlap')
    sources = [load_json(p) for p in paths]
    report = build_drafts(sources[0][0], sources[1][0])
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8') + b'\n'
    require(len(payload) <= MAX_BYTES, 'Oversized output')
    require(all(p.read_bytes() == raw for p, (_, raw) in zip(paths, sources)),
            'Input changed during validation')
    require(target.parent.is_dir() and not target.parent.is_symlink(), 'Unsafe output directory')
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'Unsafe output file')
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checklist_json')
    parser.add_argument('manual_submission_json')
    parser.add_argument('new_output_json')
    args = parser.parse_args(argv)
    result = export_drafts(args.checklist_json, args.manual_submission_json, args.new_output_json)
    print(json.dumps(result['counts']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
