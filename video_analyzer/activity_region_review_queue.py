"""Offline, review-only queue of temporal pixel changes in manually configured ROIs.

A queue item is NOT a poker event, hand boundary, card, action, or EV signal.
Source contact sheets and PNGs are re-audited before generating any hints.
"""
import argparse
import json
import math
from pathlib import Path

from activity_region_change_hints import build_region_change_hints
from activity_snapshot_chain import canonical_sha256

_LABELS = ('board', 'hero_cards', 'pot')


def _valid_float(value):
    return type(value) in (int, float) and math.isfinite(value)


def _group_candidates(region_report, merge_gap_seconds):
    """Group *consecutive* flagged comparisons within one window and ROI.

    A nonflagged comparison or missing frame breaks a run; time proximity
    alone never bridges an unobserved/unchanged pair or a different window.
    """
    candidates = []
    for window in region_report['windows']:
        active = {}
        for pair in window['pairs'] + [{'status': 'end_of_window'}]:
            flagged = {}
            if pair['status'] == 'unverified_region_pixel_change_hints':
                flagged = {r['region_label_hypothesis']: r
                           for r in pair['regions'] if r['above_fixed_pixel_threshold']}
            for label in list(active):
                item = active[label]
                continuous = (label in flagged and
                              pair['left_image'] == item['last_image'] and
                              pair['left_decoded_pts_seconds'] == item['end_pts_seconds'] and
                              pair['right_decoded_pts_seconds'] - item['end_pts_seconds']
                              <= merge_gap_seconds)
                if not continuous:
                    item.pop('last_image')
                    candidates.append(item)
                    del active[label]
            for label, region in flagged.items():
                diff = region['mean_absolute_luma_difference']
                if label in active:
                    item = active[label]
                    item['end_pts_seconds'] = pair['right_decoded_pts_seconds']
                    item['last_image'] = pair['right_image']
                    item['last_frame'] = pair['right_image']
                    item['comparison_count'] += 1
                    item['peak_luma_difference'] = max(item['peak_luma_difference'], diff)
                else:
                    active[label] = {
                        'table_id': window['table_id'],
                        'review_window_index': window['review_window_index'],
                        'region_label_hypothesis': label,
                        'start_pts_seconds': pair['left_decoded_pts_seconds'],
                        'end_pts_seconds': pair['right_decoded_pts_seconds'],
                        'first_frame': pair['left_image'],
                        'last_frame': pair['right_image'],
                        'last_image': pair['right_image'],
                        'comparison_count': 1,
                        'peak_luma_difference': diff,
                        'confidence_in_region_mapping': 'not_calibrated',
                        'confidence_in_poker_semantics': 'not_calibrated',
                        'requires_manual_review': True,
                    }
    return candidates


def build_region_review_queue(contact_report, packet_root, profile, *,
                              expected_report_sha256=None,
                              expected_profile_sha256=None,
                              pixel_threshold=0.12, merge_gap_seconds=2.0,
                              max_candidates=100):
    """Rank ROI changes by *pixel difference*, never strategic importance."""
    if (not _valid_float(merge_gap_seconds) or merge_gap_seconds <= 0
            or merge_gap_seconds > 60 or type(max_candidates) is not int
            or not 1 <= max_candidates <= 1000):
        raise ValueError('Invalid grouping or queue budget')
    regions = build_region_change_hints(
        contact_report, packet_root, profile,
        expected_report_sha256=expected_report_sha256,
        expected_profile_sha256=expected_profile_sha256,
        pixel_threshold=pixel_threshold)
    if (regions['analysis_status'] != 'unverified_manual_roi_pixel_change_hints'
            or regions['requires_manual_review'] is not True
            or any(regions.get(k) is not False for k in (
                'automatic_hand_boundaries_authorized',
                'automatic_clip_selection_authorized',
                'ready_for_equity_or_ev', 'strategic_error_established'))):
        raise ValueError('Unsafe source status')
    all_candidates = _group_candidates(regions, float(merge_gap_seconds))
    # Stable tie-breakers; the score is a visual artifact heuristic, not confidence.
    all_candidates.sort(key=lambda item: (
        -item['peak_luma_difference'], item['table_id'],
        item['review_window_index'], item['start_pts_seconds'],
        _LABELS.index(item['region_label_hypothesis'])))
    chosen = all_candidates[:max_candidates]
    for rank, item in enumerate(chosen, 1):
        item['pixel_review_rank'] = rank
    return {
        'schema_version': 1,
        'analysis_status': 'unverified_region_pixel_review_queue',
        'recording_sha256': regions['recording_sha256'],
        'source_region_change_hints_sha256': canonical_sha256(regions),
        'source_contact_sheet_sha256': regions['source_contact_sheet_sha256'],
        'source_region_profile_sha256': regions['source_region_profile_sha256'],
        'ranking_method': 'descending_peak_mean_absolute_luma_difference_only',
        'pixel_threshold': regions['fixed_pixel_threshold'],
        'merge_gap_seconds': float(merge_gap_seconds),
        'max_candidates': max_candidates,
        'total_candidate_intervals': len(all_candidates),
        'omitted_due_to_budget': len(all_candidates) - len(chosen),
        'candidates': chosen,
        'timestamp_semantics': 'decoded_source_pts_seconds_not_exact_hand_boundary',
        'requires_manual_review': True,
        'automatic_hand_boundaries_authorized': False,
        'automatic_clip_selection_authorized': False,
        'ready_for_equity_or_ev': False,
        'strategic_error_established': False,
        'warning': ('Ranking measures uncalibrated pixel differences only. '
                    'No cards, pot, actions, hand boundaries, or errors are established.'),
    }


def export_region_review_queue(packet_root, profile_json, output_json, **kwargs):
    root, profile_path, dest = map(Path, (packet_root, profile_json, output_json))
    report_path = root / 'report.json'
    if (root.is_symlink() or report_path.is_symlink() or
            not report_path.is_file() or profile_path.is_symlink() or
            not profile_path.is_file() or dest.is_symlink() or dest.exists()):
        raise ValueError('Require regular inputs and a new output path')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    profile = json.loads(profile_path.read_text(encoding='utf-8'))
    result = build_region_review_queue(report, root, profile, **kwargs)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('contact_sheet_directory')
    parser.add_argument('manual_roi_profile_json')
    parser.add_argument('output_json')
    parser.add_argument('--pixel-threshold', type=float, default=0.12)
    parser.add_argument('--merge-gap-seconds', type=float, default=2.0)
    parser.add_argument('--max-candidates', type=int, default=100)
    parser.add_argument('--expected-report-sha256')
    parser.add_argument('--expected-profile-sha256')
    args = parser.parse_args()
    result = export_region_review_queue(
        args.contact_sheet_directory, args.manual_roi_profile_json, args.output_json,
        pixel_threshold=args.pixel_threshold,
        merge_gap_seconds=args.merge_gap_seconds,
        max_candidates=args.max_candidates,
        expected_report_sha256=args.expected_report_sha256,
        expected_profile_sha256=args.expected_profile_sha256)
    print(json.dumps({'candidates': len(result['candidates']),
                      'status': result['analysis_status']}))
