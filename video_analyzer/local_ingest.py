"""Copy a validated local recording into private storage and enqueue it (not HTTP upload)."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid
from offline_jobs import OfflineJobStore
from video_validator import validate_recording

def ingest_local(source_path, storage_dir, database_path):
    source = Path(source_path).resolve(strict=True)
    metadata = validate_recording(source)
    storage = Path(storage_dir).resolve()
    storage.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(storage, 0o700)
    if source.parent == storage:
        raise ValueError('Source is already in managed storage')
    final = storage / (uuid.uuid4().hex + source.suffix.lower())
    fd, temporary = tempfile.mkstemp(prefix='.ingest-', suffix=source.suffix.lower(), dir=storage)
    try:
        with os.fdopen(fd, 'wb') as output, source.open('rb') as input_file:
            shutil.copyfileobj(input_file, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        if Path(temporary).stat().st_size != metadata['size_bytes']:
            raise ValueError('Recording changed while copying')
        validate_recording(temporary)
        os.chmod(temporary, 0o600)
        os.replace(temporary, final)
        try:
            return OfflineJobStore(database_path).enqueue(final)
        except Exception:
            final.unlink(missing_ok=True)
            raise
    finally:
        Path(temporary).unlink(missing_ok=True)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('storage_dir')
    parser.add_argument('database')
    args = parser.parse_args(argv)
    job = ingest_local(args.source, args.storage_dir, args.database)
    print(json.dumps({'job_id': job['job_id'], 'state': job['state']}))

if __name__ == '__main__':
    main()
