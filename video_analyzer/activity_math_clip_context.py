"""Bind *hypothetical* PLO5/PLO6 math to human-selected offline MP4 clips.

A JSON sidecar only: never changes MP4s, automatically ranks clips, or calls
conditional Monte Carlo EV an observed strategic error. Inputs are checked
against the reviewed worksheet, original clip bytes, and recomputed seeded
hypothetical calculation. No poker platform integration or live assistance.
"""
import argparse
import json
import math
from pathlib import Path

from activity_hypothetical_math import MODEL, build_hypothetical_report, digest
from activity_review_clip_annotate import STATUS as CLIP_STATUS, _validate_manifest

STATUS = 'human_selected_clips_with_optional_hypothetical_math_unverified'
REPORT_STATUS = 'hypothetical_math_only_not_video_verified'
WORKSHEET_STATUS = 'scenario_worksheet_unverified_no_ev'


def _key(item):
    if not isinstance(item, dict):
        raise ValueError('Decision must be an object')
    table, hand, event = (item.get(k) for k in ('table_id', 'hand_id', 'event_index'))
    if (type(table) is not int or not 1 <= table <= 4
            or type(event) is not int or event < 0
            or not isinstance(hand, str) or not 0 < len(hand) <= 256):
        raise ValueError('Invalid decision identity')
    return (table, hand, event)


