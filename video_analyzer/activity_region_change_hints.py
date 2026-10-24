"""Review-only pixel differences in manually configured regions of offline PLO frames.

No automatic ROI detection, card/action recognition, boundaries or EV authorization.
The profile is an *unverified hypothesis* about where board/hero/pot appear.
"""
import argparse
import json
import math
from pathlib import Path

from activity_snapshot_chain import canonical_sha256
from activity_visual_change_hints import _luma, _sha, build_visual_change_hints

_SIDE = 48
_NAMES = ('board', 'hero_cards', 'pot')


def _number(x):
    return type(x) in (int, float) and math.isfinite(x)


def _profile_regions(profile, recording_sha):
    if (not isinstance(profile, dict) or profile.get('schema_version') != 1
            or profile.get('profile_status') != 'manual_unverified_regions'
            or profile.get('calibration_verified') is not False
            or profile.get('recording_sha256') != recording_sha
            or not isinstance(profile.get('tables'), list)
            or not 1 <= len(profile['tables']) <= 4):
        raise ValueError('Invalid or prematurely calibrated ROI profile')
    tables = {}
    for table in profile['tables']:
        if (not isinstance(table, dict) or type(table.get('table_id')) is not int
                or not 1 <= table['table_id'] <= 4 or table['table_id'] in tables
                or not isinstance(table.get('regions'), dict)
                or not 1 <= len(table['regions']) <= 3
                or any(name not in _NAMES for name in table['regions'])):
            raise ValueError('Invalid table or region labels')
        regions = {}
        for name, rect in table['regions'].items():
            if (not isinstance(rect, list) or len(rect) != 4
                    or not all(_number(v) for v in rect)):
                raise ValueError('Invalid normalized ROI rectangle')
            x, y, width, height = rect
            if (x < 0 or y < 0 or width <= 0 or height <= 0
                    or x + width > 1 + 1e-12 or y + height > 1 + 1e-12):
                raise ValueError('ROI outside normalized image')
            x0, y0 = round(x * _SIDE), round(y * _SIDE)
            x1, y1 = round((x + width) * _SIDE), round((y + height) * _SIDE)
            if x1 - x0 < 4 or y1 - y0 < 4 or x1 > _SIDE or y1 > _SIDE:
                raise ValueError('ROI too small for 48x48 sample')
            regions[name] = (x0, y0, x1, y1)
        tables[table['table_id']] = regions
    return tables


def _roi_difference(left, right, bounds):
    x0, y0, x1, y1 = bounds
    total = 0
    for y in range(y0, y1):
        row = y * _SIDE
        for x in range(x0, x1):
            index = row + x
            total += abs(left[index] - right[index])
    return round(total / (255 * (x1 - x0) * (y1 - y0)), 6)


