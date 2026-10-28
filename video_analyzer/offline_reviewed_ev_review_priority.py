"""Conservative, OFFLINE manual-review queue from existing hypothetical EV clip attachments.

No automated clip selection, action recommendation, or proven poker mistake.
Only conditional EV interval separation is computed; range/model uncertainty is
NOT measured by the Monte Carlo sampling bounds. Requires a local recording and
exported clips to recheck their hashes. Never edits input MP4s.

Usage: python offline_reviewed_ev_review_priority.py RECORDING BATCH_DIR \
       ATTACHMENTS_JSON NEW_PRIORITY_JSON [--min-separation 0]
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

MAX_JSON = 4 * 1024 * 1024
MAX_CLIPS = 12
MAX_DECISIONS = 32
SHA = re.compile(r'[0-9a-f]{64}\Z')
SAFE_FILE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
AMOUNT = re.compile(r'-?(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,8})?\Z')
ACTIONS = ('fold', 'call', 'raise')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink(), 'Missing or symlinked input')
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def unique(pairs):
    d = {}
    for k, v in pairs:
        require(k not in d, 'Duplicate JSON key')
        d[k] = v
    return d


def read(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_JSON,
            'Invalid input JSON file')
    return json.loads(p.read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def amount(x):
    require(type(x) is str and AMOUNT.fullmatch(x), 'Invalid decimal string')
    return Decimal(x)


def timestamp(x):
    require(type(x) in (int, float) and math.isfinite(x) and x >= 0,
            'Invalid timestamp')
    return float(x)


def sha(x):
    return type(x) is str and SHA.fullmatch(x) is not None


def interval(decision, action):
    if action == 'fold':
        v = amount(decision.get('ev_fold_hypothetical'))
        require(v == 0, 'Fold EV baseline must be zero')
        return (v, v)
    key = ('ev_call_sampling_bounds' if action == 'call' else
           'ev_raise_sampling_and_fold_assumption_bounds')
    value = amount(decision.get('ev_' + action + '_hypothetical'))
    bounds = decision.get(key)
    require(type(bounds) is list and len(bounds) == 2, 'Invalid EV bounds')
    lo, hi = map(amount, bounds)
    require(lo <= value <= hi, 'EV estimate outside bounds')
    return (lo, hi)


def rank(recording_path, batch_directory, attachment_path, output_path, *, min_separation='0'):
    recording, directory, attachment, output = map(Path, (
        recording_path, batch_directory, attachment_path, output_path))
    threshold = amount(min_separation)
    require(threshold >= 0, 'Negative threshold')
    require(directory.is_dir() and not directory.is_symlink() and
            output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink() and
            not output.resolve().is_relative_to(directory.resolve()),
            'Unsafe output destination')
    require(len({str(p.resolve()) for p in (recording, attachment, output)}) == 3,
            'Input/output path collision')
    video_sha, report_sha = digest(recording), digest(attachment)
    report = read(attachment)
    require(type(report) is dict and report.get('schema_version') == 1 and
            report.get('analysis_status') == 'offline_reviewed_clip_hypothetical_ev_attachment_only' and
            report.get('source_recording_sha256') == video_sha and
            report.get('recording_and_exported_clip_hashes_checked') is True and
            report.get('video_evidence_independently_verified') is False and
            report.get('range_assumptions_verified') is False and
            report.get('ev_is_conditional_not_decision_quality') is True and
            report.get('automatic_clip_selection_authorized') is False and
            report.get('action_recommendation_authorized') is False and
            all(sha(report.get(k)) for k in (
                'source_clip_hand_links_sha256', 'source_batch_report_sha256',
                'source_hand_candidates_sha256')) and
            type(report.get('clips')) is list and
            1 <= len(report['clips']) <= MAX_CLIPS and
            type(report.get('clip_count')) is int and
            report['clip_count'] == len(report['clips']),
            'Untrusted EV attachment report')
    rows, seen_clips, seen_filenames, seen_decisions, checked = [], set(), set(), set(), {}
    for clip in report['clips']:
        require(type(clip) is dict and type(clip.get('table_id')) is int and
                1 <= clip['table_id'] <= 4 and
                type(clip.get('hand_id')) is str and 1 <= len(clip['hand_id']) <= 64 and
                clip.get('game_type_human_declared') in ('PLO5', 'PLO6') and
                clip.get('decision_quality_verified') is False and
                type(clip.get('decision_count')) is int and
                type(clip.get('hypothetical_ev_decisions')) is list and
                clip['decision_count'] == len(clip['hypothetical_ev_decisions']),
                'Invalid clip identity or decision count')
        identity = (clip['table_id'], clip['hand_id'])
        require(identity not in seen_clips, 'Duplicate hand/clip identity')
        seen_clips.add(identity)
        name = clip.get('clip_file')
        require(type(name) is str and SAFE_FILE.fullmatch(name) and
                name.endswith('.mp4') and sha(clip.get('clip_sha256')),
                'Unsafe clip filename/digest')
        require(name not in seen_filenames, 'Clip file reused for different hands')
        seen_filenames.add(name)
        path = directory / name
        require(path.parent == directory and path.is_file() and not path.is_symlink(),
                'Missing or symlinked MP4')
        actual = digest(path)
        require(actual == clip['clip_sha256'], 'MP4 hash mismatch')
        checked[str(path.resolve())] = actual
        hand_window, clip_window = clip.get('candidate_window_seconds'), clip.get('clip_window_seconds')
        require(type(hand_window) is list and len(hand_window) == 2 and
                type(clip_window) is list and len(clip_window) == 2,
                'Invalid timestamp windows')
        hs, he = map(timestamp, hand_window)
        cs, ce = map(timestamp, clip_window)
        require(cs <= hs < he <= ce and hs-cs <= 15 and ce-he <= 15,
                'Hand/clip windows inconsistent')
        for d in clip['hypothetical_ev_decisions']:
            require(type(d) is dict and type(d.get('decision_id')) is str and
                    1 <= len(d['decision_id'].strip()) <= 1000 and
                    d.get('observed_action_label') in ACTIONS and
                    d.get('model_conditional_only') is True and
                    d.get('action_recommendation_authorized') is False and
                    d.get('decision_quality_verified') is False and
                    sha(d.get('source_reviewed_decision_ev_link_sha256')) and
                    sha(d.get('source_ev_report_sha256')) and
                    sha(d.get('source_ev_scenario_sha256')) and
                    type(d.get('call_range_assumption')) is str and
                    bool(d['call_range_assumption'].strip()) and
                    type(d.get('raise_called_range_assumption')) is str and
                    bool(d['raise_called_range_assumption'].strip()),
                    'Untrusted hypothetical decision')
            key = (*identity, d['decision_id'])
            require(key not in seen_decisions, 'Duplicate decision')
            seen_decisions.add(key)
            t = timestamp(d.get('action_pts_seconds'))
            require(hs <= t <= he, 'Decision timestamp outside hand')
            p = amount(d.get('fold_probability_hypothesis'))
            require(0 <= p <= 1 and amount(d.get('reviewed_pot_units')) >= 0,
                    'Invalid pot or fold hypothesis')
            bounds = {a: interval(d, a) for a in ACTIONS}
            observed = d['observed_action_label']
            obs_lo, obs_hi = bounds[observed]
            others = [a for a in ACTIONS if a != observed]
            # Separation of *reported conditional intervals* only, never proof of a mistake.
            lower = max(bounds[a][0] - obs_hi for a in others)
            upper = max(bounds[a][1] - obs_lo for a in others)
            if lower > threshold:
                label = 'model_interval_separated_manual_review'
                tier = 0
            elif upper > threshold:
                label = 'overlapping_intervals_manual_review'
                tier = 1
            else:
                label = 'no_positive_model_gap_detected'
                tier = 2
            rows.append((tier, max(lower, Decimal('0')), max(upper, Decimal('0')),
                         {'table_id': identity[0], 'hand_id': identity[1],
                          'game_type': clip['game_type_human_declared'],
                          'clip_file': name, 'clip_sha256': actual,
                          'clip_window_seconds': [cs, ce],
                          'candidate_window_seconds': [hs, he],
                          'decision_id': d['decision_id'],
                          'action_pts_seconds': t,
                          'observed_action': observed,
                          'review_label': label,
                          'positive_interval_separation_units': str(max(lower, Decimal('0'))),
                          'possible_gap_upper_units': str(max(upper, Decimal('0'))),
                          'observed_ev_interval_units': [str(obs_lo), str(obs_hi)],
                          'fold_probability_hypothesis': d['fold_probability_hypothesis'],
                          'call_range_assumption': d['call_range_assumption'],
                          'raise_called_range_assumption': d['raise_called_range_assumption'],
                          'source_ev_report_sha256': d['source_ev_report_sha256'],
                          'review_explanation': (
                              'Prioridade somente para revisao humana: comparacao de intervalos '
                              'de EV condicionais ao modelo fornecido. A acao observada foi '
                              + observed + '; nao foi comprovado erro de decisao.'),
                          'range_hypotheses_not_verified': True,
                          'future_actions_not_modelled_completely': True,
                          'model_sampling_bounds_not_total_uncertainty': True,
                          'human_review_required': True,
                          'decision_quality_verified': False,
                          'automatic_clip_selection_authorized': False,
                          'action_recommendation_authorized': False,
                          'source_reviewed_decision_ev_link_sha256':
                              d['source_reviewed_decision_ev_link_sha256']}))
    require(type(report.get('decision_count')) is int and
            report['decision_count'] == len(rows) and
            1 <= len(rows) <= MAX_DECISIONS,
            'Decision count mismatch or empty input')
    rows.sort(key=lambda r: (r[0], -r[1], -r[2], r[3]['action_pts_seconds'],
                             r[3]['table_id'], r[3]['hand_id'], r[3]['decision_id']))
    require(digest(recording) == video_sha and digest(attachment) == report_sha and
            all(digest(p) == value for p, value in checked.items()),
            'Inputs changed during processing')
    result = {
        'schema_version': 1,
        'analysis_status': 'offline_hypothetical_ev_manual_review_priority_only',
        'source_recording_sha256': video_sha,
        'source_ev_attachments_sha256': report_sha,
        'clip_count': len(seen_clips), 'decision_count': len(rows),
        'min_conditional_interval_separation_units': str(threshold),
        'video_evidence_independently_verified': False,
        'range_assumptions_verified': False,
        'decision_quality_verified': False,
        'automatic_clip_selection_authorized': False,
        'action_recommendation_authorized': False,
        'clip_media_hashes_rechecked': True,
        'original_ev_sources_recomputed_in_this_step': False,
        'warning': ('Manual-review ordering based only on supplied conditional EV intervals. '
                    'Ranges, OCR, pots, action legality, future actions and true EV remain unverified. '
                    'Interval separation is NOT proof of a poker mistake.'),
        'manual_review_queue': [r[3] for r in rows],
    }
    with tempfile.TemporaryDirectory(prefix='plo_review_priority_', dir=output.parent) as tmp:
        staged = Path(tmp) / 'priority.json'
        staged.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                     allow_nan=False) + '\n', encoding='utf-8')
        os.link(staged, output)  # never overwrite an existing output
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording')
    parser.add_argument('batch_directory')
    parser.add_argument('attachments_json')
    parser.add_argument('new_priority_json')
    parser.add_argument('--min-separation', default='0')
    args = parser.parse_args(argv)
    result = rank(args.recording, args.batch_directory, args.attachments_json,
                  args.new_priority_json, min_separation=args.min_separation)
    print(json.dumps({'status': result['analysis_status'],
                      'decisions': result['decision_count']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())