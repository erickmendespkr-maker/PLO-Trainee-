"""Post-export verification for offline, unreviewed clip batches."""
from pathlib import Path
try:
    from .offline_batch_execute import execute_review_batch
    from .offline_export_manifest_audit import audit_export
except ImportError:
    from offline_batch_execute import execute_review_batch
    from offline_export_manifest_audit import audit_export

def execute_and_audit(source, plan, source_duration, output_root, *,
                      exporter=None, auditor=None, ffprobe='ffprobe',
                      max_clips=200, max_total_seconds=1800, stop_on_error=True):
    """Check MP4/JSON postconditions; never assert poker conclusions."""
    result = execute_review_batch(source, plan, source_duration, output_root,
                                  exporter=exporter, max_clips=max_clips,
                                  max_total_seconds=max_total_seconds,
                                  stop_on_error=stop_on_error)
    checker = auditor if auditor is not None else audit_export
    audited = []
    for entry in result['results']:
        item = dict(entry)
        item.update(verified_artifacts=False, human_review_required=True,
                    strategic_verdict_allowed=False)
        if item['status'] == 'EXPORTED_UNREVIEWED':
            try:
                verification = (checker(Path(item['destination']), ffprobe=ffprobe)
                                if auditor is None else checker(Path(item['destination'])))
                if (verification.get('verified_artifacts') is not True
                    or verification.get('strategic_verdict_allowed') is not False
                    or verification.get('human_review_required') is not True):
                    raise ValueError('unsafe or incomplete audit')
                if (item.get('clip_sha256') is not None
                    and item['clip_sha256'] != verification.get('clip_sha256')):
                    raise ValueError('exporter and auditor hashes disagree')
                item.update(verified_artifacts=True,
                            clip_sha256=verification['clip_sha256'],
                            duration_seconds=verification['duration_seconds'],
                            status='ARTIFACTS_VERIFIED_UNREVIEWED')
            except Exception as exc:
                item.update(status='AUDIT_FAILED_UNREVIEWED',
                            error_type=type(exc).__name__, error=str(exc)[:300])
        audited.append(item)
    complete = (len(audited) > 0 and len(audited) == result['planned_count']
                and all(x['verified_artifacts'] for x in audited))
    return {**result, 'results': audited,
            'status': ('ARTIFACTS_VERIFIED_UNREVIEWED' if complete else 'PARTIAL_OR_FAILED'),
            'verified_count': sum(x['verified_artifacts'] for x in audited),
            'human_review_required': True, 'gto_solution': False}
