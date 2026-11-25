"""Local strategic SQLite foundation. Only synthetic fixtures are writable in v2."""
import hashlib
import json
import math
import sqlite3

VERSION = 2
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
        elif version != VERSION:
            raise ValueError('Unsupported schema version; migration required')
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
    context = canonical(scenario)
    return digest([variant, context]), context


def add_record(db, source, variant, scenario, actions, *, synthetic):
    scenario_id, context = scenario_identity(variant, scenario)
    if synthetic is not True:
        raise ValueError('Real strategy writes disabled pending authorization workflow')
    if not isinstance(actions, dict) or not actions:
        raise ValueError('Invalid actions')
    for action, p in actions.items():
        if action not in ('fold', 'check', 'call', 'bet', 'raise', 'all_in') or type(p) not in (int, float) or not 0 <= p <= 1:
            raise ValueError('Invalid action or frequency')
    if not math.isclose(sum(actions.values()), 1, rel_tol=0, abs_tol=1e-6):
        raise ValueError('Frequencies must sum to one')
    payload = canonical(actions)
    key = digest([source, scenario_id, payload, True])
    with db:
        db.execute('INSERT INTO scenarios VALUES (?,?,?) ON CONFLICT(id) DO NOTHING', (scenario_id, variant, context))
        db.execute('INSERT INTO records VALUES (?,?,?,?,1) ON CONFLICT(id) DO NOTHING', (key, source, scenario_id, payload))
    return key


def lookup(db, variant, scenario, *, synthetic=False):
    scenario_id, _ = scenario_identity(variant, scenario)
    if type(synthetic) is not bool:
        raise ValueError('Invalid synthetic flag')
    return [(source, json.loads(payload)) for source, payload in db.execute(
        'SELECT source_id,payload FROM records WHERE scenario_id=? AND synthetic=? ORDER BY id',
        (scenario_id, int(synthetic)))]
