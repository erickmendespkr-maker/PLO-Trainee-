"""Local strategic SQLite store. v3 adds audited source permission reviews."""
from datetime import date
import hashlib
import json
import math
import sqlite3
import re
import strategic_normalize as norm

VERSION = 3
SCHEMA = """
BEGIN IMMEDIATE;
CREATE TABLE sources (
    id TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL,
    license TEXT NOT NULL, evidence TEXT NOT NULL,
    permission TEXT NOT NULL DEFAULT 'pending' CHECK(permission = 'pending')
);
CREATE TABLE scenarios (
    id TEXT PRIMARY KEY NOT NULL,
    variant INTEGER NOT NULL CHECK(typeof(variant) = 'integer' AND variant IN (5,6)),
    context TEXT NOT NULL,
    UNIQUE(variant, context)
);
CREATE TABLE records (
    id TEXT PRIMARY KEY NOT NULL,
    source_id TEXT NOT NULL REFERENCES sources(id),
    scenario_id TEXT NOT NULL REFERENCES scenarios(id),
    payload TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK(synthetic = 1),
    UNIQUE(source_id, scenario_id, payload, synthetic)
);
CREATE INDEX records_lookup ON records(scenario_id, synthetic, source_id);
PRAGMA user_version = 2;
COMMIT;
"""


def connect(path):
    db = sqlite3.connect(path)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version == 0:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1").fetchone():
                raise ValueError('Unversioned nonempty database; migration required')
            db.executescript(SCHEMA)
        elif version not in (2, VERSION):
            raise ValueError('Unsupported schema version; migration required')
        migrate_permissions(db)
        return db
    except BaseException:
        db.close()
        raise


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def add_source(db, name, license, evidence):
    if not all(isinstance(x, str) and x.strip() for x in (name, license, evidence)):
        raise ValueError('Source provenance required')
    key = digest([name, license, evidence])
    with db:
        db.execute('INSERT INTO sources(id,name,license,evidence) VALUES (?,?,?,?) ON CONFLICT(id) DO NOTHING',
                   (key, name, license, evidence))
    return key


def scenario_identity(variant, scenario):
    if type(variant) is not int or variant not in (5, 6):
        raise ValueError('Invalid variant')
    if not isinstance(scenario, dict) or not scenario or any(type(k) is not str for k in scenario):
        raise ValueError('Invalid scenario')
    if "schema" in scenario:
        scenario = norm.normalize_scenario(variant, scenario)
    context = canonical(scenario)
    return digest([variant, context]), context


def prepare_record(source, variant, scenario, actions, *, synthetic):
    if synthetic is not True:
        raise ValueError('Real strategy writes disabled pending normalized import validation')
    if isinstance(scenario, dict) and scenario.get("schema") == norm.SCHEMA:
        scenario, actions = norm.normalize_record(variant, scenario, actions)
        scenario_id, context = scenario_identity(variant, scenario)
        payload = canonical(actions)
        key = digest([source, scenario_id, payload, True])
        return (scenario_id, variant, context), (key, source, scenario_id, payload)
    scenario_id, context = scenario_identity(variant, scenario)
    if not isinstance(actions, dict) or not actions:
        raise ValueError('Invalid actions')
    for action, p in actions.items():
        if action not in ('fold', 'check', 'call', 'bet', 'raise', 'all_in') or type(p) not in (int, float) or not 0 <= p <= 1:
            raise ValueError('Invalid action or frequency')
    if not math.isclose(sum(actions.values()), 1, rel_tol=0, abs_tol=1e-6):
        raise ValueError('Frequencies must sum to one')
    payload = canonical(actions)
    key = digest([source, scenario_id, payload, True])
    return (scenario_id, variant, context), (key, source, scenario_id, payload)


def insert_prepared_record(db, prepared):
    """Internal transaction participant; caller must validate and commit."""
    scenario, record = prepared
    db.execute('INSERT INTO scenarios VALUES (?,?,?) ON CONFLICT(id) DO NOTHING', scenario)
    return db.execute('INSERT INTO records VALUES (?,?,?,?,1) ON CONFLICT(id) DO NOTHING', record).rowcount


def add_record(db, source, variant, scenario, actions, *, synthetic):
    prepared = prepare_record(source, variant, scenario, actions, synthetic=synthetic)
    with db:
        insert_prepared_record(db, prepared)
    return prepared[1][0]


def lookup(db, variant, scenario, *, synthetic=False):
    scenario_id, _ = scenario_identity(variant, scenario)
    if type(synthetic) is not bool:
        raise ValueError('Invalid synthetic flag')
    return [(source, json.loads(payload)) for source, payload in db.execute(
        'SELECT source_id,payload FROM records WHERE scenario_id=? AND synthetic=? ORDER BY id',
        (scenario_id, int(synthetic)))]


