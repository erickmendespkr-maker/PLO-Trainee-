"""Offline one-job worker; all extracted evidence requires human review."""
import hashlib
import json
from pathlib import Path
from evidence_sampler import export_evidence
from evidence_ocr import scan_evidence
from offline_jobs import OfflineJobStore

def process_next(store: OfflineJobStore, output_root, *, interval_seconds=30, max_frames_per_table=150, roi_manifest=None, max_ocr_tasks=4000):
    job = store.claim_next()
    if job is None:
        return None
    job_id = job['job_id']
    try:
        source = Path(job['source_path'])
        digest = hashlib.sha256()
        with source.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != job['source_sha256']:
            raise ValueError('Recording content changed since registration')
        destination = Path(output_root) / job_id
        report = export_evidence(source, destination, interval_seconds=interval_seconds,
                                 max_frames_per_table=max_frames_per_table)
        if not report['requires_manual_review']:
            raise RuntimeError('Evidence export did not request review')
        result_path = destination / 'manifest.json'
        if roi_manifest is not None:
            ocr_path = destination / 'ocr_candidates.json'
            ocr_report = scan_evidence(destination, roi_manifest, ocr_path,
                                       max_tasks=max_ocr_tasks)
            if not ocr_report.get('requires_manual_review') or ocr_report.get('analysis_status') != 'unverified_ocr_candidates_only':
                raise RuntimeError('OCR output did not require review')
            result_path = ocr_path
        store.transition(job_id, 'review_required', result_path=str(result_path))
    except Exception as exc:
        store.transition(job_id, 'failed', error=f'{type(exc).__name__}: {exc}'[:1000])
    return store.get(job_id)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database')
    parser.add_argument('output_root')
    parser.add_argument('--interval', type=float, default=30)
    parser.add_argument('--max-frames', type=int, default=150)
    parser.add_argument('--roi-manifest', help='Optional local JSON file with manual table ROIs')
    parser.add_argument('--max-ocr-tasks', type=int, default=4000)
    args = parser.parse_args()
    result = process_next(OfflineJobStore(args.database), args.output_root,
                          interval_seconds=args.interval, max_frames_per_table=args.max_frames,
                          roi_manifest=args.roi_manifest, max_ocr_tasks=args.max_ocr_tasks)
    print(json.dumps({'job_id': result['job_id'], 'state': result['state'],
                      'result_path': result['result_path'], 'error': result['error']} if result else {'state': 'empty'}))
