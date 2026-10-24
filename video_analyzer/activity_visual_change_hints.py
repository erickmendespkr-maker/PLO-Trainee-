"""Review-only, pixel-level change hints for audited offline PLO contact sheets.

This deliberately does NOT detect cards, pot, actions, hand boundaries or errors.
A high difference can be an animation, cursor, overlay or compression artifact.
Only FFmpeg (already used by the video pipeline) and Python stdlib are needed.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

from activity_snapshot_chain import canonical_sha256

_IMAGE = re.compile(r'images/table_(0[1-4])/frame_\d{5}\.png\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_SIZE = 48  # 2304 luma bytes per image; coarse comparison, not OCR.


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _sha(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _luma(path, *, timeout=15):
    """Decode a single audited PNG into a bounded, coarse grayscale sample."""
    cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
           '-i', str(path), '-frames:v', '1',
           '-vf', f'scale={_SIZE}:{_SIZE}:flags=area,format=gray',
           '-f', 'rawvideo', '-pix_fmt', 'gray', 'pipe:1']
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ValueError('FFmpeg PNG decode unavailable') from exc
    if proc.returncode or len(proc.stdout) != _SIZE * _SIZE:
        raise ValueError('FFmpeg PNG decode failed or unexpected dimensions')
    return proc.stdout


def _difference(left, right):
    # All values are luma 0..255. Mean absolute difference is not probability.
    strips = []
    for start in (0, _SIZE // 3, 2 * _SIZE // 3):
        a, b = start * _SIZE, (start + _SIZE // 3) * _SIZE
        strips.append(round(sum(abs(x-y) for x, y in zip(left[a:b], right[a:b])) /
                            (255 * (b-a)), 6))
    return round(sum(abs(x-y) for x, y in zip(left, right)) /
                 (255 * len(left)), 6), strips


def build_visual_change_hints(report, packet_root, *, expected_report_sha256=None,
                              change_threshold=.12, max_images=600,
                              max_total_png_bytes=100_000_000):
    """Compare adjacent *decoded* frames within each unconfirmed review window.

    Re-audits every referenced PNG hash before invoking FFmpeg. Does not trust
    filenames outside the contact-sheet's fixed relative PNG layout. Refuses
    premature authorization, missing/changed images and invalid provenance.
    """
    if (type(change_threshold) not in (int, float) or not math.isfinite(change_threshold)
            or not 0 < change_threshold < 1
            or type(max_images) is not int or not 1 <= max_images <= 600
            or type(max_total_png_bytes) is not int
            or not 1 <= max_total_png_bytes <= 100_000_000):
        raise ValueError('Invalid visual change limits')
    if (not isinstance(report, dict) or report.get('schema_version') != 1
            or report.get('analysis_status') != 'offline_boundary_contact_sheet_review_only'
            or report.get('requires_manual_review') is not True
            or any(report.get(k) is not False for k in (
                'automatic_hand_boundaries_authorized',
                'automatic_clip_selection_authorized', 'ready_for_equity_or_ev',
                'strategic_error_established'))
            or report.get('timestamp_semantics') != 'requested_seeks_distinct_from_decoded_filtergraph_pts'
            or not isinstance(report.get('windows'), list)
            or len(report['windows']) > 10000
            or not isinstance(report.get('recording_sha256'), str)
            or not _SHA.fullmatch(report['recording_sha256'])
            or any(not isinstance(report.get(k), str) or not _SHA.fullmatch(report[k])
                   for k in ('source_seek_plan_sha256', 'source_evidence_manifest_sha256',
                             'source_boundary_review_sha256'))):
        raise ValueError('Invalid or prematurely authorized contact-sheet report')
    report_sha = canonical_sha256(report)
    if expected_report_sha256 is not None and expected_report_sha256 != report_sha:
        raise ValueError('Contact-sheet report SHA-256 mismatch')
    root = Path(packet_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Invalid contact-sheet directory')
    seen, samples, result, total = set(), {}, [], 0
    resolved = unresolved = 0
    for window in report['windows']:
        if (not isinstance(window, dict) or type(window.get('table_id')) is not int
                or not 1 <= window['table_id'] <= 4
                or type(window.get('review_window_index')) is not int
                or window['review_window_index'] < 0
                or window.get('requires_manual_review') is not True
                or window.get('exact_boundary_known') is not False
                or not isinstance(window.get('candidate_interval_pts'), list)
                or len(window['candidate_interval_pts']) != 2
                or not all(_finite(t) for t in window['candidate_interval_pts'])
                or window['candidate_interval_pts'][0] >= window['candidate_interval_pts'][1]
                or not isinstance(window.get('frames'), list)):
            raise ValueError('Invalid contact-sheet window')
        first, last = window['candidate_interval_pts']
        frames = []
        prev_seek = -1
        for frame in window['frames']:
            if (not isinstance(frame, dict)
                    or not _finite(frame.get('requested_seek_seconds'))
                    or not first < frame['requested_seek_seconds'] < last
                    or frame['requested_seek_seconds'] <= prev_seek):
                raise ValueError('Invalid or unordered requested seeks')
            prev_seek = frame['requested_seek_seconds']
            status = frame.get('status')
            if status == 'no_decoded_frame':
                if frame.get('image') is not None or frame.get('decoded_source_pts_seconds') is not None:
                    raise ValueError('Unresolved frame has decoded evidence')
                unresolved += 1
                frames.append(None)
                continue
            if status not in ('unverified_visual_evidence',
                              'decoded_outside_candidate_interval_review_required'):
                raise ValueError('Unexpected decoded frame status')
            image = frame.get('image')
            pts = frame.get('decoded_source_pts_seconds')
            if (not isinstance(image, str) or not _IMAGE.fullmatch(image)
                    or int(image.split('/')[1][-2:]) != window['table_id']
                    or not _finite(pts)
                    or not isinstance(frame.get('sha256'), str)
                    or not _SHA.fullmatch(frame['sha256'])
                    or (status == 'unverified_visual_evidence') != (first <= pts <= last)):
                raise ValueError('Inconsistent PNG identity, PTS or interval status')
            # A decoded PNG may appear in multiple requests; hash and path must agree.
            if image in seen:
                raise ValueError('Repeated PNG reference')
            seen.add(image)
            if len(seen) > max_images:
                raise ValueError('Image count exceeds budget')
            file = root / image
            if file.is_symlink() or not file.is_file():
                raise ValueError('Missing or unsafe PNG evidence')
            total += file.stat().st_size
            if total > max_total_png_bytes:
                raise ValueError('PNG byte budget exceeded')
            if _sha(file) != frame['sha256']:
                raise ValueError('PNG SHA-256 mismatch')
            samples[image] = _luma(file)
            resolved += 1
            frames.append(frame)
        pairs = []
        for left, right in zip(frames, frames[1:]):
            if left is None or right is None:
                pairs.append({'status': 'unresolved_frame_prevents_comparison'})
                continue
            if (left['status'] != 'unverified_visual_evidence'
                    or right['status'] != 'unverified_visual_evidence'):
                pairs.append({'status': 'outside_interval_prevents_comparison'})
                continue
            t1, t2 = left['decoded_source_pts_seconds'], right['decoded_source_pts_seconds']
            if t2 <= t1:
                pairs.append({'status': 'non_increasing_decoded_pts_prevents_comparison'})
                continue
            overall, strips = _difference(samples[left['image']], samples[right['image']])
            pairs.append({'status': 'unverified_pixel_change_hint',
                          'left_image': left['image'], 'right_image': right['image'],
                          'left_decoded_pts_seconds': t1, 'right_decoded_pts_seconds': t2,
                          'mean_absolute_luma_difference': overall,
                          'top_middle_bottom_luma_differences': strips,
                          'above_fixed_pixel_threshold': overall >= change_threshold,
                          'confidence_in_poker_semantics': 'not_calibrated'})
        result.append({'table_id': window['table_id'],
                       'review_window_index': window['review_window_index'],
                       'candidate_interval_pts': [first, last], 'pairs': pairs,
                       'requires_manual_review': True, 'exact_boundary_known': False})
    if (report.get('resolved_count') != resolved or report.get('unresolved_count') != unresolved
            or report.get('requested_count') != resolved + unresolved):
        raise ValueError('Contact-sheet count mismatch')
    return {'schema_version': 1, 'analysis_status': 'unverified_offline_pixel_change_hints',
            'recording_sha256': report['recording_sha256'],
            'source_contact_sheet_sha256': report_sha,
            'timestamp_semantics': 'decoded_source_pts_seconds_not_exact_hand_boundary',
            'fixed_pixel_threshold': float(change_threshold),
            'comparison_method': 'ffmpeg_48x48_area_gray_mean_absolute_luma_difference',
            'resolved_images': resolved, 'unresolved_images': unresolved,
            'windows': result, 'requires_manual_review': True,
            'automatic_hand_boundaries_authorized': False,
            'automatic_clip_selection_authorized': False,
            'ready_for_equity_or_ev': False, 'strategic_error_established': False,
            'warning': ('Pixel differences are not cards, board, pot, actions, '
                        'hand boundaries or mathematical evidence. Animations, cursors '
                        'and video compression can change pixels.')}


def export_visual_change_hints(packet_root, output_json, **kwargs):
    root, dest = Path(packet_root), Path(output_json)
    report_path = root / 'report.json'
    if (report_path.is_symlink() or not report_path.is_file()
            or dest.is_symlink() or dest.exists()):
        raise ValueError('Require a regular contact-sheet report and new output path')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    result = build_visual_change_hints(report, root, **kwargs)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('contact_sheet_directory')
    parser.add_argument('output_json')
    parser.add_argument('--expected-report-sha256')
    parser.add_argument('--change-threshold', type=float, default=.12)
    args = parser.parse_args()
    r = export_visual_change_hints(args.contact_sheet_directory, args.output_json,
                                   expected_report_sha256=args.expected_report_sha256,
                                   change_threshold=args.change_threshold)
    print(json.dumps({'windows': len(r['windows']), 'resolved_images': r['resolved_images']}))
