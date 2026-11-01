"""Offline diagnostic queue: attach unreviewed OCR to human hand windows.

No automatic poker reconstruction, equity, EV or clip selection.
OCR timestamps are source PTS; hand windows are playback seconds. The caller
must provide the PTS origin explicitly; it is not authenticated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

MAX_JSON = 4 * 1024 * 1024
FIELDS = {'hero_cards', 'board', 'pot', 'bet', 'stack', 'action'}


def check(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        check(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def load(path):
    path = Path(path)
    check(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= MAX_JSON,
          'invalid JSON input')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_pairs,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def verify_image(bundle, relative, expected, folder):
    check(type(relative) is str and relative.startswith(folder + '/') and
          relative.endswith('.png') and '\\' not in relative and
          all(part not in ('', '.', '..') for part in relative.split('/')) and
          len(relative.split('/')) == 2, 'unsafe image path')
    check(type(expected) is str and len(expected) == 64 and
          all(c in '0123456789abcdef' for c in expected), 'invalid image SHA-256')
    path = bundle / relative
    check(path.is_file() and not path.is_symlink() and
          path.resolve().is_relative_to(bundle.resolve()) and digest(path) == expected,
          'crop hash mismatch' if folder == 'tables' else 'image hash mismatch')


def verify_crop(bundle, relative, expected):
    verify_image(bundle, relative, expected, 'tables')


def build(video, bundle, proposals, boundaries, *, source_pts_origin):
    check(number(source_pts_origin) and abs(source_pts_origin) <= 86400,
          'invalid source PTS origin')
    video, bundle, proposals, boundaries = map(Path, (video, bundle, proposals, boundaries))
    source_path = bundle / 'region_samples.json'
    inputs = (video, source_path, proposals, boundaries)
    check(bundle.is_dir() and not bundle.is_symlink() and
          len({str(p.resolve()) for p in inputs}) == 4 and
          all(p.is_file() and not p.is_symlink() for p in inputs), 'unsafe input files')
    original_hashes = {str(p.resolve()): digest(p) for p in inputs}
    video_sha = original_hashes[str(video.resolve())]
    source_sha = original_hashes[str(source_path.resolve())]
    source, ocr, hands = load(source_path), load(proposals), load(boundaries)
    check(type(source) is dict and source.get('analysis_status') ==
          'unverified_four_table_region_samples_for_manual_review_only' and
          source.get('recording_sha256') == video_sha and
          source.get('ready_for_equity_or_ev') is False and
          source.get('automatic_clip_selection_authorized') is False and
          type(source.get('samples')) is list and 1 <= len(source['samples']) <= 8 and
          type(source.get('regions')) is list and 1 <= len(source['regions']) <= 4,
          'invalid source evidence')
    check(type(ocr) is dict and ocr.get('analysis_status') ==
          'unverified_four_table_ocr_proposals_only' and
          ocr.get('recording_sha256') == video_sha and
          ocr.get('source_region_samples_sha256') == source_sha and
          ocr.get('requires_manual_review') is True and
          ocr.get('ready_for_equity_or_ev') is False and
          ocr.get('automatic_hand_or_action_inference') is False and
          type(ocr.get('candidates')) is list and len(ocr['candidates']) <= 32,
          'invalid unreviewed OCR report')
    check(type(hands) is dict and set(hands) ==
          {'schema_version', 'status', 'recording_sha256', 'hands'} and
          hands['schema_version'] == 1 and type(hands['schema_version']) is int and
          hands['status'] == 'human_annotated_hand_boundaries' and
          hands['recording_sha256'] == video_sha and
          type(hands['hands']) is list and 1 <= len(hands['hands']) <= 512,
          'invalid hand boundaries')
    regions = source['regions']
    tables = set()
    for region in regions:
        check(type(region) is dict and type(region.get('table_id')) is int and
              1 <= region['table_id'] <= 4 and region['table_id'] not in tables,
              'invalid table identity')
        tables.add(region['table_id'])
    sample_crops = {}
    seen_image_paths = set()
    last_pts = -math.inf
    for i, sample in enumerate(source['samples']):
        check(type(sample) is dict and number(sample.get('decoded_source_pts_seconds')) and
              type(sample.get('table_crops')) is list, 'invalid sample timestamp')
        pts = sample['decoded_source_pts_seconds']
        check(pts > last_pts, 'non-increasing source PTS')
        last_pts = pts
        frame_path = sample.get('frame_path')
        check(frame_path not in seen_image_paths, 'duplicate source frame')
        verify_image(bundle, frame_path, sample.get('frame_sha256'), 'frames')
        seen_image_paths.add(frame_path)
        for crop in sample['table_crops']:
            check(type(crop) is dict and type(crop.get('table_id')) is int and
                  crop['table_id'] in tables and type(crop.get('sha256')) is str and
                  len(crop['sha256']) == 64 and
                  (i, crop['table_id']) not in sample_crops,
                  'invalid source crop')
            check(crop.get('path') not in seen_image_paths, 'duplicate crop path')
            verify_crop(bundle, crop.get('path'), crop['sha256'])
            seen_image_paths.add(crop['path'])
            sample_crops[(i, crop['table_id'])] = crop
        check({c['table_id'] for c in sample['table_crops']} == tables,
              'incomplete sample crops')
    by_table = {table: [] for table in tables}
    records = []
    for index, hand in enumerate(hands['hands']):
        check(type(hand) is dict and set(hand) ==
              {'table_id', 'start_seconds', 'end_seconds'} and
              type(hand['table_id']) is int and hand['table_id'] in tables and
              number(hand['start_seconds']) and number(hand['end_seconds']) and
              0 <= hand['start_seconds'] < hand['end_seconds'],
              'invalid hand interval')
        by_table[hand['table_id']].append((hand['start_seconds'], hand['end_seconds']))
        records.append({'hand_index': index, 'table_id': hand['table_id'],
                        'start_seconds': hand['start_seconds'],
                        'end_seconds': hand['end_seconds'], 'observations': []})
    for intervals in by_table.values():
        intervals.sort()
        check(all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:])),
              'overlapping hands on same table')
    unassigned = []
    seen = set()
    for index, candidate in enumerate(ocr['candidates']):
        check(type(candidate) is dict and
              type(candidate.get('table_id')) is int and candidate['table_id'] in tables and
              type(candidate.get('sample_index')) is int and
              0 <= candidate['sample_index'] < len(source['samples']) and
              candidate.get('field') in FIELDS and
              candidate.get('status') == 'needs_manual_review' and
              candidate.get('parsed_candidate') is None and
              type(candidate.get('raw_ocr_text')) is str and
              len(candidate['raw_ocr_text']) <= 4096,
              'invalid or promoted OCR candidate')
        key = (candidate['sample_index'], candidate['table_id'], candidate['field'])
        check(key not in seen, 'duplicate OCR observation')
        seen.add(key)
        crop = sample_crops[(candidate['sample_index'], candidate['table_id'])]
        roi = candidate.get('roi')
        check(type(roi) is dict and set(roi) == {'x', 'y', 'width', 'height'} and
              all(type(v) is int for v in roi.values()) and
              min(roi['x'], roi['y']) >= 0 and
              8 <= roi['width'] <= 2048 and 8 <= roi['height'] <= 2048 and
              type(crop.get('width')) is int and type(crop.get('height')) is int and
              roi['x'] + roi['width'] <= crop['width'] and
              roi['y'] + roi['height'] <= crop['height'],
              'OCR ROI outside source crop')
        check(candidate.get('source_crop_path') == crop['path'] and
              candidate.get('source_crop_sha256') == crop['sha256'],
              'OCR candidate not bound to crop')
        pts = source['samples'][candidate['sample_index']]['decoded_source_pts_seconds']
        check(number(candidate.get('decoded_source_pts_seconds')) and
              abs(candidate['decoded_source_pts_seconds'] - pts) <= 1e-6,
              'OCR timestamp not bound to sample')
        playback = pts - source_pts_origin
        matches = [r for r in records if r['table_id'] == candidate['table_id'] and
                   r['start_seconds'] <= playback < r['end_seconds']]
        check(len(matches) <= 1, 'ambiguous hand association')
        observation = {'candidate_index': index, 'field': candidate['field'],
                       'decoded_source_pts_seconds': pts,
                       'playback_seconds_using_declared_origin': playback,
                       'raw_ocr_text': candidate['raw_ocr_text'],
                       'status': 'needs_manual_review',
                       'source_crop_sha256': crop['sha256']}
        if matches:
            matches[0]['observations'].append(observation)
        else:
            unassigned.append({'candidate_index': index, 'table_id': candidate['table_id'],
                               'reason': 'outside_human_annotated_hand_window',
                               'playback_seconds_using_declared_origin': playback})
    for sample in source['samples']:
        verify_image(bundle, sample['frame_path'], sample['frame_sha256'], 'frames')
        for crop in sample['table_crops']:
            verify_crop(bundle, crop['path'], crop['sha256'])
    check(all(digest(Path(p)) == sha for p, sha in original_hashes.items()),
          'input changed during review queue build')
    return {'schema_version': 1, 'status': 'offline_unreviewed_hand_ocr_review_queue_only',
            'recording_sha256_verified_against_bytes': video_sha,
            'region_samples_sha256': source_sha,
            'ocr_report_sha256': original_hashes[str(proposals.resolve())],
            'human_boundaries_sha256': original_hashes[str(boundaries.resolve())],
            'source_pts_origin_seconds_supplied_unverified': source_pts_origin,
            'timestamp_conversion': 'playback_seconds = decoded_source_pts_seconds - supplied_origin',
            'hands': records, 'unassigned_observations': unassigned,
            'observations_assigned': sum(len(r['observations']) for r in records),
            'observations_unassigned': len(unassigned),
            'human_annotations_authenticated': False, 'ocr_fields_verified': False,
            'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
            'warning': 'PTS origin and hand boundaries supplied; OCR is unreviewed. No poker facts or equity/EV.'}


def run(video, bundle, proposals, boundaries, output, *, source_pts_origin):
    output = Path(output)
    check(output.parent.is_dir() and not output.parent.is_symlink() and
          not output.exists() and not output.is_symlink() and
          all(not output.resolve().is_relative_to(Path(p).resolve()) for p in
              (video, bundle, proposals, boundaries)), 'output must be new and disjoint')
    result = build(video, bundle, proposals, boundaries,
                   source_pts_origin=source_pts_origin)
    with tempfile.TemporaryDirectory(prefix='.plo_review_queue_', dir=output.parent) as tmp:
        stage = Path(tmp) / 'review_queue.json'
        stage.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                    allow_nan=False) + '\n', encoding='utf-8')
        os.link(stage, output)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording')
    parser.add_argument('region_bundle')
    parser.add_argument('ocr_proposals')
    parser.add_argument('human_boundaries')
    parser.add_argument('new_output_json')
    parser.add_argument('--source-pts-origin', required=True, type=float)
    args = parser.parse_args(argv)
    result = run(args.recording, args.region_bundle, args.ocr_proposals,
                 args.human_boundaries, args.new_output_json,
                 source_pts_origin=args.source_pts_origin)
    print(json.dumps({'status': result['status'],
                      'observations_assigned': result['observations_assigned'],
                      'observations_unassigned': result['observations_unassigned']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
