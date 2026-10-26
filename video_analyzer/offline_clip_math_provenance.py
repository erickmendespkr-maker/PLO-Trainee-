"""Bind an already-exported *manual* MP4 clip to a hypothetical PLO math result.

Offline provenance manifest only. Does not infer hand boundaries, verify OCR,
recompute Monte Carlo, promote subjective confidence, or authorize auto-clips.
The clip's existing human subtitle is not replaced by a strategic verdict.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from offline_manual_clip_export import digest_file, probe, validate_selection, require
from offline_job_hand_history_draft import validate_hand

MAX_JSON = 16 * 1024 * 1024
MAX_REPORT = 128 * 1024
SHA = re.compile(r'[0-9a-f]{64}\Z')


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def _pairs(items):
    d = {}
    for k, v in items:
        require(k not in d, 'Duplicate JSON key')
        d[k] = v
    return d


def load(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and p.stat().st_size <= MAX_JSON,
            'Unsafe or oversized JSON')
    raw = p.read_bytes()
    require(len(raw) <= MAX_JSON, 'Oversized JSON')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x))), raw
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid UTF-8 JSON') from exc


def canonical_sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _false_flags(obj, keys):
    require(type(obj) is dict and all(obj.get(k) is False for k in keys),
            'Unexpected verification/automation authorization')


def _math_result(result, hand, form):
    require(type(result) is dict and result.get('status') == 'hypothetical_only_not_video_verified',
            'Only explicit hypothetical math can be linked')
    _false_flags(result, ('hand_reconstruction_verified', 'strategic_error_established',
                          'automatic_clip_selection_authorized'))
    require(result.get('variant') == hand['human_entry']['variant'] and
            result.get('variant') in ('PLO5', 'PLO6'), 'Math variant mismatch')
    require(type(form) is dict and form.get('human_confirmed') is True and
            finite(form.get('timestamp')), 'Missing attested decision timestamp')
    stamp = form['timestamp']
    fields = form.get('reviewed_fields')
    require(type(fields) is dict and set(fields) ==
            {'hero_cards', 'board', 'observed_action', 'pot_before_action', 'call_amount'},
            'Invalid reviewed decision fields')
    for item in fields.values():
        require(type(item) is dict and set(item) ==
                {'value', 'confidence', 'source_timestamp', 'source', 'human_confirmed'} and
                item['human_confirmed'] is True and finite(item['confidence']) and
                0 <= item['confidence'] <= 1 and finite(item['source_timestamp']) and
                abs(item['source_timestamp'] - stamp) <= .05 and
                item['source'] == 'independent_manual_video_review',
                'Incomplete independent manual field review')
    require(fields['hero_cards']['value'] == hand['human_entry']['hero_cards'] and
            fields['pot_before_action']['value'] == hand['human_entry']['pot_before_decision'] and
            fields['call_amount']['value'] == hand['human_entry']['call_amount'],
            'Reviewed decision contradicts human hand history')
    board = hand['human_entry']['board_by_street']
    known = (board['flop'] or []) + ([board['turn']] if board['turn'] else []) + (
        [board['river']] if board['river'] else [])
    require(type(fields['board']['value']) is list and
            fields['board']['value'] == known[:len(fields['board']['value'])] and
            len(fields['board']['value']) in (0, 3, 4, 5),
            'Reviewed board contradicts human hand history')
    require(type(form.get('monte_carlo_trials')) is int and
            form['monte_carlo_trials'] == result.get('trials') and
            type(form.get('monte_carlo_seed')) is int and
            form['monte_carlo_seed'] == result.get('seed') and
            form.get('model_notes') == result.get('model_notes'),
            'Math result parameters contradict filled worksheet')
    action = result.get('observed_action_assumed')
    require(fields['observed_action']['value'] == action,
            'Reviewed action contradicts math result')
    require(action in ('call', 'raise') and
            any(a.get('actor') == 'hero' and a.get('action') == action and
                finite(a.get('source_pts_seconds')) and
                abs(a['source_pts_seconds'] - stamp) <= 0.05
                for a in hand['human_entry']['actions']), 'Decision not in human hand history')
    for key in ('equity', 'human_confidence_subjective'):
        require(finite(result.get(key)) and 0 <= result[key] <= 1, 'Invalid math confidence/equity')
    for key in ('equity_sampling_ci95', 'ev_sampling_ci95'):
        interval = result.get(key)
        require(type(interval) is list and len(interval) == 2 and
                all(finite(x) for x in interval) and interval[0] <= interval[1],
                'Invalid sampling interval')
    require(0 <= result['equity_sampling_ci95'][0] <=
            result['equity_sampling_ci95'][1] <= 1, 'Invalid equity CI')
    require(finite(result.get('ev_vs_fold_zero')), 'Invalid EV')
    require(type(result.get('trials')) is int and 1 <= result['trials'] <= 10_000_000 and
            type(result.get('seed')) is int and 0 <= result['seed'] <= 2**63 - 1,
            'Invalid Monte Carlo parameters')
    require(all(type(result.get(k)) is int and 0 <= result[k] <= result['trials']
                for k in ('wins', 'ties', 'losses')) and
            sum(result[k] for k in ('wins', 'ties', 'losses')) == result['trials'],
            'Invalid Monte Carlo outcomes')
    require(type(result.get('model_notes')) is str and
            type(result.get('model_limitations')) is str and
            0 < len(result['model_limitations']) <= 2000, 'Missing model limitations')
    return stamp


def build_link(source, clip, sidecar, audit, draft, worksheet, filled, math_report,
               table_id, hand_label, *, source_sha, clip_sha, file_shas):
    require(type(table_id) is int and 1 <= table_id <= 4 and
            type(hand_label) is str and 0 < len(hand_label) <= 64, 'Invalid hand identity')
    require(type(source_sha) is str and SHA.fullmatch(source_sha) and
            type(clip_sha) is str and SHA.fullmatch(clip_sha), 'Invalid media digest')
    require(type(sidecar) is dict and sidecar.get('schema_version') == 1 and
            sidecar.get('status') == 'manual_clip_not_video_hand_verified',
            'Not a manual clip export')
    _false_flags(sidecar, ('source_pts_boundaries_verified', 'hand_reconstruction_verified',
                           'math_analysis_linked', 'strategic_error_established',
                           'automatic_clip_selection_authorized'))
    sel = validate_selection(sidecar.get('selection'))
    require(sel['recording_sha256'] == source_sha and sidecar.get('source_sha256') == source_sha and
            sidecar.get('output_sha256') == clip_sha and sel['table_id'] == table_id,
            'Clip/source/table identity mismatch')
    require(sel['end_seconds'] <= source['duration_seconds'] + .01 and
            abs(clip['duration_seconds'] - (sel['end_seconds'] - sel['start_seconds'])) <= .35 and
            finite(sidecar.get('output_duration_seconds')) and
            abs(sidecar['output_duration_seconds'] - clip['duration_seconds']) <= .05,
            'Clip duration mismatch')
    crop = sel['crop']
    if crop:
        require(crop['x'] + crop['width'] <= source['width'] and
                crop['y'] + crop['height'] <= source['height'] and
                clip['width'] == crop['width'] and clip['height'] == crop['height'],
                'Crop geometry mismatch')
    else:
        require(clip['width'] == source['width'] and clip['height'] == source['height'],
                'Clip geometry mismatch')

    require(type(audit) is dict and audit.get('schema_version') == 1 and
            audit.get('status') == 'bounded_source_frame_pts_observation_not_hand_verified' and
            audit.get('source_sha256') == source_sha and
            audit.get('selection_sha256') == canonical_sha(sel) and
            audit.get('table_id_human_selected') == table_id and
            audit.get('source_frame_pts_observed') is True, 'PTS audit provenance mismatch')
    _false_flags(audit, ('hand_start_or_end_pts_verified', 'hand_reconstruction_verified',
                         'math_analysis_linked', 'strategic_error_established',
                         'automatic_clip_selection_authorized'))
    require(finite(audit.get('source_video_start_pts_seconds')) and
            abs(audit['source_video_start_pts_seconds']) <= .05 and
            finite(audit.get('container_duration_seconds')) and
            abs(audit['container_duration_seconds'] - source['duration_seconds']) <= .05,
            'PTS audit source origin/duration mismatch')
    edges = audit.get('edges')
    require(type(edges) is dict and set(edges) == {'start_seconds', 'end_seconds'},
            'Missing frame observations')
    tolerance = audit.get('tolerance_seconds')
    require(finite(tolerance) and .01 <= tolerance <= 1, 'Invalid audit tolerance')
    for key in edges:
        e = edges[key]
        require(type(e) is dict and finite(e.get('requested_seconds')) and
                abs(e['requested_seconds'] - sel[key]) <= 1e-6 and
                finite(e.get('absolute_offset_seconds')) and
                type(e.get('observed_frame_within_tolerance')) is bool and
                e.get('sample_is_not_exhaustive_or_globally_nearest_proof') is True and
                finite(e.get('nearest_observed_frame_pts_seconds')) and
                abs(abs(e['nearest_observed_frame_pts_seconds'] - sel[key]) -
                    e['absolute_offset_seconds']) <= .00001 and
                e['observed_frame_within_tolerance'] is
                (e['absolute_offset_seconds'] <= tolerance),
                'PTS observation mismatch')
    require(audit.get('both_edges_have_observed_frames_within_tolerance') is
            all(edges[k]['observed_frame_within_tolerance'] for k in edges),
            'Contradictory PTS tolerance flags')

    require(type(draft) is dict and draft.get('schema_version') == 1 and
            draft.get('analysis_status') == 'human_entered_hand_history_drafts_no_math' and
            draft.get('source_sha256') == source_sha and
            draft.get('timestamp_semantics') == 'human_claimed_pts_not_independently_verified' and
            draft.get('requires_source_video_reaudit') is True, 'Hand draft provenance mismatch')
    _false_flags(draft, ('hand_start_or_end_pts_verified', 'hand_reconstruction_verified',
                         'ready_for_equity_or_ev', 'automatic_clip_selection_authorized'))
    hands = draft.get('hands')
    require(type(hands) is list and len(hands) <= 2000, 'Invalid hand drafts')
    matches = [h for h in hands if type(h) is dict and
               h.get('table_id') == table_id and h.get('hand_label_human_assigned') == hand_label]
    require(len(matches) == 1, 'Hand identity missing or ambiguous')
    hand = matches[0]
    require(hand.get('status') == 'structurally_complete_human_draft_unverified' and
            validate_hand(hand['human_entry'], hand), 'Incomplete hand draft')
    _false_flags(hand, ('hand_reconstruction_verified', 'ready_for_equity_or_ev',
                        'automatic_clip_selection_authorized'))
    claimed = [hand['human_entry']['source_pts_start_seconds'],
               hand['human_entry']['source_pts_end_seconds']]
    require(all(finite(x) for x in claimed) and claimed[0] < claimed[1] and
            sel['start_seconds'] < claimed[1] and sel['end_seconds'] > claimed[0],
            'Clip does not overlap human-claimed hand interval')

    require(type(worksheet) is dict and worksheet.get('schema_version') == 1 and
            worksheet.get('analysis_status') == 'manual_hypothetical_math_review_not_video_verified' and
            worksheet.get('job_id') == draft.get('job_id') and
            worksheet.get('source_draft_sha256') == file_shas['draft'] and
            worksheet.get('recording_sha256_unverified') == source_sha,
            'Worksheet provenance mismatch')
    _false_flags(worksheet, ('ready_for_equity_or_ev', 'hand_reconstruction_verified',
                             'automatic_clip_selection_authorized'))
    require(type(filled) is dict and type(worksheet.get('tasks')) is list and
            type(filled.get('tasks')) is list and
            len(filled['tasks']) == len(worksheet['tasks']), 'Invalid filled worksheet')
    protected = copy.deepcopy(filled)
    for index, task in enumerate(worksheet['tasks']):
        require(type(task) is dict and type(protected['tasks'][index]) is dict and
                type(task.get('manual_scenario_draft')) is dict and
                task['manual_scenario_draft'].get('human_confirmed') is False and
                task['manual_scenario_draft'].get('timestamp') is None,
                'Invalid blank worksheet')
        protected['tasks'][index]['manual_scenario_draft'] = task['manual_scenario_draft']
    require(protected == worksheet, 'Filled worksheet changed protected metadata')
    task_matches = [t for t in filled['tasks'] if t.get('table_id') == table_id and
                    t.get('hand_label_human_assigned') == hand_label]
    require(len(task_matches) == 1 and
            task_matches[0].get('source_human_entry_sha256') == canonical_sha(hand['human_entry']) and
            task_matches[0].get('source_nominal_interval_seconds') == hand['source_nominal_interval_seconds'],
            'Worksheet hand identity mismatch')
    form = task_matches[0]['manual_scenario_draft']

    require(type(math_report) is dict and math_report.get('schema_version') == 1 and
            math_report.get('analysis_status') == 'hypothetical_math_from_unverified_hand_drafts' and
            math_report.get('job_id') == draft['job_id'] and
            math_report.get('source_draft_sha256') == file_shas['draft'] and
            math_report.get('source_worksheet_sha256') == canonical_sha(worksheet) and
            math_report.get('source_filled_worksheet_sha256') == canonical_sha(filled),
            'Math result provenance mismatch')
    _false_flags(math_report, ('ready_for_equity_or_ev', 'hand_reconstruction_verified',
                               'strategic_error_established', 'automatic_clip_selection_authorized'))
    results = math_report.get('results')
    require(type(results) is list and len(results) == len(hands), 'Math result count mismatch')
    hand_ids = [(h.get('table_id'), h.get('hand_label_human_assigned')) for h in hands]
    task_ids = [(t.get('table_id'), t.get('hand_label_human_assigned'))
                for t in worksheet['tasks']]
    result_ids = [(r.get('table_id'), r.get('hand_label_human_assigned'))
                  for r in results if type(r) is dict]
    require(len(set(hand_ids)) == len(hands) and len(set(task_ids)) == len(hands) and
            len(set(result_ids)) == len(hands) and
            set(hand_ids) == set(task_ids) == set(result_ids),
            'Duplicate or missing hand/math identities')
    counts = math_report.get('counts')
    require(type(counts) is dict and counts.get('total') == len(results) and
            counts.get('hypothetical') == sum(r.get('status') == 'hypothetical_only_not_video_verified'
                                              for r in results) and
            counts.get('blocked') == sum(str(r.get('status', '')).startswith('blocked_')
                                       for r in results) and
            counts.get('skipped') == sum(str(r.get('status', '')).startswith('skipped_')
                                       for r in results), 'Math result counts mismatch')
    matches = [r for r in results if type(r) is dict and r.get('table_id') == table_id and
               r.get('hand_label_human_assigned') == hand_label]
    require(len(matches) == 1 and
            matches[0].get('source_human_entry_sha256') == canonical_sha(hand['human_entry']),
            'Math result hand mismatch')
    result = matches[0]
    stamp = _math_result(result, hand, form)
    require(sel['start_seconds'] <= stamp <= sel['end_seconds'],
            'Clip does not contain the manually documented decision timestamp')
    require(claimed[0] <= stamp <= claimed[1], 'Decision outside human-claimed hand interval')

    return {
        'schema_version': 1,
        'status': 'manual_clip_linked_to_hypothetical_math_not_video_verified',
        'job_id': draft['job_id'], 'table_id': table_id,
        'hand_label_human_assigned': hand_label,
        'source_recording_sha256': source_sha,
        'clip_mp4_sha256': clip_sha,
        'input_json_sha256': file_shas,
        'clip_selection_seconds_human': [sel['start_seconds'], sel['end_seconds']],
        'decision_timestamp_seconds_human': stamp,
        'hand_interval_seconds_human_claimed': claimed,
        'frame_pts_audit_within_tolerance_observed': audit['both_edges_have_observed_frames_within_tolerance'],
        'hypothetical_math': {
            'action_assumed': result['observed_action_assumed'],
            'variant': result['variant'], 'equity': result['equity'],
            'equity_sampling_ci95': result['equity_sampling_ci95'],
            'ev_vs_fold_zero': result['ev_vs_fold_zero'],
            'ev_sampling_ci95': result['ev_sampling_ci95'],
            'monte_carlo_trials': result['trials'], 'monte_carlo_seed': result['seed'],
            'opponent_range_combinations': result.get('opponent_range_combinations'),
            'model_notes': result['model_notes'],
            'model_limitations': result['model_limitations'],
            'human_confidence_subjective': result['human_confidence_subjective'],
        },
        'clip_and_math_linked_by_manual_identifiers': True,
        'math_result_independently_recomputed': False,
        'hand_start_or_end_pts_verified': False,
        'hand_reconstruction_verified': False,
        'strategic_error_established': False,
        'automatic_clip_selection_authorized': False,
        'warning': ('Provenance association only. OCR, hand boundaries, decision PTS and ranges '
                    'are not independently verified; the supplied Monte Carlo result is not '
                    'recomputed. Its 95% CI reflects sampling, not range/model uncertainty. '
                    'The MP4 subtitle remains human-authored, not a proven strategic verdict.'),
    }


def export_link(source_path, clip_path, sidecar_path, audit_path, draft_path,
                worksheet_path, filled_path, math_path, table_id, hand_label, output_path):
    inputs = [Path(x) for x in (source_path, clip_path, sidecar_path, audit_path,
                               draft_path, worksheet_path, filled_path, math_path)]
    output = Path(output_path)
    require(len({p.resolve() for p in inputs + [output]}) == len(inputs) + 1,
            'Overlapping paths')
    require(output.suffix.lower() == '.json' and output.parent.is_dir() and
            not output.parent.is_symlink() and not output.exists(), 'Unsafe output')
    source, clip = inputs[:2]
    require(all(p.is_file() and not p.is_symlink() for p in (source, clip)),
            'Unsafe video input')
    loaded = [load(p) for p in inputs[2:]]
    sidecar, audit, draft, worksheet, filled, math_report = [row[0] for row in loaded]
    file_shas = dict(zip(('sidecar', 'audit', 'draft', 'worksheet', 'filled', 'math'),
                         (hashlib.sha256(raw).hexdigest() for _, raw in loaded)))
    source_sha, clip_sha = digest_file(source), digest_file(clip)
    result = build_link(probe(source), probe(clip), sidecar, audit, draft, worksheet,
                        filled, math_report, table_id, hand_label,
                        source_sha=source_sha, clip_sha=clip_sha, file_shas=file_shas)
    require(all(p.read_bytes() == raw for p, (_, raw) in zip(inputs[2:], loaded)) and
            digest_file(source) == source_sha and digest_file(clip) == clip_sha,
            'Input changed during linking')
    payload = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False).encode() + b'\n'
    require(len(payload) <= MAX_REPORT, 'Oversized provenance manifest')
    fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            require(stat.S_ISREG(os.fstat(f.fileno()).st_mode), 'Unsafe output file')
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('recording', 'clip_mp4', 'clip_sidecar_json', 'frame_audit_json',
                'hand_drafts_json', 'math_worksheet_json', 'filled_worksheet_json',
                'math_results_json'):
        parser.add_argument(arg)
    parser.add_argument('--table', type=int, required=True)
    parser.add_argument('--hand', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    result = export_link(args.recording, args.clip_mp4, args.clip_sidecar_json,
                         args.frame_audit_json, args.hand_drafts_json,
                         args.math_worksheet_json, args.filled_worksheet_json,
                         args.math_results_json, args.table, args.hand, args.output)
    print(json.dumps({'status': result['status'], 'clip_mp4_sha256': result['clip_mp4_sha256']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
