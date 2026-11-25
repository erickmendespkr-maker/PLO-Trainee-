"""PLO5 recorded-session evidence coverage; never certify recognition or hands."""
import argparse
from collections import Counter
import json
from pathlib import Path
import time

from local_ingest import ingest_local
from offline_jobs import OfflineJobStore
from offline_ingest_pts_audit import read_manifest
from offline_video_ingest_probe import sample_times
from plo5_ingest_job import run_job, read_bound_evidence
from plo5_ground_truth import template
from plo5_leak_review import need
from plo5_session_export import write


def summarize(database, job_id, interval):
    binding=read_bound_evidence(database,job_id)
    job=OfflineJobStore(database).get(job_id);root=Path(job['result_path']).parent
    m=read_manifest(root/'evidence/ingest/manifest.json')
    pts=json.loads((root/'evidence/pts_audit.json').read_text('utf-8'))
    pixels=json.loads((root/'evidence/pixel_spotcheck.json').read_text('utf-8'))
    media=m['media'];times=sample_times(media['duration_seconds'],media['frame_rate_reported'],interval)
    tables={r['table_id'] for r in m['regions']}
    expected={(t,s) for t in tables for s in times}
    actual={(s['table_id'],s['timestamp_seconds']) for s in m['samples']}
    need(actual==expected and len(m['samples'])==len(expected),'Incomplete requested sample schedule')
    names={s['file'] for s in m['samples']}
    audited=pts['verified_samples'];checked=pixels['results']
    need(len(audited)==len(names)==binding['crops_pts_hash_audited'] and {s['file'] for s in audited}==names and all(s['crop_sha256_verified'] is True for s in audited),'Incomplete timestamp/hash audit')
    need(len(checked)==binding['crops_pixel_checked'] and len({s['file'] for s in checked})==len(checked) and all(s['file'] in names and s['visual_roi_match_within_tolerance'] is True for s in checked),'Incomplete pixel audit')
    need(pts['source_sha256']==pixels['source_sha256']==binding['source_sha256'],'Audit source mismatch')
    report={'variant':5,'status':'RECORDED_MEDIA_EVIDENCE_ONLY','job_id':job_id,
            'source_sha256':binding['source_sha256'],'media':media,'table_regions_declared':len(tables),
            'source_decoded_frames':pts['source_decoded_frame_count'],'vfr_observed':pts['variable_frame_intervals_observed'],
            'interval_seconds':interval,'scheduled_samples':len(expected),'samples_pts_hash_audited':len(audited),
            'samples_by_table':dict(sorted(Counter(s['table_id'] for s in m['samples']).items())),
            'pixel_spotchecks':len(checked),'max_pixel_mae_rgb':max(s['mean_abs_rgb_error'] for s in checked),
            'max_requested_pts_delta_seconds':pts['max_abs_requested_to_decoded_delta_seconds'],
            'source_bytes':m['source_size_bytes'],'evidence_bytes':sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),
            'real_session_validated':False,'complete_hands_verified':False,'ocr_verified':False,
            'gto_solution':False,'automatic_clip_selection_authorized':False}
    return report,template(binding,m)


def run(recording, regions, output, *, interval=120, pixel_checks=8):
    out=Path(output);need(out.parent.is_dir() and not out.exists() and not out.is_symlink(),'New output directory required');out.mkdir(mode=0o700)
    db=out/'jobs.db';start=time.perf_counter()
    j=ingest_local(recording,out/'uploads',db);queued=time.perf_counter()
    run_job(db,j['job_id'],regions,out/'evidence',interval=interval,pixel_checks=pixel_checks);audited=time.perf_counter()
    report,annotations=summarize(db,j['job_id'],interval)
    report['queue_wall_seconds']=queued-start;report['ingest_audit_wall_seconds']=audited-queued
    report['total_wall_seconds']=time.perf_counter()-start
    write(out/'annotations.json',annotations);write(out/'media_audit.json',report);return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('recording');p.add_argument('regions');p.add_argument('output');p.add_argument('--interval',type=float,default=120);p.add_argument('--pixel-checks',type=int,default=8);a=p.parse_args(argv)
    print(json.dumps(run(a.recording,a.regions,a.output,interval=a.interval,pixel_checks=a.pixel_checks)),flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
