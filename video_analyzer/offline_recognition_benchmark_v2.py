"""Offline, non-authoritative OCR benchmark against manually labeled observations.

Usage: python offline_recognition_benchmark_v2.py OCR_REPORT.json GOLD.json NEW_REPORT.json

This evaluator cannot prove any prediction or hand is correct. It measures only
agreement with the supplied human labels; synthetic labels never establish real
video accuracy. No poker equity, EV, or real-time integration is performed.

Inputs:
  OCR_REPORT: {"candidates": [{"table_id": 1, "field": "pot", "timestamp": 1.0,
                "parsed_candidate": 20, "status": "candidate_unverified"}, ...]}
  GOLD: [{"table_id": 1, "field": "pot", "timestamp": 1.0, "expected": 20}, ...]
Fields: pot, bet, board, hero_cards. The status candidate_unverified denotes an
answered OCR proposal, NOT a human-verified fact.

Matching is deterministic, one-to-one, and maximizes the number of temporally
matchable observations within each (table, field). Sorted earliest-feasible
matching does NOT guarantee minimum total timestamp error. That tradeoff is
recorded explicitly and the matched time deltas are returned.
"""
from __future__ import annotations

from collections import defaultdict
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

FIELDS = frozenset({'pot', 'bet', 'board', 'hero_cards'})
MAX_ROWS = 100_000
MAX_INPUT_BYTES = 32 * 1024 * 1024
Z95 = 1.959963984540054


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _value(field, value, *, truth):
    if value is None:
        require(not truth, 'ground truth cannot be empty')
        return
    if field in ('pot', 'bet'):
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                'invalid numeric amount')
    else:
        require(type(value) is list and 1 <= len(value) <= (5 if field == 'board' else 6)
                and all(type(x) is str and 2 <= len(x) <= 3 for x in value),
                'invalid card-list candidate')


def _row(row, truth):
    require(type(row) is dict, 'observation must be an object')
    require(type(row.get('table_id')) is int and 1 <= row['table_id'] <= 4,
            'table_id must be 1..4')
    require(type(row.get('field')) is str and row['field'] in FIELDS,
            'invalid field')
    require(type(row.get('timestamp')) in (int, float) and
            math.isfinite(row['timestamp']) and 0 <= row['timestamp'] <= 14400,
            'invalid timestamp')
    if truth:
        require('expected' in row, 'ground truth expected missing')
        _value(row['field'], row['expected'], truth=True)
    else:
        require(type(row.get('status')) is str and row['status'] in
                {'candidate_unverified', 'needs_manual_review', 'abstained', 'rejected'},
                'invalid candidate status')
        _value(row['field'], row.get('parsed_candidate'), truth=False)
    return (row['table_id'], row['field'])


def wilson(successes, trials):
    """Two-sided Wilson 95% interval, None when no denominator exists."""
    if not trials:
        return None
    p = successes / trials
    denom = 1 + Z95 * Z95 / trials
    center = (p + Z95 * Z95 / (2 * trials)) / denom
    radius = (Z95 / denom) * math.sqrt((p * (1 - p) / trials) +
                                        (Z95 * Z95 / (4 * trials * trials)))
    return [max(0.0, center - radius), min(1.0, center + radius)]


def _counts(correct, incorrect, abstained, unmatched_answered, unmatched_abstained):
    total = correct + incorrect + abstained
    answered = correct + incorrect
    predicted = answered + unmatched_answered
    precision = correct / predicted if predicted else None
    recall = correct / total if total else None
    return {
        'labeled': total, 'correct': correct, 'incorrect': incorrect,
        'abstained_or_missing': abstained,
        'unmatched_answered_predictions': unmatched_answered,
        'unmatched_abstaining_predictions': unmatched_abstained,
        'coverage': answered / total if total else None,
        'answered_accuracy': correct / answered if answered else None,
        'answered_accuracy_wilson95': wilson(correct, answered),
        'strict_precision': precision,
        'strict_recall': recall,
        'strict_recall_wilson95': wilson(correct, total),
        'strict_f1': 2 * precision * recall / (precision + recall)
                     if precision is not None and recall is not None and
                     precision + recall else None,
    }


