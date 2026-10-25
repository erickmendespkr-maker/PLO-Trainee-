"""Read-only integrity audit for asynchronous, *unverified* PLO video evidence.

Checks the output of offline_worker without promoting OCR/frame hints into
confirmed hands or mathematical inputs. Never connects to poker platforms.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_FRAMES = 40000
MAX_IMAGE_BYTES = 30 * 1024 * 1024
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
JOB_ID = re.compile(r'^[0-9a-f]{32}$')
IMAGE_PATH = re.compile(r'^table_(0[1-4])/frame_[0-9]{5}\.png$')


def _hash_file(path, *, max_bytes=None):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing or symlinked evidence file')
    if max_bytes is not None and not 0 < path.stat().st_size <= max_bytes:
        raise ValueError('Evidence file exceeds allowed size')
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_JSON_BYTES:
        raise ValueError('Missing, symlinked, or oversized JSON')
    return json.loads(path.read_text(encoding='utf-8'),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON number')))


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def audit_job(store, job_id, results_root):
    """Return a provenance report; do not modify queue, files, or verdicts."""
    if type(job_id) is not str or not JOB_ID.fullmatch(job_id):
        raise ValueError('Invalid job ID')
    job = store.get(job_id)
    if job is None or job.get('job_id') != job_id or job.get('state') != 'review_required':
        raise ValueError('Job is not ready for human review')
    root = Path(results_root)
    if root.is_symlink():
        raise ValueError('Symlinked result root')
    directory = root / job_id
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Invalid job output directory')
    result_path = directory / 'result.json'
    if Path(job.get('result_path') or '').resolve() != result_path.resolve():
        raise ValueError('Queue result path does not match isolated job directory')
    result, manifest = _json(result_path), _json(directory / 'manifest.json')
    if (type(result) is not dict or result.get('schema_version') != 1 or
            result.get('job_id') != job_id or result.get('status') != 'review_required' or
            result.get('requires_manual_review') is not True or
            result.get('timestamp_semantics') != 'nominal_sampling_grid_not_exact_source_pts'):
        raise ValueError('Invalid worker result')
    if (type(manifest) is not dict or manifest.get('schema_version') != 1 or
            manifest.get('analysis_status') != 'unverified_visual_evidence_only' or
            manifest.get('requires_manual_review') is not True or
            manifest.get('timestamp_semantics') != 'nominal_sampling_grid_not_exact_source_pts'):
        raise ValueError('Invalid evidence manifest')
    source = Path(job['source_path'])
    source_hash = _hash_file(source)
    if source_hash != job['source_sha256']:
        raise ValueError('Recording SHA-256 changed since queue registration')
    metadata = job['video_metadata']
    if (type(metadata) is not dict or type(manifest.get('recording')) is not dict or
            manifest['recording'].get('filename') != source.name or
            any(manifest['recording'].get(key) != metadata.get(key)
                for key in ('size_bytes', 'duration_seconds', 'width', 'height'))):
        raise ValueError('Recording metadata differs from queue')
    if source.stat().st_size != metadata['size_bytes'] or not _number(metadata['duration_seconds']):
        raise ValueError('Invalid recording metadata')
    regions, frames = manifest.get('regions'), manifest.get('frames')
    if type(regions) is not list or not 1 <= len(regions) <= 4:
        raise ValueError('Invalid table regions')
    tables = set()
    for region in regions:
        if type(region) is not dict or type(region.get('table_id')) is not int or not 1 <= region['table_id'] <= 4:
            raise ValueError('Invalid table region')
        if region['table_id'] in tables:
            raise ValueError('Duplicate table region')
        tables.add(region['table_id'])
        for key in ('x', 'y', 'width', 'height'):
            if type(region.get(key)) is not int or region[key] < (1 if key in ('width', 'height') else 0):
                raise ValueError('Invalid region coordinates')
        if (region['x'] + region['width'] > metadata['width'] or
                region['y'] + region['height'] > metadata['height']):
            raise ValueError('Region outside recording')
    if (type(frames) is not list or not 1 <= len(frames) <= MAX_FRAMES or
            type(result.get('frame_count')) is not int or result['frame_count'] != len(frames) or
            result.get('table_count') != len(tables)):
        raise ValueError('Frame/table counts do not match')
    if not _number(manifest.get('interval_seconds')) or manifest['interval_seconds'] <= 0:
        raise ValueError('Invalid sampling interval')
    seen, counts, images = set(), {str(table): 0 for table in sorted(tables)}, []
    for frame in frames:
        if type(frame) is not dict or type(frame.get('table_id')) is not int or frame['table_id'] not in tables:
            raise ValueError('Frame refers to unknown table')
        relative = frame.get('image')
        match = IMAGE_PATH.fullmatch(relative) if type(relative) is str else None
        if not match or int(match.group(1)) != frame['table_id'] or relative in seen:
            raise ValueError('Invalid, repeated or cross-table image path')
        seen.add(relative)
        stamp = frame.get('nominal_timestamp_seconds')
        if (not _number(stamp) or stamp > metadata['duration_seconds'] + manifest['interval_seconds'] or
                frame.get('status') != 'unverified_visual_evidence'):
            raise ValueError('Invalid nominal frame timestamp or status')
        image_path = directory / relative
        if image_path.parent.is_symlink():
            raise ValueError('Symlinked table directory')
        if image_path.is_symlink() or not image_path.is_file():
            raise ValueError('Missing image')
        with image_path.open('rb') as handle:
            if handle.read(8) != PNG_SIGNATURE:
                raise ValueError('Invalid PNG signature')
        digest = _hash_file(image_path, max_bytes=MAX_IMAGE_BYTES)
        counts[str(frame['table_id'])] += 1
        images.append({'table_id': frame['table_id'], 'nominal_timestamp_seconds': stamp,
                       'image': relative, 'sha256': digest, 'verification': 'bytes_only_not_visual_truth'})
    template = result.get('review_template')
    if template is not None and template != 'review_template.json':
        raise ValueError('Unexpected review template name')
    template_sha = _hash_file(directory / template, max_bytes=MAX_JSON_BYTES) if template else None
    return {'schema_version': 1, 'analysis_status': 'audited_unverified_frames_human_review_required',
            'job_id': job_id, 'recording_sha256': source_hash,
            'worker_result_sha256': _hash_file(result_path, max_bytes=MAX_JSON_BYTES),
            'evidence_manifest_sha256': _hash_file(directory / 'manifest.json', max_bytes=MAX_JSON_BYTES),
            'review_template_sha256': template_sha, 'timestamp_semantics': manifest['timestamp_semantics'],
            'frame_count': len(images), 'table_frame_counts': counts, 'frames': images,
            'hand_reconstruction_verified': False, 'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False, 'requires_manual_review': True,
            'warning': 'Hashes verify file bytes, not OCR, source PTS, cards, actions, or hand boundaries.'}


def main(argv=None):
    from offline_jobs import OfflineJobStore
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database')
    parser.add_argument('job_id')
    parser.add_argument('results_root')
    parser.add_argument('--output', help='New JSON report path; never overwrite')
    args = parser.parse_args(argv)
    report = audit_job(OfflineJobStore(args.database), args.job_id, args.results_root)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if args.output:
        with Path(args.output).open('x', encoding='utf-8') as handle:
            handle.write(rendered)
    else:
        print(rendered, end='')


if __name__ == '__main__':
    main()
