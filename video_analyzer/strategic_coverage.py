"""Persistent successful fixture batches and offline coverage reports."""
from collections import Counter, defaultdict
import json

SCHEMA = (
    """CREATE TABLE import_batches (
        id TEXT PRIMARY KEY NOT NULL,
        source_id TEXT NOT NULL REFERENCES sources(id),
        sha256 TEXT NOT NULL CHECK(length(sha256)=64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
        format TEXT NOT NULL CHECK(format IN ('csv','json','txt')),
        importer_version INTEGER NOT NULL CHECK(importer_version=1),
        row_count INTEGER NOT NULL CHECK(row_count>0),
        inserted INTEGER NOT NULL CHECK(inserted>=0 AND inserted<=row_count),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(source_id,sha256,format,importer_version)
    )""",
    """CREATE TABLE import_batch_records (
        batch_id TEXT NOT NULL REFERENCES import_batches(id),
        record_id TEXT NOT NULL REFERENCES records(id),
        occurrences INTEGER NOT NULL CHECK(occurrences>0),
        PRIMARY KEY(batch_id,record_id)
    )""",
    'CREATE INDEX batch_record_lookup ON import_batch_records(record_id)',
)


def batch_identity(source, report):
    from strategic_store import digest
    return digest([source, report['sha256'], report['format'], 1])


def persist_batch(db, source, report, prepared, inserted):
    """Participate in the caller's transaction; retain first successful import."""
    if not db.in_transaction:
        raise ValueError('Batch persistence requires a transaction')
    key = batch_identity(source, report)
    counts = Counter(item[1][0] for item in prepared)
    old = db.execute('SELECT row_count FROM import_batches WHERE id=?', (key,)).fetchone()
    if old is not None:
        links = dict(db.execute('SELECT record_id,occurrences FROM import_batch_records WHERE batch_id=?', (key,)))
        if old[0] != report['read'] or links != counts:
            raise ValueError('Replay differs from stored batch')
        return key, True
    db.execute('INSERT INTO import_batches(id,source_id,sha256,format,importer_version,row_count,inserted) VALUES (?,?,?,?,1,?,?)',
               (key, source, report['sha256'], report['format'], report['read'], inserted))
    db.executemany('INSERT INTO import_batch_records VALUES (?,?,?)', ((key, record, count) for record, count in sorted(counts.items())))
    return key, False


def audit_batches(db):
    """Check batch identities, counts and source linkage in a stable snapshot."""
    for key, source, sha, fmt, count, inserted, distinct, occurrences, foreign in db.execute(
        'SELECT b.id,b.source_id,b.sha256,b.format,b.row_count,b.inserted,count(l.record_id),'
        'coalesce(sum(l.occurrences),0),coalesce(sum(r.source_id<>b.source_id),0) '
        'FROM import_batches b LEFT JOIN import_batch_records l ON b.id=l.batch_id '
        'LEFT JOIN records r ON r.id=l.record_id GROUP BY b.id'):
        if (key != batch_identity(source, {'sha256': sha, 'format': fmt}) or
                count != occurrences or not 0 <= inserted <= distinct or foreign):
            raise ValueError('Invalid import batch provenance or counts')


def coverage(db, *, synthetic=False):
    """Exact scenario coverage only; never estimate coverage of the poker game tree."""
    if type(synthetic) is not bool:
        raise ValueError('Explicit boolean fixture flag required')
    groups = defaultdict(lambda: [0, set()])
    nodes = defaultdict(list)
    all_scenarios = set()
    normalized = 0
    for key, source, scenario, variant, context, payload in db.execute(
        'SELECT r.id,r.source_id,r.scenario_id,s.variant,s.context,r.payload '
        'FROM records r JOIN scenarios s ON s.id=r.scenario_id WHERE r.synthetic=? ORDER BY r.id', (int(synthetic),)):
        fields = json.loads(context)
        complete = fields.get('schema') == 'plo-decision-v2'
        normalized += int(complete)
        dimension = (source, variant, fields['street'] if complete else 'UNKNOWN',
                     fields['position'] if complete else 'UNKNOWN', fields['stack'] if complete else 'UNKNOWN')
        group = groups[dimension]
        group[0] += 1
        group[1].add(scenario)
        all_scenarios.add(scenario)
        nodes[(source, scenario)].append((key, payload))
    divergences = [{'source_id': source, 'scenario_id': scenario, 'record_ids': [key for key, _ in rows]}
                   for (source, scenario), rows in sorted(nodes.items()) if len({p for _, p in rows}) > 1]
    return {'synthetic': synthetic, 'records': sum(group[0] for group in groups.values()),
            'scenarios': len(all_scenarios), 'normalized_records': normalized,
            'groups': [dict(source_id=k[0], variant=k[1], street=k[2], position=k[3], stack_bb=k[4],
                            records=v[0], scenarios=len(v[1])) for k,v in sorted(groups.items())],
            'divergences': divergences,
            'batches': db.execute('SELECT count(*) FROM import_batches').fetchone()[0] if synthetic else 0}
