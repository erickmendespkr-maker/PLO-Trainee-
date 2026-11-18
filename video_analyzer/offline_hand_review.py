"""Bind explicit human corrections to immutable, provisional OCR observations."""
import hashlib
import json


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def apply_reviews(ledger, reviews):
    if not isinstance(ledger, dict) or ledger.get('schema_version') != 1:
        raise ValueError('unsupported ledger')
    expected = ledger.get('ledger_sha256')
    base = {k: v for k, v in ledger.items() if k != 'ledger_sha256'}
    if not isinstance(expected, str) or _digest(base) != expected:
        raise ValueError('ledger integrity failure')
    observations = ledger.get('observations')
    if not isinstance(observations, list) or not isinstance(reviews, list):
        raise ValueError('invalid input')
    if any(not isinstance(o, dict) or o.get('verified_by_human') is not False or o.get('value') is not None for o in observations):
        raise ValueError('expected provisional observations')
    output = []
    reviewed = set()
    for item in reviews:
        if not isinstance(item, dict) or set(item) != {'observation_index', 'corrected_value', 'reviewer', 'review_note'}:
            raise ValueError('invalid review')
        index = item['observation_index']
        value = item['corrected_value']
        reviewer = item['reviewer']
        note = item['review_note']
        if type(index) is not int or not 0 <= index < len(observations) or index in reviewed:
            raise ValueError('invalid or repeated observation index')
        if not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise ValueError('invalid corrected value')
        if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 128:
            raise ValueError('invalid reviewer')
        if not isinstance(note, str) or not note.strip() or len(note) > 1024:
            raise ValueError('review reason required')
        reviewed.add(index)
        output.append({'observation_index': index, 'corrected_value': value, 'reviewer': reviewer, 'review_note': note})
    output.sort(key=lambda x: x['observation_index'])
    result = {'schema_version': 1, 'ledger_sha256': expected, 'reviews': output, 'unreviewed_count': len(observations) - len(output), 'strategy_validated': False}
    result['review_sha256'] = _digest(result)
    return result
