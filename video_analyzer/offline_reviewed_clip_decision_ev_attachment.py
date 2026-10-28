"""Attach reviewed, hypothetical EV decisions to already exported OFFLINE MP4 clips.

Usage:
 python offline_reviewed_clip_decision_ev_attachment.py RECORDING CLIP_LINKS_JSON \
     BATCH_DIRECTORY NEW_REPORT_JSON --decision-ev REVIEWED_EV_LINK_JSON [...]

Fail closed: independently hash the local recording and all selected MP4s,
sidecars and requests; require same recording/hand/table/game, an action inside
both the reviewed hand and exported clip windows, and unchanged provenance.
Never infer unseen cards, rank decisions, select clips or recommend actions.
EV/ranges and human observations remain unverified hypotheses.
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

MAX_JSON = 4 * 1024 * 1024
MAX_REPORTS = 32
SHA = re.compile(r'[0-9a-f]{64}\Z')
SAFE_FILE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
OBS_KEYS = ('hero', 'board', 'pot', 'action')


def require(condition, message):
    if not condition:
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
    obj = {}
    for k, v in pairs:
        require(k not in obj, 'Duplicate JSON key')
        obj[k] = v
    return obj


def read(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_JSON,
            'Missing, symlinked, empty or oversized JSON')
    return json.loads(p.read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))


def number(value):
    require(type(value) in (int, float) and math.isfinite(value),
            'Invalid or non-finite timestamp')
    return float(value)


def money(value):
    require(type(value) is str and 1 <= len(value) <= 64 and
            re.fullmatch(r'-?(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,8})?', value),
            'Invalid decimal amount')
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('Invalid decimal') from exc
    require(result.is_finite(), 'Non-finite decimal')
    return result


def safe_member(directory, name):
    require(type(name) is str and SAFE_FILE.fullmatch(name) and name not in ('.', '..'),
            'Unsafe batch filename')
    path = directory / name
    require(path.is_file() and not path.is_symlink() and path.parent == directory,
            'Missing or symlinked batch member')
    return path


def verified_clip_links(links, batch, directory, video_sha, batch_sha, checked):
    require(type(links) is dict and links.get('schema_version') == 1 and
            links.get('analysis_status') == 'offline_clip_hand_provenance_links_only' and
            links.get('source_video_sha256') == video_sha and
            links.get('source_batch_report_sha256') == batch_sha and
            links.get('video_evidence_verified') is False and
            links.get('ev_verified') is False and
            links.get('automatic_clip_selection_authorized') is False and
            links.get('action_recommendation_authorized') is False and
            type(links.get('linked_clips')) is list and
            1 <= len(links['linked_clips']) <= 12 and
            links.get('clip_count') == len(links['linked_clips']),
            'Invalid or unsupported clip/hand link report')
    require(type(batch) is dict and batch.get('schema_version') == 1 and
            batch.get('analysis_status') == 'manually_selected_offline_clip_batch_only' and
            batch.get('source_video_sha256') == video_sha and
            batch.get('source_manifest_sha256') == links.get('source_batch_manifest_sha256') and
            batch.get('video_evidence_verified') is False and
            batch.get('automatic_clip_selection_authorized') is False and
            type(batch.get('clips')) is list and
            batch.get('clip_count') == len(batch['clips']) == len(links['linked_clips']),
            'Batch report no longer matches clip/hand link report')
    index = {}
    for clip, entry in zip(links['linked_clips'], batch['clips']):
        require(type(clip) is dict and type(entry) is dict,
                'Invalid clip or batch entry')
        key = (clip.get('table_id'), clip.get('hand_id'))
        require(type(key[0]) is int and 1 <= key[0] <= 4 and
                type(key[1]) is str and 1 <= len(key[1]) <= 64 and
                key not in index and
                entry.get('table_id') == key[0] and entry.get('hand_id') == key[1] and
                clip.get('game_type_human_declared') in ('PLO5', 'PLO6') and
                clip.get('decision_quality_verified') is False and
                clip.get('ev_attachment') is None,
                'Duplicate/changed clip hand identity or prior EV')
        hand_window, clip_window = clip.get('candidate_window_seconds'), clip.get('clip_window_seconds')
        require(type(hand_window) is list and len(hand_window) == 2 and
                type(clip_window) is list and len(clip_window) == 2,
                'Invalid window arrays')
        hs, he = map(number, hand_window)
        cs, ce = map(number, clip_window)
        require(0 <= cs <= hs < he <= ce and hs-cs <= 15 and ce-he <= 15 and
                entry.get('start_seconds') == cs and entry.get('end_seconds') == ce,
                'Invalid clip/hand timestamps')
        filename = clip.get('clip_file')
        require(filename == entry.get('clip_file') and
                type(filename) is str and filename.endswith('.mp4') and
                clip.get('clip_sha256') == entry.get('clip_sha256') and
                type(clip.get('clip_sha256')) is str and SHA.fullmatch(clip['clip_sha256']),
                'Clip filename or digest mismatch')
        mp4 = safe_member(directory, filename)
        sidecar = safe_member(directory, entry.get('sidecar_file'))
        request = safe_member(directory, entry.get('request_file'))
        require(sidecar.name == filename + '.json' and
                type(entry.get('request_sha256')) is str and
                SHA.fullmatch(entry['request_sha256']), 'Invalid batch members')
        checked[str(mp4.resolve())] = digest(mp4)
        checked[str(sidecar.resolve())] = digest(sidecar)
        checked[str(request.resolve())] = digest(request)
        require(checked[str(mp4.resolve())] == clip['clip_sha256'] and
                checked[str(request.resolve())] == entry['request_sha256'],
                'Exported MP4 or request has changed')
        req, meta = read(request), read(sidecar)
        require(type(req) is dict and type(meta) is dict and
                req.get('hand_id') == key[1] and req.get('table_id') == key[0] and
                req.get('source_video_sha256') == video_sha and
                req.get('reviewer_confirmed_offline') is True and
                number(req.get('start_seconds')) == cs and
                number(req.get('end_seconds')) == ce and
                meta.get('analysis_status') == 'manually_selected_offline_clip' and
                meta.get('source_video_sha256') == video_sha and
                meta.get('source_request_sha256') == entry['request_sha256'] and
                meta.get('clip_sha256') == clip['clip_sha256'] and
                meta.get('hand_id') == key[1] and meta.get('table_id') == key[0] and
                number(meta.get('start_seconds')) == cs and
                number(meta.get('end_seconds')) == ce and
                meta.get('crop') == req.get('crop') and
                meta.get('explanation') == req.get('explanation') and
                meta.get('video_evidence_verified') is False and
                meta.get('automatic_clip_selection_authorized') is False,
                'Clip request/sidecar no longer matches export')
        index[key] = (clip, cs, ce, hs, he)
    return index


def validated_decision(decision, index, video_sha, hands_sha):
    require(type(decision) is dict and decision.get('schema_version') == 1 and
            decision.get('analysis_status') == 'reviewed_offline_decision_hypothetical_ev_link_only' and
            decision.get('recording_sha256') == video_sha and
            decision.get('source_hand_candidates_sha256') == hands_sha and
            decision.get('recomputed_ev_and_audit_from_supplied_inputs') is True and
            decision.get('video_evidence_independently_verified') is False and
            decision.get('action_history_complete') is False and
            decision.get('raise_legality_verified') is False and
            decision.get('decision_quality_verified') is False and
            decision.get('automatic_clip_selection_authorized') is False and
            decision.get('action_recommendation_authorized') is False,
            'Untrusted or promoted decision EV report')
    for key in ('source_action_audit_sha256', 'source_ev_scenario_sha256',
                'source_ev_report_sha256', 'source_approval_sha256'):
        require(type(decision.get(key)) is str and SHA.fullmatch(decision[key]),
                'Missing EV provenance digest')
    identity = (decision.get('table_id'), decision.get('hand_id'))
    require(identity in index and
            decision.get('game_type') == index[identity][0]['game_type_human_declared'],
            'Decision does not belong to an exported hand/game')
    _, cs, ce, hs, he = index[identity]
    t = number(decision.get('action_pts_seconds'))
    require(hs <= t <= he and cs <= t <= ce, 'Decision timestamp outside hand/clip')
    require(type(decision.get('decision_id')) is str and
            1 <= len(decision['decision_id'].strip()) <= 1000 and
            decision.get('observed_action_label') in ('fold', 'call', 'raise') and
            type(decision.get('street_candidate_not_confirmed')) is str and
            1 <= len(decision['street_candidate_not_confirmed']) <= 100 and
            type(decision.get('reviewer_note')) is str and
            1 <= len(decision['reviewer_note'].strip()) <= 1000,
            'Invalid decision identity or human context')
    indices, crops = decision.get('reviewed_observation_indices'), decision.get('source_crop_sha256')
    require(type(indices) is dict and set(indices) == set(OBS_KEYS) and
            all(type(indices[k]) is int and 0 <= indices[k] < 32 for k in OBS_KEYS) and
            len(set(indices.values())) == 4 and
            type(crops) is dict and set(crops) == set(OBS_KEYS) and
            all(type(crops[k]) is str and SHA.fullmatch(crops[k]) for k in OBS_KEYS),
            'Invalid reviewed observation provenance')
    pot = money(decision.get('pot_before_decision_as_reviewed'))
    require(pot >= 0, 'Negative reviewed pot')
    values = {key: money(decision.get(key)) for key in
              ('conditional_ev_fold', 'conditional_ev_call', 'conditional_ev_raise')}
    require(values['conditional_ev_fold'] == 0, 'Unexpected fold EV baseline')
    for value_key, bound_key in (
        ('conditional_ev_call', 'conditional_ev_call_sampling_bounds'),
        ('conditional_ev_raise', 'conditional_ev_raise_sampling_and_fold_assumption_bounds'),
    ):
        bounds = decision.get(bound_key)
        require(type(bounds) is list and len(bounds) == 2,
                'Missing EV uncertainty bounds')
        lo, hi = map(money, bounds)
        require(lo <= values[value_key] <= hi, 'EV estimate outside reported bounds')
    fold_prob = money(decision.get('fold_probability_hypothesis'))
    require(0 <= fold_prob <= 1, 'Invalid fold probability')
    for k in ('call_range_assumption', 'raise_called_range_assumption'):
        require(type(decision.get(k)) is str and
                1 <= len(decision[k].strip()) <= 1000,
                'Missing explicit range assumption')
    return identity, {
        'decision_id': decision['decision_id'],
        'observed_action_label': decision['observed_action_label'],
        'action_pts_seconds': t,
        'street_candidate_not_confirmed': decision['street_candidate_not_confirmed'],
        'reviewed_pot_units': str(pot),
        'ev_fold_hypothetical': decision['conditional_ev_fold'],
        'ev_call_hypothetical': decision['conditional_ev_call'],
        'ev_raise_hypothetical': decision['conditional_ev_raise'],
        'ev_call_sampling_bounds': decision['conditional_ev_call_sampling_bounds'],
        'ev_raise_sampling_and_fold_assumption_bounds':
            decision['conditional_ev_raise_sampling_and_fold_assumption_bounds'],
        'fold_probability_hypothesis': decision['fold_probability_hypothesis'],
        'call_range_assumption': decision['call_range_assumption'],
        'raise_called_range_assumption': decision['raise_called_range_assumption'],
        'reviewed_observation_indices': indices,
        'source_crop_sha256': crops,
        'source_ev_scenario_sha256': decision['source_ev_scenario_sha256'],
        'source_ev_report_sha256': decision['source_ev_report_sha256'],
        'source_approval_sha256': decision['source_approval_sha256'],
        'reviewer_note': decision['reviewer_note'],
        'model_conditional_only': True,
        'action_recommendation_authorized': False,
        'decision_quality_verified': False,
    }


def attach(recording_path, clip_links_path, batch_directory, output_path, *, decision_paths):
    recording, links_path, directory, output = map(Path, (
        recording_path, clip_links_path, batch_directory, output_path))
    reports = tuple(map(Path, decision_paths))
    require(1 <= len(reports) <= MAX_REPORTS, 'Require 1-32 reviewed EV reports')
    require(directory.is_dir() and not directory.is_symlink() and
            output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink() and
            not output.resolve().is_relative_to(directory.resolve()),
            'Output must be new and outside batch directory')
    inputs = (recording, links_path, directory / 'batch_report.json', *reports)
    require(len({str(p.resolve()) for p in inputs}) == len(inputs) and
            all(output.resolve() != p.resolve() for p in inputs),
            'Duplicate input or output overlaps source')
    checked = {str(p.resolve()): digest(p) for p in inputs}
    video_sha, links_sha, batch_sha = (checked[str(p.resolve())] for p in inputs[:3])
    links, batch = read(links_path), read(directory / 'batch_report.json')
    index = verified_clip_links(links, batch, directory, video_sha, batch_sha, checked)
    hands_sha = links.get('source_hand_candidates_sha256')
    require(type(hands_sha) is str and SHA.fullmatch(hands_sha),
            'Invalid hand candidates digest')
    attachments = {key: [] for key in index}
    used = set()
    for p in reports:
        report = read(p)
        key, attachment = validated_decision(report, index, video_sha, hands_sha)
        decision_key = (key[0], key[1], attachment['decision_id'])
        require(decision_key not in used, 'Duplicate decision attachment')
        used.add(decision_key)
        attachment['source_reviewed_decision_ev_link_sha256'] = checked[str(p.resolve())]
        attachments[key].append(attachment)
    result_clips = []
    for key, (clip, _, _, _, _) in index.items():
        decisions = sorted(attachments[key], key=lambda x: (x['action_pts_seconds'], x['decision_id']))
        result_clips.append({
            'table_id': key[0], 'hand_id': key[1],
            'game_type_human_declared': clip['game_type_human_declared'],
            'clip_file': clip['clip_file'], 'clip_sha256': clip['clip_sha256'],
            'clip_window_seconds': clip['clip_window_seconds'],
            'candidate_window_seconds': clip['candidate_window_seconds'],
            'decision_count': len(decisions), 'hypothetical_ev_decisions': decisions,
            'decision_quality_verified': False,
        })
    require(all(digest(Path(k)) == v for k, v in checked.items()),
            'Input changed during provenance check')
    result = {
        'schema_version': 1,
        'analysis_status': 'offline_reviewed_clip_hypothetical_ev_attachment_only',
        'source_recording_sha256': video_sha,
        'source_clip_hand_links_sha256': links_sha,
        'source_batch_report_sha256': batch_sha,
        'source_hand_candidates_sha256': hands_sha,
        'clip_count': len(result_clips), 'decision_count': len(reports),
        'clips': result_clips,
        'recording_and_exported_clip_hashes_checked': True,
        'video_evidence_independently_verified': False,
        'range_assumptions_verified': False,
        'ev_is_conditional_not_decision_quality': True,
        'automatic_clip_selection_authorized': False,
        'action_recommendation_authorized': False,
        'warning': 'Offline consistency and file-integrity attachment only. Visible cards, '
                   'pot, ranges, future betting, action legality and EV assumptions are '
                   'not independently authenticated. Do not interpret EV as proven error.',
    }
    with tempfile.TemporaryDirectory(prefix='plo_clip_ev_', dir=output.parent) as tmp:
        staged = Path(tmp) / 'report.json'
        staged.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                     allow_nan=False) + '\n', encoding='utf-8')
        os.link(staged, output)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording')
    parser.add_argument('clip_links')
    parser.add_argument('batch_directory')
    parser.add_argument('new_report')
    parser.add_argument('--decision-ev', nargs='+', required=True)
    args = parser.parse_args(argv)
    result = attach(args.recording, args.clip_links, args.batch_directory,
                    args.new_report, decision_paths=args.decision_ev)
    print(json.dumps({'status': result['analysis_status'],
                      'clips': result['clip_count'],
                      'decisions': result['decision_count']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