def evaluate(candidates, truth, *, tolerance_seconds=0.5):
    require(type(candidates) is list and type(truth) is list and
            len(candidates) <= MAX_ROWS and len(truth) <= MAX_ROWS,
            'invalid or oversized observations')
    require(type(tolerance_seconds) in (int, float) and
            math.isfinite(tolerance_seconds) and 0 <= tolerance_seconds <= 30,
            'invalid tolerance')
    groups = defaultdict(lambda: {'gold': [], 'pred': []})
    seen_gold = set()
    for i, row in enumerate(truth):
        key = _row(row, True)
        unique = (*key, row['timestamp'])
        require(unique not in seen_gold, 'duplicate ground-truth key')
        seen_gold.add(unique)
        groups[key]['gold'].append((row['timestamp'], i, row))
    for i, row in enumerate(candidates):
        key = _row(row, False)
        groups[key]['pred'].append((row['timestamp'], i, row))
    details = []
    strata = []
    sums = [0, 0, 0, 0, 0]
    for key in sorted(groups):
        gold = sorted(groups[key]['gold'])
        pred = sorted(groups[key]['pred'])
        # Earliest-feasible chronological matching on two sorted sequences.
        # O(n log n) overall, versus quadratic nearest-neighbor scans.
        i = j = 0
        used = set()
        correct = incorrect = missing = 0
        while i < len(gold):
            ts, gold_idx, g = gold[i]
            while j < len(pred) and pred[j][0] < ts - tolerance_seconds:
                j += 1
            if j >= len(pred) or pred[j][0] > ts + tolerance_seconds:
                missing += 1
                details.append({'ground_truth_index': gold_idx, 'table_id': key[0],
                                'field': key[1], 'timestamp': ts,
                                'outcome': 'missing'})
            else:
                pts, pred_idx, p = pred[j]
                used.add(pred_idx)
                answered = (p['status'] == 'candidate_unverified' and
                            p.get('parsed_candidate') is not None)
                outcome = 'abstained'
                if not answered:
                    missing += 1
                elif p['parsed_candidate'] == g['expected']:
                    correct += 1
                    outcome = 'correct'
                else:
                    incorrect += 1
                    outcome = 'incorrect'
                details.append({'ground_truth_index': gold_idx, 'table_id': key[0],
                                'field': key[1], 'timestamp': ts,
                                'prediction_index': pred_idx,
                                'timestamp_error_seconds': round(pts - ts, 9),
                                'outcome': outcome})
                j += 1
            i += 1
        unmatched_answered = sum(p['status'] == 'candidate_unverified' and
                                 p.get('parsed_candidate') is not None
                                 for _, idx, p in pred if idx not in used)
        unmatched_abstained = len(pred) - len(used) - unmatched_answered
        row = _counts(correct, incorrect, missing, unmatched_answered,
                      unmatched_abstained)
        row.update({'table_id': key[0], 'field': key[1]})
        strata.append(row)
        for idx, value in enumerate((correct, incorrect, missing,
                                     unmatched_answered, unmatched_abstained)):
            sums[idx] += value
    summary = _counts(*sums)
    return {
        'schema_version': 2,
        'status': 'offline_label_agreement_only_not_validated_on_real_video',
        'tolerance_seconds': tolerance_seconds,
        'matching_strategy': 'max_cardinality_earliest_feasible_per_table_field',
        'summary': summary,
        'by_table_field': strata,
        'details': sorted(details, key=lambda x: x['ground_truth_index']),
        'human_ground_truth_authenticity_verified': False,
        'ocr_engine_confidence_calibrated': False,
        'hands_reconstructed': False,
        'equity_ev_authorized': False,
        'limitations': [
            'Scores describe agreement only with supplied labels, not real-video accuracy.',
            'A wrong answer counts as both a false positive and a false negative in strict precision/recall.',
            'Timestamp alignment is max-cardinality, not minimum-error; matched deltas are reported.',
            'Wilson intervals describe sampling uncertainty, not label correctness or OCR calibration.',
            'Human labels and video provenance must be validated separately.']}


def _load(path):
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= MAX_INPUT_BYTES, 'invalid input JSON file')
    def no_duplicates(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, 'duplicate JSON key')
            out[key] = value
        return out
    def no_constant(value):
        raise ValueError('nonfinite JSON constant')
    return json.loads(path.read_text(encoding='utf-8'),
                      object_pairs_hook=no_duplicates, parse_constant=no_constant)


def _sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def run(ocr_path, gold_path, output_path, *, tolerance_seconds=0.5):
    ocr, gold, output = map(Path, (ocr_path, gold_path, output_path))
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink(),
            'output must be a new file in an existing directory')
    require(len({str(p.resolve()) for p in (ocr, gold, output)}) == 3,
            'inputs and output must differ')
    before = (_sha(ocr), _sha(gold))
    source = _load(ocr)
    labels = _load(gold)
    require(type(source) is dict and type(source.get('candidates')) is list,
            'expected OCR report with candidates')
    result = evaluate(source['candidates'], labels, tolerance_seconds=tolerance_seconds)
    require((_sha(ocr), _sha(gold)) == before, 'inputs changed during evaluation')
    result['source_ocr_sha256'] = before[0]
    result['source_ground_truth_sha256'] = before[1]
    with tempfile.TemporaryDirectory(prefix='.plo_eval_', dir=output.parent) as tmp:
        staged = Path(tmp) / 'report.json'
        staged.write_text(json.dumps(result, indent=2, ensure_ascii=False,
                                     allow_nan=False) + '\n', encoding='utf-8')
        os.link(staged, output)  # create-only; never overwrite an existing result
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ocr_report_json')
    parser.add_argument('ground_truth_json')
    parser.add_argument('new_output_json')
    parser.add_argument('--tolerance-seconds', type=float, default=0.5)
    args = parser.parse_args(argv)
    result = run(args.ocr_report_json, args.ground_truth_json,
                 args.new_output_json, tolerance_seconds=args.tolerance_seconds)
    print(json.dumps({'labeled': result['summary']['labeled'],
                      'strict_recall': result['summary']['strict_recall'],
                      'coverage': result['summary']['coverage']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
