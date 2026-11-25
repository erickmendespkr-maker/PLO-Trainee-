"""Verify a reviewed PLO5 equity reference; never infer exact suits or GTO."""
import argparse
from contextlib import closing
import hashlib
import json
import os
import tempfile
from pathlib import Path
import sqlite3
import time

CSV_SHA = '5a636b991a836da6b01b5802f97b7b5bd1479a0dc2bda2482422efa0d3d94651'
DB_SHA = 'bddf887d08b9bfaeb55ab55e287b3398c31cf51620dde2ce9986baf7aeddaa9a'
EXPECTED = {'variant': '5', 'kind': 'equity_vs_one_random_opponent',
            'csv_sha256': CSV_SHA, 'schema_version': '1',
            'source': 'https://solvepoker.app/plo5-starting-hand-rankings',
            'license': 'https://creativecommons.org/licenses/by/4.0/',
            'attribution': 'SolvePoker (solvepoker.app)'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_connection(db, *, orbit_audit):
    """Structural checks only; caller is responsible for provenance."""
    require(db.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'SQLite integrity failure')
    tables = db.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    require(tables == [('equity','table'),('equity_descriptor','index'),('metadata','table')], 'Unexpected schema objects')
    require([r[1] for r in db.execute('PRAGMA table_info(equity)')] == ['rank','hand','suits','lo','hi','combos'], 'Unexpected equity columns')
    require([r[2] for r in db.execute('PRAGMA index_info(equity_descriptor)')] == ['hand','suits'], 'Missing descriptor index')
    meta = dict(db.execute('SELECT key,value FROM metadata'))
    require(all(meta.get(k)==v for k,v in EXPECTED.items()), 'Reference provenance metadata mismatch')
    count, combos, first, last = db.execute('SELECT count(*),sum(combos),min(rank),max(rank) FROM equity').fetchone()
    require((count,combos,first,last)==(134459,2598960,1,134459), 'Incomplete reference')
    result = orbit_audit(db)
    require(result['status']=='AGGREGATE_COUNTS_MATCH' and result['exact_orbits']==count and result['physical_combinations']==combos, 'Descriptor orbit coverage mismatch')
    plan = db.execute('EXPLAIN QUERY PLAN SELECT rank,lo,hi,combos FROM equity WHERE hand=? AND suits=? ORDER BY rank',('A-A-T-9-9','ds')).fetchall()
    require(any('equity_descriptor' in row[-1] for row in plan), 'Descriptor index not used')
    return {'rows':count,'physical_combinations':combos,'orbit_audit':result,'lookup_query_plan':[row[-1] for row in plan]}


def audit(database, *, csv_path=None):
    from plo5_equity_store import parse_rows
    from plo5_hand_classes import audit_source
    path = Path(database)
    require(path.is_file() and not path.is_symlink(), 'Existing regular SQLite file required')
    require(path.stat().st_size <= 64*1024**2, 'Database too large')
    before=sha(path); exact=before==DB_SHA
    rows=None
    if csv_path is not None:
        source=Path(csv_path)
        require(source.is_file() and not source.is_symlink() and source.stat().st_size<=8*1024**2,'Invalid CSV')
        raw=source.read_bytes()
        require(hashlib.sha256(raw).hexdigest()==CSV_SHA,'CSV differs from reviewed snapshot')
        rows=parse_rows(raw.decode('utf-8'))
    require(exact or rows is not None,'Unreviewed SQLite; provide the original reviewed CSV for comparison')
    start=time.perf_counter()
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('PRAGMA query_only=ON')
        result=validate_connection(db,orbit_audit=audit_source)
        if rows is not None:
            from itertools import zip_longest
            actual=db.execute('SELECT rank,hand,suits,lo,hi,combos FROM equity ORDER BY rank')
            require(all(a==b for a,b in zip_longest(actual,rows)), 'Database rows differ from reviewed CSV')
    require(sha(path)==before,'Database changed during audit')
    return {'variant':5,'status':'REVIEWED_EQUITY_REFERENCE','database_sha256':before,
            'original_binary_snapshot':exact,'csv_rows_compared':rows is not None,
            **result,'exact_suit_equity_available':False,'gto_records':0,'gto_solution':False,
            'strict_regression_snapshot_compatible':exact,'audit_seconds':time.perf_counter()-start}


def recover(database, csv_path):
    """Publish only after full audit; failed recovery never leaves a candidate DB."""
    from plo5_equity_store import import_csv
    dest=Path(database)
    require(dest.parent.is_dir() and not dest.exists() and not dest.is_symlink(), 'New database destination required')
    with tempfile.TemporaryDirectory(prefix='.plo5-reference-',dir=dest.parent) as tmp:
        stage=Path(tmp)/'reference.sqlite'
        import_csv(csv_path,stage)
        result=audit(stage,csv_path=csv_path)
        # No overwrite even if another process creates the destination after the guard.
        os.link(stage,dest)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('database');p.add_argument('--csv');p.add_argument('--recover',action='store_true')
    a=p.parse_args(argv)
    if a.recover:
        require(a.csv is not None,'Recovery requires original reviewed CSV')
        result=recover(a.database,a.csv)
    else:
        result=audit(a.database,csv_path=a.csv)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
