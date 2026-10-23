"""Offline, non-authorizing review triage for human-selected PLO5/PLO6 clips.

This is a *review workload* classifier, not strategic ranking. It replays the
hypothetical Monte Carlo and validates source MP4 hashes through
``build_explanations``. No error verdict, clip selection, or EV-based ordering.
"""
import argparse
import json
import math
from pathlib import Path

from activity_hypothetical_math import digest
from activity_math_explanation import build_explanations

STATUS = 'review_attention_candidates_unverified_no_auto_selection'
FIELDS = ('hero_cards', 'board', 'observed_action', 'pot_before_action', 'call_amount')


def _nonnegative(value):
    return (type(value) in (int, float) and math.isfinite(value) and value >= 0)


def build_review_triage(manifest, clips_dir, worksheet, request, report):
    """Group clips for human follow-up without claiming a strategic mistake.

    Exposure >= 25% of the *reviewed* pre-action pot is only a configurable
    attention heuristic. It is not EV, and is never used for automatic cuts.
    """
    explanations = build_explanations(manifest, clips_dir, worksheet, request, report)
    rows = []
    seen = set()
    for clip in explanations['clips']:
        key = (clip['table_id'], clip['hand_id'], clip['event_index'])
        if key in seen:
            raise ValueError('Duplicate review identity')
        seen.add(key)
        review = clip['observed_review']
        missing = review['unconfirmed_fields']
        if (not isinstance(missing, list) or len(set(missing)) != len(missing)
                or any(field not in FIELDS for field in missing)):
            raise ValueError('Invalid unconfirmed field list')
        pot, call = review['pot_before_action'], review['call_amount']
        if pot is not None and not _nonnegative(pot):
            raise ValueError('Invalid reviewed pot')
        if call is not None and not _nonnegative(call):
            raise ValueError('Invalid reviewed call')
        # Do not promote an incomplete review into a decision recommendation.
        if missing:
            category, rationale, exposure = (
                'needs_evidence', 'Missing human-attested visible fields', None)
        elif review['action'] == 'call' and pot is not None and pot > 0 and call is not None:
            exposure = round(call / pot, 6)
            if exposure >= .25:
                category = 'human_attention_suggested'
                rationale = 'Reviewed call >=25% of reviewed pot; heuristic only'
            else:
                category = 'human_review_optional'
                rationale = 'Reviewed call <25% of reviewed pot; heuristic only'
        else:
            category, rationale, exposure = (
                'human_review_optional', 'No applicable call-exposure heuristic', None)
        result = clip['conditional_result']
        rows.append({
            'table_id': key[0], 'hand_id': key[1], 'event_index': key[2],
            'decision_timestamp': clip['decision_timestamp'],
            'filename': clip['filename'],
            'original_mp4_sha256': clip['original_mp4_sha256'],
            'review_category': category, 'reason': rationale,
            'missing_fields': missing, 'call_to_pot_ratio': exposure,
            'has_conditional_what_if': result is not None,
            'sampling_ci95_if_available': (result['equity_sampling_ci95']
                                           if result is not None else None),
            'visual_evidence_confidence': 'unverified',
            'range_confidence': 'unverified_user_hypothesis',
            'strategic_error_established': False,
            'auto_clip_selection_authorized': False,
            'ev_ranking_authorized': False,
        })
    # Stable chronological display, NOT ordering by EV or error severity.
    rows.sort(key=lambda row: (row['decision_timestamp'], row['table_id'],
                               row['hand_id'], row['event_index']))
    return {
        'schema_version': 1, 'analysis_status': STATUS,
        'recording_sha256': explanations['recording_sha256'],
        'source_explanations_sha256': digest(explanations),
        'source_clip_manifest_sha256': digest(manifest),
        'auto_clip_selection_authorized': False,
        'authorized_for_ev_based_ranking': False,
        'strategic_error_established': False,
        'sort_order': 'timestamp_only_not_mathematical_rank',
        'attention_threshold_call_to_pot': .25,
        'candidates': rows,
        'warning': ('This triage identifies manual review workload only. It does not '
                    'identify mistakes, select clips automatically, verify visual '
                    'observations, or infer real-hand EV. Sampling CI excludes range '
                    'uncertainty and video recognition error.'),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('clip_manifest_json', 'clips_dir', 'worksheet_json',
                 'request_json', 'hypothetical_report_json', 'output_json'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    inputs = [Path(p) for p in (args.clip_manifest_json, args.worksheet_json,
                                args.request_json, args.hypothetical_report_json)]
    clips_dir, output = Path(args.clips_dir), Path(args.output_json)
    if (any(not p.is_file() or p.is_symlink() for p in inputs)
            or not clips_dir.is_dir() or clips_dir.is_symlink()
            or output.exists() or output.is_symlink()
            or output.resolve() in {p.resolve() for p in inputs}):
        raise ValueError('Require regular inputs and a new output')
    values = [json.loads(p.read_text(encoding='utf-8')) for p in inputs]
    triage = build_review_triage(values[0], clips_dir, *values[1:])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as fp:
        json.dump(triage, fp, ensure_ascii=False, indent=2, allow_nan=False)
        fp.write('\n')
    print(json.dumps({'candidates': len(triage['candidates']),
                      'auto_selection_authorized': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
