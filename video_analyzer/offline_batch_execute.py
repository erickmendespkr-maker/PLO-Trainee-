"""Sequential offline clip batch executor; never interprets poker decisions.

Only provisional plans are accepted. A per-destination exclusive lock protects
cooperating workers; existing exporter still needs atomic no-clobber publishing
for protection from unrelated writers. Partial successes are reported explicitly.
"""
import os
from pathlib import Path

try:
    from .offline_batch_ready import prepare_batch
    from .offline_review_clip_export import export_review_clip
except ImportError:
    from offline_batch_ready import prepare_batch
    from offline_review_clip_export import export_review_clip


def execute_review_batch(source, plan, source_duration, output_root, *, exporter=None,
                         max_clips=200, max_total_seconds=1800, stop_on_error=True):
    """Export checked intervals sequentially, retaining failures for inspection.

    The output directory must exist. The source is never modified. The caller
    owns cleanup of successful clips if a later clip fails.
    """
    if type(stop_on_error) is not bool:
        raise ValueError('stop_on_error must be bool')
    src = Path(source)
    if not src.is_file() or not src.stat().st_size:
        raise ValueError('source missing or empty')
    ready = prepare_batch(plan, source_duration, output_root,
                          max_clips=max_clips, max_total_seconds=max_total_seconds)
    writer = exporter if exporter is not None else export_review_clip
    results = []
    for index, (checked, original) in enumerate(zip(ready['clips'], plan)):
        destination = Path(checked['destination'])
        lock = destination.with_suffix('.mp4.lock')
        fd = None
        owned = False
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            fd = None
            owned = True
            if destination.exists() or destination.with_suffix('.json').exists():
                raise FileExistsError('destination appeared after preflight')
            manifest = writer(src, destination, original['record'])
            if not destination.is_file() or not destination.with_suffix('.json').is_file():
                raise RuntimeError('exporter returned without both artifacts')
            results.append({'index': index, 'destination': str(destination),
                            'status': 'EXPORTED_UNREVIEWED',
                            'clip_sha256': manifest.get('clip_sha256') if isinstance(manifest, dict) else None})
        except Exception as exc:
            results.append({'index': index, 'destination': str(destination),
                            'status': 'FAILED', 'error_type': type(exc).__name__,
                            'error': str(exc)[:300]})
            if stop_on_error:
                break
        finally:
            if fd is not None:
                os.close(fd)
            if owned:
                lock.unlink(missing_ok=True)
    return {'status': 'PARTIAL_OR_FAILED' if any(r['status'] == 'FAILED' for r in results)
            else 'EXPORTED_UNREVIEWED', 'results': results,
            'planned_count': len(plan), 'attempted_count': len(results),
            'human_review_required': True, 'gto_solution': False}
