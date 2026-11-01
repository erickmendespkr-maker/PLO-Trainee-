"""Benchmark actual four-table OCR proposals against separate human labels, offline.

Usage: python offline_four_table_ocr_benchmark_bridge.py OCR_REPORT.json GOLD.json NEW_REPORT.json

Raw OCR is parsed conservatively; ambiguous/unparseable values ABSTAIN. The
result is diagnostic only and cannot authorize reconstruction, equity, or EV.
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

from offline_recognition_benchmark_v2 import evaluate

STATUS = 'unverified_four_table_ocr_proposals_only'
FIELDS = frozenset({'pot', 'bet', 'board', 'hero_cards'})
SOURCE_FIELDS = FIELDS | {'stack', 'action'}
SHA = re.compile(r'[0-9a-f]{64}\Z')
CARD = re.compile(r'[2-9TJQKA][cdhs]\Z')
AMOUNT = re.compile(r'(?:0|[1-9]\d{0,8})(?:\.\d{1,2})?\Z')
MAX_BYTES = 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'duplicate JSON key')
        out[key] = value
    return out


def load(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= MAX_BYTES, 'invalid input JSON')
    return json.loads(path.read_text('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def parse(field, raw):
    """Return an exact unambiguous proposal or None; never infer missing cards."""
    require(type(raw) is str and len(raw) <= 4096, 'invalid raw OCR text')
    value = raw.strip()
    if field in ('pot', 'bet'):
        return float(value) if AMOUNT.fullmatch(value) else None
    cards = value.split()
    allowed = (5, 6) if field == 'hero_cards' else range(1, 6)
    if len(cards) not in allowed or not all(CARD.fullmatch(c) for c in cards):
        return None
    if len(set(cards)) != len(cards):
        return None
    return cards


def adapt(source):
    require(type(source) is dict and source.get('schema_version') == 1 and
            source.get('analysis_status') == STATUS and
            source.get('ready_for_equity_or_ev') is False and
            source.get('requires_manual_review') is True and
            source.get('automatic_hand_or_action_inference') is False and
            source.get('engine_confidence_is_calibrated_probability') is False and
            type(source.get('recording_sha256')) is str and
            SHA.fullmatch(source['recording_sha256']) and
            type(source.get('source_region_samples_sha256')) is str and
            SHA.fullmatch(source['source_region_samples_sha256']) and
            type(source.get('candidates')) is list and
            1 <= len(source['candidates']) <= 32,
            'invalid or promoted original OCR report')
    predictions, abstained, skipped, seen = [], 0, {}, set()
    for index, c in enumerate(source['candidates']):
        require(type(c) is dict and type(c.get('table_id')) is int and
                1 <= c['table_id'] <= 4 and
                type(c.get('sample_index')) is int and c['sample_index'] >= 0 and
                type(c.get('field')) is str and c['field'] in SOURCE_FIELDS and
                type(c.get('decoded_source_pts_seconds')) in (int, float) and
                math.isfinite(c['decoded_source_pts_seconds']) and
                0 <= c['decoded_source_pts_seconds'] <= 14400 and
                c.get('status') == 'needs_manual_review' and
                c.get('parsed_candidate') is None and
                type(c.get('source_crop_sha256')) is str and
                SHA.fullmatch(c['source_crop_sha256']) and
                type(c.get('source_crop_path')) is str and
                1 <= len(c['source_crop_path']) <= 512,
                'invalid OCR candidate or source evidence')
        key = (c['table_id'], c['sample_index'], c['field'])
        require(key not in seen, 'duplicate OCR candidate identity')
        seen.add(key)
        if c['field'] not in FIELDS:
            skipped[c['field']] = skipped.get(c['field'], 0) + 1
            continue
        candidate = parse(c['field'], c.get('raw_ocr_text'))
        if candidate is None:
            abstained += 1
        predictions.append({'table_id': c['table_id'], 'field': c['field'],
                            'timestamp': c['decoded_source_pts_seconds'],
                            'parsed_candidate': candidate,
                            'status': ('candidate_unverified' if candidate is not None
                                       else 'abstained'), 'source_candidate_index': index})
    return predictions, abstained, skipped


def build(source, gold, ocr_sha, gold_sha, *, tolerance_seconds=0.5):
    require(type(gold) is list and len(gold) <= 100000 and
            all(type(row) is dict and row.get('field') in FIELDS for row in gold),
            'ground truth must use supported fields only')
    predictions, abstained, skipped = adapt(source)
    result = evaluate(predictions, gold, tolerance_seconds=tolerance_seconds)
    result.update({'schema_version': 1,
                   'underlying_evaluation_schema_version': 2,
                   'status': 'offline_raw_ocr_label_agreement_only',
                   'source_original_ocr_sha256': ocr_sha,
                   'source_human_labels_sha256': gold_sha,
                   'source_recording_sha256_claim': source['recording_sha256'],
                   'source_region_samples_sha256_claim': source['source_region_samples_sha256'],
                   'original_candidate_count': len(source['candidates']),
                   'evaluated_candidate_count': len(predictions),
                   'unparseable_or_ambiguous_abstentions': abstained,
                   'excluded_unsupported_fields': skipped,
                   'raw_ocr_not_human_reviewed': True,
                   'raw_ocr_confidence_not_calibrated': True,
                   'ground_truth_video_authenticity_not_verified': True,
                   'ready_for_equity_or_ev': False,
                   'hands_reconstructed': False,
                   'warning': 'Agreement with supplied labels only; no evidence of real-video accuracy, no math authorization.'})
    return result


def run(ocr_path, gold_path, output_path, *, tolerance_seconds=0.5):
    ocr, gold, out = map(Path, (ocr_path, gold_path, output_path))
    require(out.parent.is_dir() and not out.parent.is_symlink() and
            not out.exists() and not out.is_symlink() and
            len({str(p.resolve()) for p in (ocr, gold, out)}) == 3,
            'output must be new and distinct')
    before = sha(ocr), sha(gold)
    result = build(load(ocr), load(gold), *before, tolerance_seconds=tolerance_seconds)
    require((sha(ocr), sha(gold)) == before, 'inputs changed during benchmark')
    with tempfile.TemporaryDirectory(prefix='.plo_ocr_benchmark_', dir=out.parent) as tmp:
        stage = Path(tmp) / 'report.json'
        stage.write_text(json.dumps(result, indent=2, ensure_ascii=False,
                                    allow_nan=False) + '\n', encoding='utf-8')
        os.link(stage, out)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('original_ocr_report')
    p.add_argument('human_ground_truth')
    p.add_argument('new_output_json')
    p.add_argument('--tolerance-seconds', type=float, default=0.5)
    a = p.parse_args(argv)
    r = run(a.original_ocr_report, a.human_ground_truth, a.new_output_json,
            tolerance_seconds=a.tolerance_seconds)
    print(json.dumps({'labeled': r['summary']['labeled'],
                      'strict_recall': r['summary']['strict_recall'],
                      'ready_for_equity_or_ev': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
