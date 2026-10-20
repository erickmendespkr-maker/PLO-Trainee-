"""Conservative temporal aggregation of *unverified* OCR candidates.

Repeated text is NOT evidence of a correct card or hand reconstruction.
No events from this module may be passed to EV analysis without human review.
"""
from collections import defaultdict
import json
import math
from pathlib import Path

FIELDS = frozenset({'pot', 'bet', 'board', 'hero_cards'})


def _candidate_key(value):
    if isinstance(value, list):
        if not value or not all(isinstance(c, str) for c in value):
            return None
        return tuple(value)
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
        return None
    return float(value)


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be finite and positive')
    return float(value)


def aggregate_candidates(candidates, *, min_samples=3, min_engine_confidence=.75, max_gap_seconds=2.):
    """Group consecutive identical OCR candidates by table/field/time.

    Every run is either a repeated candidate or a review item. Low confidence,
    missing parses, conflicting values and excessive time gaps break runs.
    Duplicate timestamps never count as independent samples. Runs never
    imply hand boundaries or associate a candidate with a particular hand.
    """
    if isinstance(min_samples, bool) or not isinstance(min_samples, int) or min_samples < 2:
        raise ValueError('min_samples must be an integer >= 2')
    if not 0 <= _positive(min_engine_confidence, 'min_engine_confidence') <= 1:
        raise ValueError('min_engine_confidence must be <= 1')
    gap = _positive(max_gap_seconds, 'max_gap_seconds')
    if not isinstance(candidates, list) or len(candidates) > 100000:
        raise ValueError('candidates must be a list of at most 100000 entries')
    grouped = defaultdict(list)
    for item in candidates:
        if not isinstance(item, dict):
            raise ValueError('Each candidate must be an object')
        table = item.get('table_id')
        field = item.get('field')
        stamp = item.get('timestamp')
        if isinstance(table, bool) or not isinstance(table, int) or not 1 <= table <= 4:
            raise ValueError('Invalid table_id')
        if field not in FIELDS:
            raise ValueError('Invalid field')
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp) or stamp < 0:
            raise ValueError('Invalid timestamp')
        grouped[(table, field)].append(item)
    stable, review = [], []

    def emit(run, table, field):
        if not run:
            return
        value = run[0]['parsed_candidate']
        item = {'table_id': table, 'field': field, 'first_timestamp': run[0]['timestamp'],
                'last_timestamp': run[-1]['timestamp'], 'parsed_candidate': value,
                'independent_samples': len(run),
                'min_engine_confidence': min(x['mean_engine_confidence'] for x in run),
                'source': 'temporal_ocr_repetition', 'human_confirmed': False}
        if len(run) >= min_samples:
            item['status'] = 'temporally_repeated_unverified'
            stable.append(item)
        else:
            item['status'] = 'needs_manual_review'
            review.append(item)

    for (table, field), items in sorted(grouped.items()):
        run = []
        for item in sorted(items, key=lambda x: x['timestamp']):
            confidence = item.get('mean_engine_confidence')
            key = _candidate_key(item.get('parsed_candidate'))
            valid = (item.get('status') == 'candidate_unverified'
                     and isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
                     and math.isfinite(confidence) and min_engine_confidence <= confidence <= 1
                     and key is not None)
            if not valid:
                emit(run, table, field)
                run = []
                review.append({'table_id': table, 'field': field,
                               'first_timestamp': item['timestamp'], 'last_timestamp': item['timestamp'],
                               'parsed_candidate': item.get('parsed_candidate'),
                               'independent_samples': 0, 'status': 'needs_manual_review',
                               'reason': 'invalid_or_low_confidence_candidate', 'human_confirmed': False})
                continue
            if run:
                prev = run[-1]
                previous_key = _candidate_key(prev['parsed_candidate'])
                dt = item['timestamp'] - prev['timestamp']
                if previous_key != key or dt > gap:
                    emit(run, table, field)
                    run = []
                elif dt == 0:
                    # Duplicate frame/timestamp is not independent evidence.
                    if item['mean_engine_confidence'] < prev['mean_engine_confidence']:
                        run[-1] = item
                    continue
            run.append(item)
        emit(run, table, field)
    return {'schema_version': 1, 'analysis_status': 'unverified_ocr_temporal_candidates_only',
            'stable_candidates': stable, 'review_items': review,
            'requires_manual_review': True,
            'warning': 'Repetition and Tesseract confidence are not calibrated probabilities; no direct EV input.'}


def aggregate_json(source, destination, **kwargs):
    raw = json.loads(Path(source).read_text(encoding='utf-8'))
    if not isinstance(raw, dict) or not isinstance(raw.get('candidates'), list):
        raise ValueError('Expected OCR candidate report with candidates list')
    result = aggregate_candidates(raw['candidates'], **kwargs)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate_json')
    parser.add_argument('output_json')
    parser.add_argument('--min-samples', type=int, default=3)
    parser.add_argument('--max-gap', type=float, default=2.)
    args = parser.parse_args()
    result = aggregate_json(args.candidate_json, args.output_json,
                            min_samples=args.min_samples, max_gap_seconds=args.max_gap)
    print(json.dumps({'stable_candidates': len(result['stable_candidates']),
                      'review_items': len(result['review_items'])}))
