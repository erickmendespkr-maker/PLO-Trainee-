"""Run a bounded batch of queued offline video jobs, then exit."""
import argparse
import json
from offline_jobs import OfflineJobStore
from offline_worker import process_next

def process_batch(store, output_root, *, max_jobs=10, **worker_options):
    if isinstance(max_jobs, bool) or not isinstance(max_jobs, int) or not 1 <= max_jobs <= 100:
        raise ValueError('max_jobs must be an integer from 1 to 100')
    outcomes = []
    for _ in range(max_jobs):
        result = process_next(store, output_root, **worker_options)
        if result is None:
            break
        outcomes.append({'job_id': result['job_id'], 'state': result['state'],
                         'error': result['error']})
    return {'processed': len(outcomes),
            'review_required': sum(x['state'] == 'review_required' for x in outcomes),
            'failed': sum(x['state'] == 'failed' for x in outcomes), 'jobs': outcomes}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database')
    parser.add_argument('output_root')
    parser.add_argument('--max-jobs', type=int, default=10)
    parser.add_argument('--interval', type=float, default=30)
    parser.add_argument('--max-frames', type=int, default=150)
    parser.add_argument('--roi-manifest')
    parser.add_argument('--max-ocr-tasks', type=int, default=4000)
    args = parser.parse_args(argv)
    summary = process_batch(OfflineJobStore(args.database), args.output_root,
                            max_jobs=args.max_jobs, interval_seconds=args.interval,
                            max_frames_per_table=args.max_frames,
                            roi_manifest=args.roi_manifest, max_ocr_tasks=args.max_ocr_tasks)
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if summary['failed'] else 0

if __name__ == '__main__':
    raise SystemExit(main())