def build_region_change_hints(contact_report, packet_root, profile, *,
                              expected_report_sha256=None,
                              expected_profile_sha256=None,
                              pixel_threshold=0.12):
    """Audit the contact sheet, then compare only configured pixel rectangles.

    Never infer poker meaning from pixels. Source images are hashed before AND
    after decoding. A symlink at any expected directory level is rejected.
    """
    if not _number(pixel_threshold) or not 0 < pixel_threshold < 1:
        raise ValueError('Invalid fixed pixel threshold')
    if not isinstance(contact_report, dict) or not isinstance(profile, dict):
        raise ValueError('Expected contact-sheet report and ROI profile objects')
    report_hash = canonical_sha256(contact_report)
    profile_hash = canonical_sha256(profile)
    if expected_profile_sha256 is not None and expected_profile_sha256 != profile_hash:
        raise ValueError('ROI profile SHA-256 mismatch')
    regions = _profile_regions(profile, contact_report.get('recording_sha256'))
    root = Path(packet_root)
    for directory in (root, root / 'images'):
        if directory.is_symlink():
            raise ValueError('Unsafe contact-sheet directory symlink')
    for table_id in range(1, 5):
        if (root / 'images' / ('table_%02d' % table_id)).is_symlink():
            raise ValueError('Unsafe table directory symlink')
    # Reuse all upstream checks: counts, status gates, PTS, names, per-PNG hashes.
    base = build_visual_change_hints(contact_report, root,
                                    expected_report_sha256=expected_report_sha256)
    sample_cache = {}
    expected_hashes = {}
    for window in contact_report['windows']:
        for frame in window['frames']:
            if frame['status'] == 'no_decoded_frame':
                continue
            image = frame['image']
            table_dir = root / 'images' / ('table_%02d' % window['table_id'])
            if table_dir.is_symlink():
                raise ValueError('Unsafe table directory symlink')
            expected_hashes[image] = frame['sha256']
    output_windows = []
    for window in base['windows']:
        table_id = window['table_id']
        roi_map = regions.get(table_id)
        pairs = []
        for pair in window['pairs']:
            if pair['status'] != 'unverified_pixel_change_hint':
                pairs.append({'status': pair['status'], 'regions': []})
                continue
            if not roi_map:
                pairs.append({'status': 'unconfigured_regions_requires_manual_review',
                              'regions': []})
                continue
            left_image, right_image = pair['left_image'], pair['right_image']
            for image in (left_image, right_image):
                if image not in sample_cache:
                    path = root / image
                    if _sha(path) != expected_hashes[image]:
                        raise ValueError('PNG changed before region decoding')
                    decoded = _luma(path)
                    if _sha(path) != expected_hashes[image]:
                        raise ValueError('PNG changed during region decoding')
                    sample_cache[image] = decoded
            comparisons = []
            for name in _NAMES:
                if name not in roi_map:
                    continue
                diff = _roi_difference(sample_cache[left_image],
                                       sample_cache[right_image], roi_map[name])
                comparisons.append({'region_label_hypothesis': name,
                                    'mean_absolute_luma_difference': diff,
                                    'above_fixed_pixel_threshold': diff >= pixel_threshold,
                                    'confidence_in_region_mapping': 'not_calibrated',
                                    'confidence_in_poker_semantics': 'not_calibrated'})
            pairs.append({'status': 'unverified_region_pixel_change_hints',
                          'left_image': left_image, 'right_image': right_image,
                          'left_decoded_pts_seconds': pair['left_decoded_pts_seconds'],
                          'right_decoded_pts_seconds': pair['right_decoded_pts_seconds'],
                          'regions': comparisons})
        output_windows.append({'table_id': table_id,
                               'review_window_index': window['review_window_index'],
                               'candidate_interval_pts': window['candidate_interval_pts'],
                               'pairs': pairs, 'requires_manual_review': True,
                               'exact_boundary_known': False})
    return {'schema_version': 1,
            'analysis_status': 'unverified_manual_roi_pixel_change_hints',
            'recording_sha256': contact_report['recording_sha256'],
            'source_contact_sheet_sha256': report_hash,
            'source_pixel_change_hints_sha256': canonical_sha256(base),
            'source_region_profile_sha256': profile_hash,
            'fixed_pixel_threshold': float(pixel_threshold),
            'comparison_method': 'ffmpeg_48x48_area_gray_manual_normalized_roi_mad',
            'timestamp_semantics': 'decoded_source_pts_seconds_not_exact_hand_boundary',
            'windows': output_windows, 'requires_manual_review': True,
            'automatic_hand_boundaries_authorized': False,
            'automatic_clip_selection_authorized': False,
            'ready_for_equity_or_ev': False,
            'strategic_error_established': False,
            'warning': 'Regions are uncalibrated manual guesses. Pixel differences do not establish cards, actions, pot values, hand boundaries or errors.'}


def export_region_change_hints(packet_root, profile_json, output_json, **kwargs):
    root, profile_path, dest = map(Path, (packet_root, profile_json, output_json))
    report_path = root / 'report.json'
    if (report_path.is_symlink() or not report_path.is_file()
            or profile_path.is_symlink() or not profile_path.is_file()
            or dest.is_symlink() or dest.exists()):
        raise ValueError('Require regular input files and a new output path')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    profile = json.loads(profile_path.read_text(encoding='utf-8'))
    result = build_region_change_hints(report, root, profile, **kwargs)
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
    parser.add_argument('--expected-report-sha256')
    parser.add_argument('--expected-profile-sha256')
    parser.add_argument('--pixel-threshold', type=float, default=0.12)
    args = parser.parse_args()
    result = export_region_change_hints(
        args.contact_sheet_directory, args.manual_roi_profile_json, args.output_json,
        expected_report_sha256=args.expected_report_sha256,
        expected_profile_sha256=args.expected_profile_sha256,
        pixel_threshold=args.pixel_threshold)
    print(json.dumps({'windows': len(result['windows']), 'status': result['analysis_status']}))