# The v2 sources.permission column is a legacy pending-only marker.
# The latest review below is the authoritative local permission metadata.
# An approval records a human decision; it does not independently verify a license.
PERMISSION_SCHEMA = (
    """CREATE TABLE source_permission_reviews (
        id INTEGER PRIMARY KEY,
        source_id TEXT NOT NULL REFERENCES sources(id),
        status TEXT NOT NULL CHECK(status IN ('pending','allowed','restricted')),
        local_use INTEGER NOT NULL CHECK(local_use IN (0,1)),
        redistribution INTEGER NOT NULL CHECK(redistribution IN (0,1)),
        reviewer TEXT NOT NULL CHECK(length(trim(reviewer)) > 0),
        reviewed_on TEXT NOT NULL,
        evidence_ref TEXT NOT NULL CHECK(length(trim(evidence_ref)) > 0),
        evidence_sha256 TEXT NOT NULL CHECK(length(evidence_sha256) = 64 AND evidence_sha256 NOT GLOB '*[^0-9a-f]*'),
        source_version TEXT NOT NULL CHECK(length(trim(source_version)) > 0),
        scope TEXT NOT NULL CHECK(length(trim(scope)) > 0),
        CHECK((status = 'allowed' AND local_use = 1) OR
              (status != 'allowed' AND local_use = 0 AND redistribution = 0))
    )""",
    "CREATE INDEX source_review_latest ON source_permission_reviews(source_id, id DESC)",
    """CREATE TRIGGER source_review_no_update BEFORE UPDATE ON source_permission_reviews
        BEGIN SELECT RAISE(ABORT, 'Permission review history is append-only'); END""",
    """CREATE TRIGGER source_review_no_delete BEFORE DELETE ON source_permission_reviews
        BEGIN SELECT RAISE(ABORT, 'Permission review history is append-only'); END""",
)


def migrate_permissions(db):
    if db.in_transaction:
        raise ValueError('Migration requires an idle connection')
    db.execute('BEGIN IMMEDIATE')
    try:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version == 2:
            for statement in PERMISSION_SCHEMA:
                db.execute(statement)
            if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise ValueError('Existing database violates foreign keys')
            db.execute('PRAGMA user_version=3')
        elif version != VERSION:
            raise ValueError('Unsupported schema version; migration required')
        # Fail closed on a version marker without its required table.
        db.execute('SELECT id, source_id, status FROM source_permission_reviews LIMIT 0')
        db.commit()
    except BaseException:
        db.rollback()
        raise


def record_permission_review(db, source, *, status, local_use, redistribution,
                             reviewer, reviewed_on, evidence_ref, evidence_sha256,
                             source_version, scope):
    """Append an explicit human review; never call from an untrusted importer."""
    if status not in ('pending', 'allowed', 'restricted'):
        raise ValueError('Invalid permission status')
    if type(local_use) is not bool or type(redistribution) is not bool:
        raise ValueError('Permission scope flags must be boolean')
    if local_use != (status == 'allowed') or (redistribution and not local_use):
        raise ValueError('Permission scope contradicts status')
    if not all(isinstance(x, str) and x.strip() for x in
               (reviewer, reviewed_on, evidence_ref, evidence_sha256, source_version, scope)):
        raise ValueError('Complete review provenance required')
    if date.fromisoformat(reviewed_on).isoformat() != reviewed_on:
        raise ValueError('Review date must use YYYY-MM-DD')
    if re.fullmatch(r'[0-9a-f]{64}', evidence_sha256) is None:
        raise ValueError('Expected lowercase SHA-256 of permission evidence')
    with db:
        cursor = db.execute(
            'INSERT INTO source_permission_reviews(source_id,status,local_use,redistribution,'
            'reviewer,reviewed_on,evidence_ref,evidence_sha256,source_version,scope) '
            'VALUES (?,?,?,?,?,?,?,?,?,?)',
            (source, status, int(local_use), int(redistribution), reviewer, reviewed_on,
             evidence_ref, evidence_sha256, source_version, scope))
        return cursor.lastrowid


def source_permission(db, source):
    """Return the latest review or a fail-closed pending result for a known source."""
    if db.execute('SELECT 1 FROM sources WHERE id=?', (source,)).fetchone() is None:
        raise KeyError('Unknown source')
    cursor = db.execute(
        'SELECT id,status,local_use,redistribution,reviewer,reviewed_on,evidence_ref,'
        'evidence_sha256,source_version,scope FROM source_permission_reviews '
        'WHERE source_id=? ORDER BY id DESC LIMIT 1', (source,))
    row = cursor.fetchone()
    if row is None:
        return {'status': 'pending', 'local_use': False, 'redistribution': False, 'id': None}
    result = dict(zip((column[0] for column in cursor.description), row))
    result['local_use'] = bool(result['local_use'])
    result['redistribution'] = bool(result['redistribution'])
    return result