def _timestamp(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid decision timestamp')
    return value


def build_math_clip_context(manifest, clips_dir, worksheet, request, report):
    """Validate source provenance and attach unverified math without ranking."""
    if (not isinstance(manifest, dict)
            or manifest.get('analysis_status') != CLIP_STATUS
            or manifest.get('ready_for_equity_or_ev') is not False
            or manifest.get('authorized_for_ev_based_ranking') is not False
            or manifest.get('source_visual_content_verified') is not False):
        raise ValueError('Only human-selected, unverified clip manifests accepted')
    # Also checks original MP4 SHA-256, file size, dimensions, duration and symlinks.
    clips = _validate_manifest(manifest, Path(clips_dir))
    if (not isinstance(worksheet, dict)
            or worksheet.get('analysis_status') != WORKSHEET_STATUS
            or worksheet.get('ready_for_equity_or_ev') is not False
            or worksheet.get('recording_sha256') != manifest['recording_sha256']
            or worksheet.get('source_queue_sha256') != manifest['source_queue_sha256']
            or worksheet.get('source_draft_sha256') != manifest['source_draft_sha256']):
        raise ValueError('Worksheet and clips do not share attested source identity')
    if (not isinstance(report, dict)
            or report.get('analysis_status') != REPORT_STATUS
            or report.get('ready_for_equity_or_ev') is not False
            or report.get('authorized_for_clips') is not False
            or report.get('source_worksheet_sha256') != digest(worksheet)
            or report.get('source_request_sha256') != digest(request)):
        raise ValueError('Hypothetical report is unbound or claims authorization')
    # A report SHA alone cannot authenticate a result: replay the seeded model
    # and compare all fields, including CI and range assumptions.
    if report != build_hypothetical_report(worksheet, request):
        raise ValueError('Hypothetical report does not match deterministic calculation')

    scenarios = worksheet.get('scenarios')
    if not isinstance(scenarios, list):
        raise ValueError('Invalid worksheet scenarios')
    worksheet_by_key = {}
    for scenario in scenarios:
        key = _key(scenario)
        if key in worksheet_by_key:
            raise ValueError('Duplicate worksheet decision')
        _timestamp(scenario.get('decision_timestamp'))
        worksheet_by_key[key] = scenario
    math_by_key = {}
    for item in report['results']:
        key = _key(item)
        if key in math_by_key or key not in worksheet_by_key:
            raise ValueError('Duplicate or unknown hypothetical decision')
        if (item.get('ready_for_equity_or_ev') is not False
                or item.get('authorized_for_clips') is not False
                or item.get('model_acknowledgement') != MODEL):
            raise ValueError('Unauthorized hypothetical result')
        math_by_key[key] = item

    entries, seen, matched = [], set(), set()
    for clip in clips:
        key = _key(clip)
        if key in seen or key not in worksheet_by_key:
            raise ValueError('Duplicate or unknown clip decision')
        seen.add(key)
        scenario = worksheet_by_key[key]
        if (abs(_timestamp(clip['decision_timestamp']) -
                _timestamp(scenario['decision_timestamp'])) > 1e-6):
            raise ValueError('Clip/worksheet decision timestamp mismatch')
        reviewed = scenario.get('reviewed_visible_inputs')
        if not isinstance(reviewed, dict):
            raise ValueError('Missing reviewed decision fields')
        if reviewed.get('observed_action') is not None and reviewed['observed_action'] != clip['reviewed_action']:
            raise ValueError('Clip/worksheet observed action mismatch')
        entry = {
            'filename': clip['filename'], 'table_id': key[0], 'hand_id': key[1],
            'event_index': key[2], 'decision_timestamp': clip['decision_timestamp'],
            'original_mp4_sha256': clip['mp4_sha256'],
            'human_review_explanation': clip['explanation'],
            'subjective_action_confidence': clip.get('subjective_action_confidence'),
            'math_status': 'no_hypothetical_calculation', 'hypothetical_math': None,
            'eligible_for_ev_ranking': False, 'strategic_error_established': False,
        }
        if key in math_by_key:
            if (reviewed.get('observed_action') != 'call'
                    or clip['reviewed_action'] != 'call'
                    or scenario.get('unconfirmed_fields') != []):
                raise ValueError('Hypothetical call lacks matching reviewed inputs')
            matched.add(key)
            result = math_by_key[key]
            entry['math_status'] = 'conditional_heads_up_all_in_what_if_only'
            entry['hypothetical_math'] = {
                'variant': result['variant'], 'model': MODEL,
                'opponent_range': result['opponent_range'],
                'trials': result['trials'], 'seed': result['seed'],
                'equity': result['equity'],
                'equity_sampling_ci95': result['equity_sampling_ci95'],
                'call_ev_vs_fold': result['call_ev_vs_fold'],
                'call_ev_sampling_ci95': result['call_ev_sampling_ci95'],
                'pot_before_call': result['pot_before_call'],
                'call_amount': result['call_amount'],
                'caveat': ('Sampling CI excludes opponent-range uncertainty, rake, '
                           'future betting and errors in manual video reconstruction.'),
            }
        entries.append(entry)
    if matched != set(math_by_key):
        raise ValueError('Hypothetical result lacks a corresponding human-selected clip')
    return {
        'schema_version': 1, 'analysis_status': STATUS,
        'source_clip_manifest_sha256': digest(manifest),
        'source_worksheet_sha256': digest(worksheet),
        'source_request_sha256': digest(request),
        'source_math_report_sha256': digest(report),
        'recording_sha256': manifest['recording_sha256'],
        'ready_for_equity_or_ev': False, 'authorized_for_ev_based_ranking': False,
        'source_visual_content_verified': False,
        'clips': entries,
        'clips_with_hypothetical_math': len(matched),
        'warning': ('Clips were chosen by a human. Conditional Monte Carlo is an '
                    'unverified what-if, not a video-confirmed EV or proof of a mistake. '
                    'Do not rank clips or infer strategic errors from this sidecar.'),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('clip_manifest_json')
    parser.add_argument('clips_dir')
    parser.add_argument('worksheet_json')
    parser.add_argument('request_json')
    parser.add_argument('hypothetical_report_json')
    parser.add_argument('output_json')
    args = parser.parse_args(argv)
    paths = [Path(p) for p in (args.clip_manifest_json, args.worksheet_json,
                                args.request_json, args.hypothetical_report_json)]
    output = Path(args.output_json)
    if (output.exists() or output.is_symlink()
            or output.resolve() in {p.resolve() for p in paths}
            or any(not p.is_file() or p.is_symlink() for p in paths)
            or not Path(args.clips_dir).is_dir() or Path(args.clips_dir).is_symlink()):
        raise ValueError('Require existing regular inputs and a new output file')
    inputs = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
    result = build_math_clip_context(inputs[0], args.clips_dir, *inputs[1:])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'clips': len(result['clips']),
                      'with_hypothetical_math': result['clips_with_hypothetical_math'],
                      'authorized_for_ev_based_ranking': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
