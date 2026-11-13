"""Append-only local review assertions with hash chaining; not visual proof."""
import hashlib
import json
import math
import os
import re
from pathlib import Path

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def validate_review(record):
    if type(record) is not dict:
        raise ValueError('review must be object')
    required = {'source_sha256', 'hand_id', 'table_id', 'start_seconds', 'end_seconds', 'review_status'}
    if set(record) != required:
        raise ValueError('review fields mismatch')
    if type(record['source_sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', record['source_sha256']):
        raise ValueError('invalid source hash')
    if type(record['hand_id']) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', record['hand_id']):
        raise ValueError('invalid hand id')
    if type(record['table_id']) is not int or not 1 <= record['table_id'] <= 4:
        raise ValueError('invalid table')
    a, b = record['start_seconds'], record['end_seconds']
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in (a, b)) or not 0 <= a < b:
        raise ValueError('invalid interval')
    if record['review_status'] not in ('confirmed', 'insufficient_data'):
        raise ValueError('invalid review status')
    return dict(record)

def append_review(path, record):
    """Append one validated assertion. Requires a single writer."""
    record = validate_review(record)
    path = Path(path)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError('unsafe ledger path')
    previous = '0' * 64
    entries = []
    if path.exists():
        entries = verify_ledger(path)
        if entries:
            previous = entries[-1]['entry_sha256']
    entry = {'sequence': len(entries) + 1, 'previous_sha256': previous, 'review': record}
    entry['entry_sha256'] = hashlib.sha256(canonical(entry).encode('utf-8')).hexdigest()
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'a', encoding='utf-8') as stream:
        stream.write(canonical(entry) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    return entry

def verify_ledger(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular ledger required')
    previous = '0' * 64
    entries = []
    with path.open('r', encoding='utf-8') as stream:
        for line in stream:
            entry = json.loads(line)
            if type(entry) is not dict or set(entry) != {'sequence', 'previous_sha256', 'review', 'entry_sha256'}:
                raise ValueError('invalid ledger entry')
            validate_review(entry['review'])
            if type(entry['sequence']) is not int or entry['sequence'] != len(entries) + 1 or entry['previous_sha256'] != previous:
                raise ValueError('broken ledger chain')
            digest = hashlib.sha256(canonical({k: entry[k] for k in ('sequence', 'previous_sha256', 'review')}).encode('utf-8')).hexdigest()
            if entry['entry_sha256'] != digest:
                raise ValueError('ledger entry hash mismatch')
            previous = digest
            entries.append(entry)
    return entries
