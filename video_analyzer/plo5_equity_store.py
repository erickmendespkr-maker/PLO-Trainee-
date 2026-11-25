"""Offline import of the reviewed SolvePoker PLO5 equity CSV (not GTO)."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from decimal import Decimal

SHA256 = '5a636b991a836da6b01b5802f97b7b5bd1479a0dc2bda2482422efa0d3d94651'
SOURCE = 'https://solvepoker.app/plo5-starting-hand-rankings'
LICENSE = 'https://creativecommons.org/licenses/by/4.0/'
FIELDS = ['rank', 'hand', 'suits', 'equity_lo', 'equity_hi', 'combos']
RANKS = 'AKQJT98765432'
SUITS = {'ds', 'ss', '3-suit', '3+2', '4-suit', 'mono'}


def parse_rows(text):
    reader = csv.DictReader(line for line in io.StringIO(text) if not line.startswith('#'))
    if reader.fieldnames != FIELDS:
        raise ValueError('Unexpected CSV schema')
    for ordinal, row in enumerate(reader, 1):
        if None in row or any(v is None for v in row.values()):
            raise ValueError('Malformed CSV row')
        cards = row['hand'].split('-')
        if (int(row['rank']) != ordinal or len(cards) != 5 or
                any(c not in RANKS or len(c) != 1 for c in cards) or
                max(cards.count(c) for c in cards) > 4 or
                cards != sorted(cards, key=RANKS.index) or row['suits'] not in SUITS):
            raise ValueError('Invalid class descriptor')
        lo, hi = Decimal(row['equity_lo']), Decimal(row['equity_hi'])
        combos = int(row['combos'])
        if not (lo.is_finite() and hi.is_finite() and 0 <= lo <= hi <= 1 and combos in (4, 12, 24)):
            raise ValueError('Invalid equity or combination count')
        yield ordinal, row['hand'], row['suits'], str(lo), str(hi), combos


def import_csv(source, destination):
    """Create a separate SQLite file atomically; no overwrite or strategy records."""
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    if source.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('File exceeds reviewed size limit')
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SHA256:
        raise ValueError('CSV differs from reviewed licensed snapshot')
    text = raw.decode('utf-8')
    comments = '\n'.join(line for line in text.splitlines() if line.startswith('#'))
    rows = list(parse_rows(text))
    if len(rows) != 134459 or sum(r[5] for r in rows) != 2598960:
        raise ValueError('Unexpected class or combination count')
    fd, tmp = tempfile.mkstemp(prefix='.equity-', suffix='.db', dir=destination.parent)
    os.close(fd)
    try:
        db = sqlite3.connect(tmp)
        try:
            with db:
                db.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)')
                db.execute('CREATE TABLE equity(rank INTEGER PRIMARY KEY, hand TEXT NOT NULL, suits TEXT NOT NULL, lo TEXT NOT NULL, hi TEXT NOT NULL, combos INTEGER NOT NULL)')
                db.executemany('INSERT INTO equity VALUES (?,?,?,?,?,?)', rows)
                db.execute('CREATE INDEX equity_descriptor ON equity(hand,suits)')
                db.executemany('INSERT INTO metadata VALUES (?,?)', {
                    'source': SOURCE, 'attribution': 'SolvePoker (solvepoker.app)', 'license': LICENSE,
                    'csv_sha256': digest, 'source_comments': comments, 'variant': '5',
                    'kind': 'equity_vs_one_random_opponent', 'schema_version': '1',
                    'transformation': 'CSV to SQLite; original rows retained; no exact suit mapping inferred'}.items())
            if db.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise ValueError('SQLite integrity failure')
            report = dict(rows=db.execute('SELECT count(*) FROM equity').fetchone()[0],
                          combinations=db.execute('SELECT sum(combos) FROM equity').fetchone()[0],
                          descriptors=db.execute('SELECT count(*) FROM (SELECT hand,suits FROM equity GROUP BY hand,suits)').fetchone()[0],
                          sha256=digest, gto_records=0)
        finally:
            db.close()
        os.link(tmp, destination)
        return report
    finally:
        os.unlink(tmp)


def lookup_descriptor(db, hand, suits):
    """Return all matching source rows, never resolve an omitted suit assignment."""
    rows = db.execute('SELECT rank,lo,hi,combos FROM equity WHERE hand=? AND suits=? ORDER BY rank', (hand,suits)).fetchall()
    if not rows:
        return {'status': 'NO_MATCH', 'kind': 'equity_vs_one_random_opponent', 'gto': False}
    return {'status': 'AMBIGUOUS_DESCRIPTOR' if len(rows) > 1 else 'DESCRIPTOR_ONLY',
            'kind': 'equity_vs_one_random_opponent', 'gto': False,
            'equity_lo': str(min(Decimal(r[1]) for r in rows)),
            'equity_hi': str(max(Decimal(r[2]) for r in rows)),
            'matches': len(rows), 'rows': rows, 'exact_suit_match': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv')
    parser.add_argument('sqlite')
    args = parser.parse_args()
    print(json.dumps(import_csv(args.csv, args.sqlite), indent=2))
