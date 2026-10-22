"""Read-only status reporting for the offline video analysis queue."""
import argparse
import json
import sqlite3
from offline_jobs import OfflineJobStore

PUBLIC_FIELDS = ('job_id','state','attempts','created_at','updated_at','error')

def status_report(database, *, job_id=None, limit=50):
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1 <= limit <= 500:
        raise ValueError('limit must be 1..500')
    store = OfflineJobStore(database)
    if job_id is not None:
        if not isinstance(job_id,str) or len(job_id) != 32 or any(c not in '0123456789abcdef' for c in job_id):
            raise ValueError('invalid job ID')
        job = store.get(job_id)
        return {'job': {k:job[k] for k in PUBLIC_FIELDS} if job else None}
    with sqlite3.connect(store.database_path) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute('SELECT job_id,state,attempts,created_at,updated_at,error FROM video_jobs ORDER BY created_at DESC,rowid DESC LIMIT ?', (limit,)).fetchall()
        counts = db.execute('SELECT state,COUNT(*) FROM video_jobs GROUP BY state').fetchall()
    return {'counts': {state:count for state,count in counts}, 'jobs':[dict(row) for row in rows]}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database')
    parser.add_argument('--job-id')
    parser.add_argument('--limit',type=int,default=50)
    args = parser.parse_args(argv)
    print(json.dumps(status_report(args.database,job_id=args.job_id,limit=args.limit),ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
