"""Offline, explicit human review of SHA-bound OCR proposals (never equity/EV input).

python offline_roi_human_review.py OCR_OUTPUT_DIR ANNOTATIONS_JSON NEW_OUTPUT_DIR

Annotations v1: {"schema_version":1,"source_roi_ocr_report_sha256":"<sha256>",
"reviews":[{"proposal_index":0,"source_roi_png_sha256":"<sha256>",
"decision":"confirmed|corrected|rejected|inconclusive",
"normalized_value":"125.00" or null,"note":"human explanation"}]}

Only an explicit human review can add a normalized value. Even reviewed values
are observations, not reconstructed hands or authorization to compute equity/EV.
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
PNG = re.compile(r'roi_\d{3}\.png\Z')
CARD = re.compile(r'(?:[2-9TJQKA][cdhs])\Z')
AMOUNT = re.compile(r'(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?\Z')
FIELDS = {'hero_cards', 'board', 'pot', 'bet', 'stack', 'action'}
DECISIONS = {'confirmed', 'corrected', 'rejected', 'inconclusive'}
ACTIONS = {'fold', 'check', 'call', 'bet', 'raise', 'all-in'}
MAX_JSON = 4 * 1024 * 1024
MAX_PNG = 12 * 1024 * 1024


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'Duplicate JSON key')
        out[key] = value
    return out


def load(path, limit=MAX_JSON):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= limit,
            'Missing, unsafe or oversized JSON')
    try:
        return json.loads(path.read_text('utf-8'), object_pairs_hook=unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Malformed JSON') from exc


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def hexsha(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def normalize(field, value):
    require(type(value) is str and 0 < len(value) <= 128 and value == value.strip(),
            'Invalid human normalized value')
    if field in {'pot', 'bet', 'stack'}:
        require(AMOUNT.fullmatch(value) is not None, 'Invalid numeric chip amount')
    elif field == 'action':
        require(value in ACTIONS, 'Unknown action')
    else:
        cards = value.split(' ')
        require(all(CARD.fullmatch(card) for card in cards) and len(set(cards)) == len(cards),
                'Invalid or repeated card')
        require((len(cards) in (5, 6)) if field == 'hero_cards' else (1 <= len(cards) <= 5),
                'Invalid card count')
    return value


def validate_source(directory):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), 'Unsafe OCR directory')
    report_path = directory / 'roi_ocr_proposals.json'
    report = load(report_path)
    require(type(report) is dict and report.get('schema_version') == 1 and
            report.get('analysis_status') == 'offline_refined_roi_ocr_proposals_only' and
            report.get('requires_manual_review') is True and
            report.get('ready_for_equity_or_ev') is False and
            report.get('hands_reconstructed') is False and
            type(report.get('proposals')) is list and
            1 <= len(report['proposals']) <= 64, 'Invalid OCR report status')
    for index, proposal in enumerate(report['proposals']):
        require(type(proposal) is dict and proposal.get('status') == 'needs_manual_review' and
                proposal.get('parsed_candidate') is None and
                type(proposal.get('table_id')) is int and 1 <= proposal['table_id'] <= 4 and
                proposal.get('field') in FIELDS and
                type(proposal.get('raw_ocr_text')) is str and
                len(proposal['raw_ocr_text']) <= 512 and
                type(proposal.get('decoded_source_pts_seconds')) in (int, float) and
                math.isfinite(proposal['decoded_source_pts_seconds']) and
                proposal['decoded_source_pts_seconds'] >= 0 and
                hexsha(proposal.get('source_frame_sha256')) and
                hexsha(proposal.get('roi_png_sha256')) and
                proposal.get('roi_png') == f'roi_{index:03d}.png' and
                PNG.fullmatch(proposal['roi_png']) is not None, 'Invalid OCR proposal identity')
        png = directory / proposal['roi_png']
        require(png.is_file() and not png.is_symlink() and
                8 <= png.stat().st_size <= MAX_PNG and
                sha(png) == proposal['roi_png_sha256'], 'OCR evidence missing or modified')
        with png.open('rb') as source:
            require(source.read(8) == b'\x89PNG\r\n\x1a\n', 'Invalid PNG evidence')
    return report, sha(report_path)


def review(ocr_dir, annotations_json, output_dir):
    ocr_dir, annotations_json, output_dir = map(Path, (ocr_dir, annotations_json, output_dir))
    require(output_dir.parent.is_dir() and not output_dir.parent.is_symlink() and
            not output_dir.exists() and not output_dir.is_symlink() and
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', output_dir.name),
            'Output directory must be new and safe')
    require(not output_dir.resolve().is_relative_to(ocr_dir.resolve()),
            'Output cannot be inside OCR evidence')
    report, report_sha = validate_source(ocr_dir)
    annotations = load(annotations_json, 128 * 1024)
    require(type(annotations) is dict and set(annotations) ==
            {'schema_version', 'source_roi_ocr_report_sha256', 'reviews'} and
            type(annotations['schema_version']) is int and annotations['schema_version'] == 1 and
            annotations['source_roi_ocr_report_sha256'] == report_sha and
            type(annotations['reviews']) is list and
            len(annotations['reviews']) <= len(report['proposals']),
            'Invalid annotations provenance')
    annotations_sha = sha(annotations_json)
    reviewed, seen = {}, set()
    for entry in annotations['reviews']:
        require(type(entry) is dict and set(entry) ==
                {'proposal_index', 'source_roi_png_sha256', 'decision', 'normalized_value', 'note'},
                'Invalid review fields')
        index = entry['proposal_index']
        require(type(index) is int and 0 <= index < len(report['proposals']) and
                index not in seen, 'Invalid or duplicate proposal index')
        seen.add(index)
        proposal = report['proposals'][index]
        require(entry['source_roi_png_sha256'] == proposal['roi_png_sha256'],
                'Review evidence hash mismatch')
        decision, value, note = entry['decision'], entry['normalized_value'], entry['note']
        require(type(decision) is str and decision in DECISIONS and
                type(note) is str and len(note) <= 1000 and
                all(ord(ch) >= 32 or ch in '\n\t' for ch in note), 'Invalid decision or note')
        if decision in {'confirmed', 'corrected'}:
            value = normalize(proposal['field'], value)
            require(decision != 'confirmed' or bool(proposal['raw_ocr_text'].strip()),
                    'Cannot confirm blank OCR')
            require(decision != 'corrected' or bool(note.strip()),
                    'Correction requires explanation')
        else:
            require(value is None, 'Unresolved review cannot contain normalized value')
        reviewed[index] = {'decision': decision, 'normalized_value': value, 'note': note}
    observations = []
    for index, proposal in enumerate(report['proposals']):
        decision = reviewed.get(index, {'decision': 'pending', 'normalized_value': None, 'note': ''})
        observations.append({'proposal_index': index, 'table_id': proposal['table_id'],
                             'frame_file': proposal['frame_file'],
                             'decoded_source_pts_seconds': proposal['decoded_source_pts_seconds'],
                             'source_frame_sha256': proposal['source_frame_sha256'],
                             'roi_png': proposal['roi_png'],
                             'roi_png_sha256': proposal['roi_png_sha256'],
                             'field': proposal['field'], 'raw_ocr_text': proposal['raw_ocr_text'],
                             **decision, 'confidence': 'human_review_not_calibrated_accuracy'})
    result = {'schema_version': 1,
              'analysis_status': 'offline_human_reviewed_ocr_observations_only',
              'source_roi_ocr_report_sha256': report_sha,
              'source_annotations_sha256': annotations_sha,
              'source_sha256': report.get('source_sha256'),
              'ready_for_equity_or_ev': False, 'hands_reconstructed': False,
              'hand_boundaries_confirmed': False, 'requires_hand_reconstruction': True,
              'observations': observations,
              'counts': {key: sum(x['decision'] == key for x in observations)
                         for key in ('confirmed', 'corrected', 'rejected', 'inconclusive', 'pending')},
              'warning': 'Human-reviewed OCR fields are not complete hands, opponent ranges, or validated EV inputs.'}
    with tempfile.TemporaryDirectory(prefix='.plo_ocr_review_', dir=output_dir.parent) as temp:
        stage = Path(temp)
        (stage / 'reviewed_ocr_observations.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', 'utf-8')
        require(sha(annotations_json) == annotations_sha, 'Annotations changed during review')
        _, final_sha = validate_source(ocr_dir)
        require(final_sha == report_sha, 'OCR report changed during review')
        require(not output_dir.exists(), 'Output path appeared during review')
        os.rename(stage, output_dir)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('ocr_output_dir', 'annotations_json', 'new_output_dir'):
        parser.add_argument(arg)
    args = parser.parse_args(argv)
    result = review(args.ocr_output_dir, args.annotations_json, args.new_output_dir)
    print(json.dumps(result['counts']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
