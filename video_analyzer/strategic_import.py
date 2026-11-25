"""Offline adapters for explicit synthetic strategy exchange format v1."""
import csv
import hashlib
import io
import json
from pathlib import Path

import strategic_store as store

FORMAT = 'plo-strategy-v1'
FIELDS = ('variant', 'scenario', 'actions')
MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 10000


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Nonfinite JSON constant: ' + value)


def _json(text):
    return json.loads(text, object_pairs_hook=_object, parse_constant=_constant)


def _rows(text, format):
    if format == 'json':
        envelope = _json(text)
        if (type(envelope) is not dict or set(envelope) != {'format', 'records'} or
                envelope['format'] != FORMAT or type(envelope['records']) is not list):
            raise ValueError('Expected versioned strategy JSON envelope')
        yield from envelope['records']
    else:
        reader = csv.reader(io.StringIO(text, newline=''), delimiter=',' if format == 'csv' else '\t', strict=True)
        if tuple(next(reader, ())) != FIELDS:
            raise ValueError('Expected exact variant,scenario,actions header')
        for fields in reader:
            if len(fields) != 3 or fields[0] not in ('5', '6'):
                raise ValueError('Invalid tabular row or variant')
            yield dict(variant=int(fields[0]), scenario=_json(fields[1]), actions=_json(fields[2]))


def read_file(path, *, source_id):
    """Parse and validate the entire file before allowing any database write."""
    path = Path(path)
    format = path.suffix.lower().lstrip('.')
    if format not in ('csv', 'json', 'txt'):
        raise ValueError('Unsupported format')
    if not path.is_file():
        raise ValueError('Expected a regular input file')
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError('Explicit source ID required')
    with path.open('rb') as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Input exceeds byte limit')
    prepared = []
    try:
        for number, row in enumerate(_rows(raw.decode('utf-8-sig'), format), 1):
            if number > MAX_ROWS:
                raise ValueError('Input exceeds row limit')
            if type(row) is not dict or set(row) != set(FIELDS):
                raise ValueError('Unexpected record fields')
            prepared.append(store.prepare_record(source_id, row['variant'], row['scenario'], row['actions'], synthetic=True))
    except (ValueError, TypeError, csv.Error, RecursionError, OverflowError) as exc:
        raise ValueError(f'Invalid {format} near record {len(prepared)+1}: {exc}') from exc
    if not prepared:
        raise ValueError('Empty strategy batch')
    return prepared, {'format': format, 'sha256': hashlib.sha256(raw).hexdigest(), 'read': len(prepared)}


def import_fixture(db, path, *, source_id, synthetic):
    """Import test fixtures only; no permission changes or production writes."""
    if synthetic is not True:
        raise ValueError('Only explicitly synthetic imports are supported')
    if db.in_transaction or not db.execute('PRAGMA foreign_keys').fetchone()[0]:
        raise ValueError('Expected idle connection with foreign keys enabled')
    if db.execute('PRAGMA user_version').fetchone()[0] != store.VERSION:
        raise ValueError('Unsupported database version')
    prepared, report = read_file(path, source_id=source_id)
    db.execute('BEGIN IMMEDIATE')
    try:
        if db.execute('SELECT 1 FROM sources WHERE id=?', (source_id,)).fetchone() is None:
            raise ValueError('Unknown source')
        inserted = sum(store.insert_prepared_record(db, item) for item in prepared)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return dict(report, source_id=source_id, synthetic=True, inserted=inserted,
                duplicates=report['read']-inserted)
