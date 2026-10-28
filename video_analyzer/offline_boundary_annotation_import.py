"""Import offline timeline boundary edits into a *draft-only* hand-boundaries document.

Usage: python offline_boundary_annotation_import.py HAND_DRAFTS_JSON ANNOTATIONS_JSON REVIEWED_OCR_JSON NEW_OUTPUT_DIR

The output `revised_boundaries.json` can be passed to offline_reviewed_hand_drafts.py
with the same reviewed OCR report. Neither this import nor rebuilding drafts validates
poker hands or permits equity/EV. SHA-256 binds bytes, not reviewer identity.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

HEX = re.compile(r'[0-9a-f]{64}\Z')
IDENT = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
STATES = {'pending', 'confirmed', 'corrected', 'inconclusive'}
MAX_BYTES = 8 * 1024 * 1024


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def pairs_unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def load(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= MAX_BYTES,
            'Unsafe JSON input')
    return json.loads(path.read_text('utf-8'), object_pairs_hook=pairs_unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def valid_time(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 86400


def valid_note(value, *, mandatory=False):
    return (type(value) is str and len(value) <= 500
            and (not mandatory or bool(value.strip()))
            and all(ord(ch) >= 32 or ch in '\n\t' for ch in value))


def transform(drafts, annotations, drafts_sha, reviewed_sha):
    require(type(drafts) is dict and type(drafts.get('schema_version')) is int
            and drafts['schema_version'] == 1
            and drafts.get('analysis_status') == 'offline_reviewed_hand_drafts_only'
            and drafts.get('ready_for_equity_or_ev') is False
            and drafts.get('hands_reconstructed') is False
            and drafts.get('source_reviewed_report_sha256') == reviewed_sha
            and type(drafts.get('source_roi_ocr_report_sha256')) is str
            and HEX.fullmatch(drafts['source_roi_ocr_report_sha256']) is not None
            and type(drafts.get('hands')) is list and 1 <= len(drafts['hands']) <= 200,
            'Invalid source draft provenance')
    require(type(annotations) is dict and set(annotations) == {
                'schema_version', 'source_hand_drafts_sha256', 'review_kind',
                'ready_for_equity_or_ev', 'annotations'}
            and type(annotations['schema_version']) is int and annotations['schema_version'] == 1
            and annotations['source_hand_drafts_sha256'] == drafts_sha
            and annotations['review_kind'] == 'manual_boundaries_only'
            and annotations['ready_for_equity_or_ev'] is False
            and type(annotations['annotations']) is list
            and len(annotations['annotations']) == len(drafts['hands']),
            'Invalid annotations provenance')
    original = {}
    for hand in drafts['hands']:
        require(type(hand) is dict and type(hand.get('hand_id')) is str
                and IDENT.fullmatch(hand['hand_id']) is not None
                and hand['hand_id'] not in original
                and type(hand.get('table_id')) is int and 1 <= hand['table_id'] <= 4
                and hand.get('variant') in ('PLO5', 'PLO6')
                and hand.get('boundary_origin') == 'manual_unverified'
                and hand.get('ready_for_equity_or_ev') is False
                and valid_time(hand.get('start_seconds'))
                and valid_time(hand.get('end_seconds'))
                and hand['start_seconds'] < hand['end_seconds']
                and valid_note(hand.get('boundary_note'), mandatory=True),
                'Invalid original hand')
        original[hand['hand_id']] = hand
    revised, audit, seen, tables = [], [], set(), {i: [] for i in range(1, 5)}
    for entry in annotations['annotations']:
        require(type(entry) is dict and set(entry) == {
                    'hand_id', 'table_id', 'review_status', 'start_seconds', 'end_seconds', 'note'},
                'Invalid annotation fields')
        hid = entry['hand_id']
        require(type(hid) is str and hid in original and hid not in seen,
                'Unknown or duplicate hand identity')
        seen.add(hid)
        hand = original[hid]
        require(type(entry['table_id']) is int and entry['table_id'] == hand['table_id']
                and entry['review_status'] in STATES
                and valid_time(entry['start_seconds']) and valid_time(entry['end_seconds'])
                and entry['start_seconds'] < entry['end_seconds']
                and valid_note(entry['note']), 'Invalid boundary annotation')
        changed = (entry['start_seconds'] != hand['start_seconds']
                   or entry['end_seconds'] != hand['end_seconds'])
        state = entry['review_status']
        require((state == 'corrected' and changed and bool(entry['note'].strip()))
                or (state != 'corrected' and not changed),
                'Boundary changes require corrected status and explanation')
        note = entry['note'] if state == 'corrected' else hand['boundary_note']
        revised.append({'hand_id': hid, 'table_id': hand['table_id'],
                        'variant': hand['variant'], 'start_seconds': entry['start_seconds'],
                        'end_seconds': entry['end_seconds'], 'note': note})
        audit.append({'hand_id': hid, 'table_id': hand['table_id'], 'review_status': state,
                      'changed': changed, 'review_note': entry['note'],
                      'source_start_seconds': hand['start_seconds'],
                      'source_end_seconds': hand['end_seconds'],
                      'revised_start_seconds': entry['start_seconds'],
                      'revised_end_seconds': entry['end_seconds']})
        tables[hand['table_id']].append((entry['start_seconds'], entry['end_seconds']))
    require(seen == set(original), 'Missing hand annotation')
    for intervals in tables.values():
        intervals.sort()
        require(all(left[1] <= right[0] for left, right in zip(intervals, intervals[1:])),
                'Overlapping revised boundaries on one table')
    revised.sort(key=lambda x: (x['table_id'], x['start_seconds'], x['hand_id']))
    audit.sort(key=lambda x: (x['table_id'], x['source_start_seconds'], x['hand_id']))
    boundaries = {'schema_version': 1, 'reviewed_report_sha256': reviewed_sha,
                  'hands': revised}
    review = {'schema_version': 1, 'analysis_status': 'offline_boundary_review_import_only',
              'source_hand_drafts_sha256': drafts_sha,
              'source_reviewed_report_sha256': reviewed_sha,
              'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
              'reviewed_boundaries_are_poker_verified': False,
              'annotations': audit,
              'warning': 'Review labels are user assertions, not proof of hand accuracy or EV.'}
    return boundaries, review


def build(drafts_path, annotations_path, reviewed_path, output_dir):
    drafts_path, annotations_path, reviewed_path, output_dir = map(
        Path, (drafts_path, annotations_path, reviewed_path, output_dir))
    require(output_dir.parent.is_dir() and not output_dir.parent.is_symlink()
            and not output_dir.exists() and not output_dir.is_symlink()
            and IDENT.fullmatch(output_dir.name) is not None,
            'Output directory must be new and safe')
    paths = (drafts_path, annotations_path, reviewed_path)
    hashes = [sha256(p) for p in paths]
    drafts, annotations, reviewed = [load(p) for p in paths]
    require(type(reviewed) is dict and reviewed.get('schema_version') == 1
            and reviewed.get('analysis_status') == 'offline_human_reviewed_ocr_observations_only'
            and reviewed.get('ready_for_equity_or_ev') is False
            and reviewed.get('hands_reconstructed') is False
            and reviewed.get('source_roi_ocr_report_sha256') == drafts.get('source_roi_ocr_report_sha256'),
            'Reviewed OCR source mismatch')
    boundaries, audit = transform(drafts, annotations, hashes[0], hashes[2])
    audit['source_annotations_sha256'] = hashes[1]
    with tempfile.TemporaryDirectory(prefix='.plo_boundary_import_', dir=output_dir.parent) as temp:
        stage = Path(temp)
        for name, obj in [('revised_boundaries.json', boundaries), ('boundary_review_audit.json', audit)]:
            (stage / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2,
                                                allow_nan=False) + '\n', 'utf-8')
        require([sha256(p) for p in paths] == hashes, 'Source changed during import')
        require(not output_dir.exists(), 'Output appeared during import')
        os.rename(stage, output_dir)
    return boundaries, audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('hand_drafts_json', 'annotations_json', 'reviewed_ocr_json', 'new_output_dir'):
        parser.add_argument(arg)
    a = parser.parse_args(argv)
    boundaries, audit = build(a.hand_drafts_json, a.annotations_json,
                              a.reviewed_ocr_json, a.new_output_dir)
    print(json.dumps({'hands': len(boundaries['hands']),
                      'corrected': sum(x['changed'] for x in audit['annotations']),
                      'ready_for_equity_or_ev': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
