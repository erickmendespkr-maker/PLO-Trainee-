"""Bind the existing audited offline MP4 evidence pipeline to a specific PLO5 job."""
import argparse
import json
import os
from pathlib import Path
import re
import tempfile

from local_ingest import ingest_local
from offline_jobs import OfflineJobStore
from offline_ingest_audited_pipeline import run as audit_pipeline, write_json
from offline_video_ingest_probe import sha256, require
from offline_ingest_pts_audit import read_manifest, NAME

REPORTS = ('evidence/chain_report.json', 'evidence/ingest/manifest.json',
           'evidence/pts_audit.json', 'evidence/pixel_spotcheck.json', 'regions.json')


def run_job(database, job_id, regions, output_root, *, interval=30., pixel_checks=32):
    """Claim a queued job and publish private evidence, not a poker analysis."""
    require(type(job_id) is str and re.fullmatch(r'[0-9a-f]{32}', job_id), 'Invalid job ID')
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(root.is_dir() and not root.is_symlink(), 'Unsafe output root')
    root = root.resolve()
    final = root / job_id
    require(not final.exists() and not final.is_symlink(), 'Job evidence already exists')
    store = OfflineJobStore(database)
    job = store.claim_job(job_id)
    require(job is not None, 'Job is not queued')
    try:
        source, config = Path(job['source_path']), Path(regions)
        require(source.suffix.lower() == '.mp4' and source.is_file() and not source.is_symlink(), 'PLO5 jobs require a local MP4')
        require(sha256(source) == job['source_sha256'], 'Recording differs from queued SHA-256')
        require(config.is_file() and not config.is_symlink() and 0 < config.stat().st_size <= 8192, 'Invalid region configuration')
        with tempfile.TemporaryDirectory(prefix='.plo5-job-', dir=root) as temporary:
            stage = Path(temporary)
            snapshot = stage / 'regions.json'
            snapshot.write_bytes(config.read_bytes())
            evidence = stage / 'evidence'
            summary = audit_pipeline(source, snapshot, evidence, interval, pixel_checks)
            manifest = read_manifest(evidence / 'ingest/manifest.json')
            require(summary['source_sha256'] == manifest['source_sha256'] == job['source_sha256'] == sha256(source), 'Evidence source mismatch')
            require(manifest['regions_config_sha256'] == sha256(snapshot), 'Evidence configuration mismatch')
            require(summary['total_crops_pts_hash_audited'] == len(manifest['samples']), 'Incomplete crop audit')
            binding = {'schema_version': 1, 'job_id': job_id, 'attempt': job['attempts'],
                       'variant': 5, 'source_sha256': job['source_sha256'],
                       'status': 'review_required', 'reports': {name: sha256(stage / name) for name in REPORTS},
                       'crops_pts_hash_audited': summary['total_crops_pts_hash_audited'],
                       'crops_pixel_checked': summary['crops_pixel_checked'],
                       'ocr_verified': False, 'hands_reconstructed': False, 'equity_ev_authorized': False}
            write_json(stage / 'job_binding.json', binding)
            require(not final.exists() and not final.is_symlink(), 'Job output appeared during processing')
            os.rename(stage, final)
        return store.transition(job_id, 'review_required', result_path=str(final / 'job_binding.json'))
    except Exception as exc:
        # Never delete a published bundle: a DB error after rename needs reconciliation.
        store.transition(job_id, 'failed', error=f'{type(exc).__name__}: {exc}'[:1000])
        raise


def read_bound_evidence(database, job_id):
    """Recheck the job identity, source, reports and crop hashes before handoff."""
    job = OfflineJobStore(database).get(job_id)
    require(job is not None and job['state'] == 'review_required' and job['result_path'], 'No reviewable evidence')
    path = Path(job['result_path'])
    require(path.name == 'job_binding.json' and path.parent.name == job_id and
            path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= 16384, 'Invalid binding path')
    binding = json.loads(path.read_text('utf-8'))
    require(binding['job_id'] == job_id and binding['attempt'] == job['attempts'] and binding['variant'] == 5 and binding['status'] == 'review_required' and binding['source_sha256'] == job['source_sha256'] == sha256(job['source_path']), 'Job binding mismatch')
    require(all(binding[k] is False for k in ('ocr_verified', 'hands_reconstructed', 'equity_ev_authorized')), 'Unverified evidence cannot authorize analysis')
    require(set(binding['reports']) == set(REPORTS), 'Incomplete evidence reports')
    for name, digest in binding['reports'].items():
        report = path.parent / name
        require(report.is_file() and not report.is_symlink() and sha256(report) == digest, 'Evidence report mismatch')
    folder = path.parent / 'evidence/ingest'
    manifest = read_manifest(folder / 'manifest.json')
    require(manifest['source_sha256'] == job['source_sha256'] and manifest['regions_config_sha256'] == sha256(path.parent / 'regions.json') and len(manifest['samples']) == binding['crops_pts_hash_audited'], 'Manifest binding mismatch')
    for sample in manifest['samples']:
        require(NAME.fullmatch(sample['file']), 'Unsafe crop name')
        crop = folder / sample['file']
        require(crop.is_file() and not crop.is_symlink() and sha256(crop) == sample['sha256'], 'Evidence crop mismatch')
    return binding


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording')
    parser.add_argument('regions_json')
    parser.add_argument('storage_dir')
    parser.add_argument('database')
    parser.add_argument('output_root')
    parser.add_argument('--interval', type=float, default=30.)
    parser.add_argument('--pixel-checks', type=int, default=32)
    args = parser.parse_args(argv)
    require(Path(args.recording).suffix.lower() == '.mp4', 'PLO5 jobs require MP4')
    queued = ingest_local(args.recording, args.storage_dir, args.database)
    job = run_job(args.database, queued['job_id'], args.regions_json, args.output_root,
                  interval=args.interval, pixel_checks=args.pixel_checks)
    print(json.dumps({'job_id': job['job_id'], 'state': job['state'], 'result_path': job['result_path']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
