"""Offline, non-authoritative temporal review of audited table-crop OCR reports.

Consumes one or more Cycle 80 OCR JSON reports. Changes are *review hints*,
never hand boundaries, verified poker events, or equity/EV inputs. Tesseract
confidence is uncalibrated; this module never upgrades it to certainty.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from ocr_candidates import FIELDS, parse_visible_amount, parse_visible_cards


def _regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected a regular non-symlink report')
    return path


def _sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _number(x, *, minimum=0):
    return type(x) in (int, float) and math.isfinite(x) and x >= minimum


def _digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _candidate(row, recording, profile, source_sha, index):
    if not isinstance(row, dict):
        raise ValueError('OCR candidate must be an object')
    table, field = row.get('table_id'), row.get('field')
    if type(table) is not int or table not in (1, 2, 3, 4) or field not in FIELDS:
        raise ValueError('Invalid table or OCR field')
    pts = row.get('decoded_frame_pts_seconds')
    verified = row.get('decoded_pts_verified_by_identical_png')
    if type(verified) is not bool or (pts is not None and not _number(pts)):
        raise ValueError('Invalid decoded PTS or verification flag')
    if verified and pts is None:
        raise ValueError('Verified decoded PTS must be present')
    if not verified:
        # An unaudited seek timestamp must never be used as a temporal fact.
        pts = None
    requested = row.get('requested_seek_pts_seconds')
    if not _number(requested) or not _number(row.get('timestamp')) or row['timestamp'] != requested:
        raise ValueError('Invalid requested timestamp')
    confidence = row.get('mean_engine_confidence')
    if confidence is not None and not _number(confidence):
        raise ValueError('Invalid OCR confidence')
    raw = row.get('raw_text')
    if not isinstance(raw, str) or len(raw) > 4096:
        raise ValueError('Invalid OCR text')
    parsed = (parse_visible_cards(raw, field=field) if field in ('board', 'hero_cards')
              else parse_visible_amount(raw, field=field))
    if isinstance(parsed, float) and not math.isfinite(parsed):
        raise ValueError('Non-finite parsed OCR amount')
    if parsed != row.get('parsed_candidate'):
        raise ValueError('OCR parsed value inconsistent with raw text')
    roi = row.get('roi_coordinates_in_table_crop')
    if (not isinstance(roi, dict) or set(roi) != {'x', 'y', 'width', 'height'}
            or any(type(roi[k]) is not int for k in roi)
            or min(roi['x'], roi['y']) < 0 or min(roi['width'], roi['height']) < 1):
        raise ValueError('Invalid ROI coordinates')
    crop_sha = row.get('source_crop_sha256')
    roi_sha = row.get('roi_sha256')
    if not _digest(crop_sha) or not _digest(roi_sha):
        raise ValueError('Invalid crop provenance')
    if (row.get('status') not in ('candidate_unverified', 'needs_manual_review')
            or row.get('requires_manual_review') is not True
            or row.get('poker_event_verified') is not False):
        raise ValueError('OCR result must remain unverified')
    return {
        'table_id': table, 'field': field, 'decoded_pts_seconds': pts,
        'requested_seek_pts_seconds': requested, 'raw_text': raw,
        'parsed_candidate': parsed, 'mean_engine_confidence': confidence,
        'roi_coordinates_in_table_crop': roi,
        'source_crop_sha256': crop_sha, 'roi_sha256': roi_sha,
        'source_report_sha256': source_sha, 'source_candidate_index': index,
        'recording_sha256': recording, 'roi_profile_sha256': profile,
        'requires_manual_review': True, 'poker_event_verified': False,
    }


def build_temporal_ocr_review(reports, *, max_gap_seconds=30.0,
                              min_engine_confidence=0.75, max_candidates=1024):
    """Build review hints from audited OCR report dictionaries plus their SHA-256s.

    `reports` contains (report_dict, source_file_sha256) pairs. A verified PTS
    here only means the upstream extractor reproduced an identical PNG.
    """
    if not _number(max_gap_seconds, minimum=0.001) or not 0 < max_gap_seconds <= 600:
        raise ValueError('Invalid maximum gap')
    if not _number(min_engine_confidence) or min_engine_confidence > 1:
        raise ValueError('Invalid OCR threshold')
    if type(max_candidates) is not int or not 1 <= max_candidates <= 4096:
        raise ValueError('Invalid candidate budget')
    if not isinstance(reports, list) or not 1 <= len(reports) <= 64:
        raise ValueError('Expected 1..64 reports')
    recording, profile = None, None
    observations = []
    for report, source_sha in reports:
        if not isinstance(report, dict) or not _digest(source_sha):
            raise ValueError('Invalid report/provenance')
        if (type(report.get('schema_version')) is not int or report['schema_version'] != 1
                or report.get('analysis_status') != 'unverified_manual_roi_ocr_on_audited_navigation_crops'
                or report.get('ready_for_equity_or_ev') is not False
                or report.get('automatic_clip_selection_authorized') is not False
                or report.get('requires_manual_review') is not True):
            raise ValueError('Unsupported or falsely authoritative OCR report')
        rec, prof = report.get('recording_sha256'), report.get('source_roi_config_sha256')
        if not _digest(rec) or not _digest(prof):
            raise ValueError('Missing recording or ROI profile provenance')
        if recording is None:
            recording, profile = rec, prof
        if (rec, prof) != (recording, profile):
            raise ValueError('Cannot compare different recordings or ROI profiles')
        rows = report.get('candidates')
        if not isinstance(rows, list) or len(rows) + len(observations) > max_candidates:
            raise ValueError('OCR candidate budget exceeded')
        for i, row in enumerate(rows):
            observations.append(_candidate(row, recording, profile, source_sha, i))
    groups = defaultdict(list)
    for row in observations:
        key = (row['table_id'], row['field'], json.dumps(row['roi_coordinates_in_table_crop'], sort_keys=True))
        groups[key].append(row)
    items = []
    for (table, field, _), rows in sorted(groups.items()):
        # Keep unaudited observations in their requested-seek position so an
        # uncertain middle frame cannot be skipped to create a false change.
        rows.sort(key=lambda x: (x['requested_seek_pts_seconds'],
                                 x['source_report_sha256'], x['source_candidate_index']))
        previous = None
        timestamps = defaultdict(list)
        for row in rows:
            if row['decoded_pts_seconds'] is not None:
                timestamps[row['decoded_pts_seconds']].append(row)
        for row in rows:
            pts = row['decoded_pts_seconds']
            reason = None
            if pts is None:
                reason = 'decoded_pts_unverified'
            elif len(timestamps[pts]) > 1:
                reason = 'duplicate_decoded_pts_ambiguous'
            elif row['parsed_candidate'] is None or row['mean_engine_confidence'] is None or row['mean_engine_confidence'] < min_engine_confidence:
                reason = 'ocr_uncertain_or_unparsed'
            if reason:
                items.append({'table_id': table, 'field': field, 'kind': reason,
                              'at_decoded_pts_seconds': pts,
                              'source_report_sha256': row['source_report_sha256'],
                              'source_candidate_index': row['source_candidate_index'],
                              'requires_manual_review': True})
                previous = None
                continue
            if previous is not None:
                gap = pts - previous['decoded_pts_seconds']
                if gap <= 0:
                    items.append({'table_id': table, 'field': field,
                                  'kind': 'nonmonotonic_decoded_pts',
                                  'at_decoded_pts_seconds': pts,
                                  'requires_manual_review': True})
                    previous = None
                    continue
                if gap <= max_gap_seconds and row['parsed_candidate'] != previous['parsed_candidate']:
                    items.append({
                        'table_id': table, 'field': field, 'kind': 'possible_visual_value_change',
                        'from_decoded_pts_seconds': previous['decoded_pts_seconds'],
                        'at_decoded_pts_seconds': pts,
                        'from_candidate': previous['parsed_candidate'],
                        'to_candidate': row['parsed_candidate'],
                        'source_evidence': [
                            {'report_sha256': r['source_report_sha256'],
                             'candidate_index': r['source_candidate_index'],
                             'roi_sha256': r['roi_sha256']}
                            for r in (previous, row)],
                        'requires_manual_review': True,
                    })
                elif gap > max_gap_seconds:
                    items.append({'table_id': table, 'field': field,
                                  'kind': 'gap_exceeds_comparison_window',
                                  'from_decoded_pts_seconds': previous['decoded_pts_seconds'],
                                  'at_decoded_pts_seconds': pts, 'requires_manual_review': True})
            previous = row
    counts = {'observations': len(observations), 'review_items': len(items),
              'possible_changes': sum(i['kind'] == 'possible_visual_value_change' for i in items),
              'ambiguous_or_uncertain': sum(i['kind'] in (
                  'decoded_pts_unverified', 'duplicate_decoded_pts_ambiguous',
                  'ocr_uncertain_or_unparsed') for i in items)}
    return {'schema_version': 1, 'analysis_status': 'unverified_temporal_ocr_review_hints',
            'recording_sha256': recording, 'roi_profile_sha256': profile,
            'source_report_sha256s': [sha for _, sha in reports],
            'review_items': items, 'counts': counts,
            'requires_manual_review': True, 'hand_boundaries_verified': False,
            'cards_or_actions_verified': False, 'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
            'strategic_error_established': False,
            'warning': 'OCR/PTS comparisons are review hints only. Confidence is uncalibrated; no verified hand transitions or poker events.'}


def export_temporal_ocr_review(report_paths, output_json, *, max_gap_seconds=30.0,
                               min_engine_confidence=0.75, max_candidates=1024):
    paths = [_regular(p) for p in report_paths]
    if len({p.resolve() for p in paths}) != len(paths):
        raise ValueError('Duplicate report paths')
    output = Path(output_json)
    if output.exists() or output.is_symlink() or output.resolve() in {p.resolve() for p in paths}:
        raise ValueError('Output must be new')
    initial = [_sha(p) for p in paths]
    reports = [(json.loads(p.read_text(encoding='utf-8')), sha) for p, sha in zip(paths, initial)]
    result = build_temporal_ocr_review(reports, max_gap_seconds=max_gap_seconds,
        min_engine_confidence=min_engine_confidence, max_candidates=max_candidates)
    if any(_sha(p) != sha for p, sha in zip(paths, initial)):
        raise ValueError('Input changed during review')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output.parent,
                                     prefix='.plo_temporal_', suffix='.json', delete=False) as stream:
        stage = Path(stream.name)
        try:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        except BaseException:
            stage.unlink(missing_ok=True)
            raise
    try:
        # Exclusive creation prevents overwriting a concurrently created report.
        with output.open('xb') as dest, stage.open('rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                dest.write(block)
    finally:
        stage.unlink(missing_ok=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', nargs='+', help='Cycle 80 OCR JSON reports')
    parser.add_argument('--output', required=True)
    parser.add_argument('--max-gap-seconds', type=float, default=30)
    parser.add_argument('--min-engine-confidence', type=float, default=0.75)
    parser.add_argument('--max-candidates', type=int, default=1024)
    args = parser.parse_args(argv)
    result = export_temporal_ocr_review(args.reports, args.output,
        max_gap_seconds=args.max_gap_seconds, min_engine_confidence=args.min_engine_confidence,
        max_candidates=args.max_candidates)
    print(json.dumps(result['counts'], sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
