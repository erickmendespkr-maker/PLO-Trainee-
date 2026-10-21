"""Local SQLite queue for recorded video analysis only."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid
from video_validator import validate_recording

@contextmanager
def _connect(path):
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()

class OfflineJobStore:
    def __init__(self, database_path):
        self.database_path = str(Path(database_path).resolve())
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with _connect(self.database_path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS video_jobs (
                job_id TEXT PRIMARY KEY, source_path TEXT NOT NULL,
                source_sha256 TEXT NOT NULL, video_metadata_json TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN
                ('queued','running','review_required','completed','failed')),
                attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, result_path TEXT, error TEXT)""")
            db.execute('CREATE INDEX IF NOT EXISTS idx_jobs_queue ON video_jobs(state,created_at)')

    @staticmethod
    def _utc():
        return datetime.now(timezone.utc).isoformat()

    def enqueue(self, recorded_video):
        source = Path(recorded_video).resolve(strict=True)
        metadata = validate_recording(source)
        digest = hashlib.sha256()
        with source.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        if source.stat().st_size != metadata['size_bytes']:
            raise ValueError('Recording changed during registration')
        job_id, now = uuid.uuid4().hex, self._utc()
        with _connect(self.database_path) as db:
            db.execute("""INSERT INTO video_jobs
              (job_id,source_path,source_sha256,video_metadata_json,state,created_at,updated_at)
              VALUES (?,?,?,?,?,?,?)""",
              (job_id, str(source), digest.hexdigest(), json.dumps(metadata), 'queued', now, now))
        return self.get(job_id)

    def get(self, job_id):
        with _connect(self.database_path) as db:
            row = db.execute('SELECT * FROM video_jobs WHERE job_id=?', (job_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result['video_metadata'] = json.loads(result.pop('video_metadata_json'))
        return result

    def claim_next(self):
        with _connect(self.database_path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("""SELECT job_id FROM video_jobs WHERE state='queued'
                              ORDER BY created_at,rowid LIMIT 1""").fetchone()
            if row is None:
                db.execute('COMMIT')
                return None
            job_id = row['job_id']
            db.execute("""UPDATE video_jobs SET state='running',attempts=attempts+1,
                          updated_at=? WHERE job_id=?""", (self._utc(), job_id))
            db.execute('COMMIT')
        return self.get(job_id)

    def transition(self, job_id, state, *, result_path=None, error=None):
        transitions = {'running': {'review_required','completed','failed'},
                       'review_required': {'completed','failed'}}
        with _connect(self.database_path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT state FROM video_jobs WHERE job_id=?', (job_id,)).fetchone()
            if row is None:
                db.execute('ROLLBACK')
                raise KeyError('Unknown job')
            if state not in transitions.get(row['state'], set()):
                db.execute('ROLLBACK')
                raise ValueError('Invalid job state transition')
            if state == 'failed' and (not isinstance(error,str) or not error.strip()):
                db.execute('ROLLBACK')
                raise ValueError('Failure requires an error description')
            if state == 'completed' and (not isinstance(result_path,str) or not result_path.strip()):
                db.execute('ROLLBACK')
                raise ValueError('Completion requires a result path')
            db.execute('UPDATE video_jobs SET state=?,result_path=?,error=?,updated_at=? WHERE job_id=?',
                       (state,result_path,error,self._utc(),job_id))
            db.execute('COMMIT')
        return self.get(job_id)
