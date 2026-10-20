"""Evaluate offline OCR candidates against manually annotated video ground truth.

A matching timestamp and field are necessary, not evidence of correctness.
Report *coverage* and *conditional accuracy* separately; no accuracy claims
are valid until a representative real-video ground-truth set is supplied.
"""
import json
import math
from pathlib import Path

FIELDS = frozenset({'pot', 'bet', 'board', 'hero_cards'})


def _validate(item, *, truth):
    if not isinstance(item, dict):
        raise ValueError('Expected object')
    table, field, stamp = item.get('table_id'), item.get('field'), item.get('timestamp')
    if isinstance(table, bool) or not isinstance(table, int) or not 1 <= table <= 4:
        raise ValueError('Invalid table_id')
    if field not in FIELDS:
        raise ValueError('Invalid field')
    if isinstance(stamp, bool) or not isinstance(stamp, (float, int)) or not math.isfinite(stamp) or stamp < 0:
        raise ValueError('Invalid timestamp')
    value = item.get('expected') if truth else item.get('parsed_candidate')
    if truth and value is None:
        raise ValueError('Ground truth cannot be missing')
    if value is not None:
        if field in ('board', 'hero_cards'):
            if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
                raise ValueError('Invalid card-list value')
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid amount value')


def score_ocr(candidates, ground_truth, *, tolerance_seconds=.5):
    """Nearest-neighbor one-to-one comparison within each table/field.

    A parsed candidate counts as answered only if its status is
    'candidate_unverified'. Incorrect readings are not counted as abstentions.
    Returns None for accuracy on empty sets or with zero answered examples.
    """
    if not isinstance(candidates, list) or not isinstance(ground_truth, list):
        raise ValueError('Candidates and ground_truth must be lists')
    if len(candidates) > 100000 or len(ground_truth) > 100000:
        raise ValueError('Too many samples')
    if isinstance(tolerance_seconds, bool) or not isinstance(tolerance_seconds, (int, float)) or not math.isfinite(tolerance_seconds) or tolerance_seconds < 0:
        raise ValueError('Invalid time tolerance')
    for row in candidates:
        _validate(row, truth=False)
    for row in ground_truth:
        _validate(row, truth=True)
    keys = [(g['table_id'], g['field'], g['timestamp']) for g in ground_truth]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate ground-truth keys')
    used = set()
    correct = incorrect = abstained = 0
    details = []
    for gold in ground_truth:
        choices = [(abs(gold['timestamp'] - pred['timestamp']), i) for i, pred in enumerate(candidates)
                   if i not in used and pred['table_id'] == gold['table_id']
                   and pred['field'] == gold['field']
                   and abs(gold['timestamp'] - pred['timestamp']) <= tolerance_seconds]
        if not choices:
            abstained += 1
            details.append({'table_id': gold['table_id'], 'field': gold['field'],
                            'timestamp': gold['timestamp'], 'outcome': 'missing'})
            continue
        _, idx = min(choices)
        used.add(idx)
        pred = candidates[idx]
        answered = pred.get('status') == 'candidate_unverified' and pred.get('parsed_candidate') is not None
        outcome = 'abstained'
        if not answered:
            abstained += 1
        elif pred['parsed_candidate'] == gold['expected']:
            correct += 1
            outcome = 'correct'
        else:
            incorrect += 1
            outcome = 'incorrect'
        details.append({'table_id': gold['table_id'], 'field': gold['field'],
                        'timestamp': gold['timestamp'], 'outcome': outcome})
    total = len(ground_truth)
    answered = correct + incorrect
    return {'schema_version': 1, 'ground_truth_samples': total,
            'correct': correct, 'incorrect': incorrect, 'abstained_or_missing': abstained,
            'unmatched_predictions': len(candidates) - len(used),
            'coverage': answered / total if total else None,
            'answered_accuracy': correct / answered if answered else None,
            'overall_accuracy': correct / total if total else None,
            'details': details,
            'warning': 'Metrics apply only to the supplied labeled samples, not to other videos or layouts.'}


def score_json(ocr_report_path, truth_path, output_path, **kwargs):
    report = json.loads(Path(ocr_report_path).read_text(encoding='utf-8'))
    truth = json.loads(Path(truth_path).read_text(encoding='utf-8'))
    if not isinstance(report, dict) or not isinstance(report.get('candidates'), list):
        raise ValueError('Expected OCR report with candidates list')
    result = score_ocr(report['candidates'], truth, **kwargs)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ocr_report_json')
    parser.add_argument('ground_truth_json')
    parser.add_argument('output_json')
    args = parser.parse_args()
    result = score_json(args.ocr_report_json, args.ground_truth_json, args.output_json)
    print(json.dumps({k: result[k] for k in ('ground_truth_samples', 'coverage', 'answered_accuracy')}))
