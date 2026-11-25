"""Verified local SQLite snapshots, never overwriting an existing destination."""
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
from contextlib import closing

import strategic_store as store


def _readonly(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError('Expected a regular database file')
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    db.execute('PRAGMA trusted_schema=OFF')
    db.execute('PRAGMA query_only=ON')
    return db


def _schema(db):
    return db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
                      "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()


def audit(db):
    """Audit a committed v3 snapshot; reject structural and semantic corruption."""
    if db.execute('PRAGMA user_version').fetchone()[0] != store.VERSION:
        raise ValueError('Unsupported snapshot version')
    with closing(store.connect(':memory:')) as expected:
        if _schema(db) != _schema(expected):
            raise ValueError('Unexpected database schema')
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise ValueError('SQLite integrity check failed')
    if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise ValueError('Broken foreign key')
    counts = {}
    for name in ('sources', 'scenarios', 'records', 'source_permission_reviews'):
        counts[name] = db.execute('SELECT count(*) FROM ' + name).fetchone()[0]
    for key, name, license, evidence in db.execute('SELECT id,name,license,evidence FROM sources'):
        if not all(isinstance(x, str) and x.strip() for x in (name, license, evidence)) or key != store.digest([name, license, evidence]):
            raise ValueError('Invalid source identity or provenance')
    for key, variant, context in db.execute('SELECT id,variant,context FROM scenarios'):
        if (key, context) != store.scenario_identity(variant, json.loads(context)):
            raise ValueError('Invalid scenario identity')
    for key, source, scenario, payload, synthetic in db.execute('SELECT id,source_id,scenario_id,payload,synthetic FROM records'):
        actions = json.loads(payload)
        if (not isinstance(actions, dict) or not actions or
                any(a not in ('fold', 'check', 'call', 'bet', 'raise', 'all_in') or
                    type(p) not in (int, float) or not 0 <= p <= 1 for a, p in actions.items()) or
                not math.isclose(sum(actions.values()), 1, rel_tol=0, abs_tol=1e-6) or
                payload != store.canonical(actions) or synthetic != 1 or
                key != store.digest([source, scenario, payload, True])):
            raise ValueError('Invalid strategy record')
    return counts


def _sha256(path):
    with open(path, 'rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def _copy(source, destination, expected_sha256=None):
    destination = Path(destination)
    destination = destination.parent.resolve(strict=True) / destination.name
    if os.path.lexists(destination):
        raise FileExistsError(destination)
    fd, name = tempfile.mkstemp(prefix='.strategic-', suffix='.sqlite', dir=destination.parent)
    os.close(fd)
    stage = Path(name)
    try:
        with closing(_readonly(source)) as src:
            # A restore digest describes the input file, not a live WAL database.
            if expected_sha256 is not None:
                if any(Path(str(Path(source).resolve()) + suffix).exists() for suffix in ('-wal', '-journal')):
                    raise ValueError('Restore requires a standalone snapshot')
                if _sha256(source) != expected_sha256:
                    raise ValueError('Snapshot SHA-256 mismatch')
            with closing(sqlite3.connect(stage)) as dst:
                src.backup(dst)
                dst.execute('PRAGMA journal_mode=DELETE')
        with closing(_readonly(stage)) as check:
            counts = audit(check)
        digest = _sha256(stage)
        with stage.open('rb') as handle:
            os.fsync(handle.fileno())
        # Hard-link publication is atomic and fails if the destination exists.
        # Unsupported filesystems fail closed rather than overwrite anything.
        os.link(stage, destination)
        return {'path': str(destination), 'sha256': digest, 'counts': counts,
                'schema_version': store.VERSION}
    finally:
        stage.unlink(missing_ok=True)


def backup(source, destination):
    return _copy(source, destination)


def restore(source, destination, *, expected_sha256):
    if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64 or
            any(c not in '0123456789abcdef' for c in expected_sha256)):
        raise ValueError('Expected lowercase SHA-256 required')
    return _copy(source, destination, expected_sha256)
