"""Audit offline_review_clip_export artifacts; never infer poker decisions."""
import hashlib
import json
import math
from pathlib import Path
import subprocess

def _hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def _unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate manifest key')
        obj[key] = value
    return obj

def audit_review_export(clip, *, source=None, ffprobe='ffprobe', timeout=30):
    """Fail closed on missing/altered artifacts; never validate strategic claims."""
    clip = Path(clip)
    manifest_path = clip.with_suffix('.json')
    if clip.suffix.lower() != '.mp4':
        raise ValueError('expected MP4')
    for path in (clip, manifest_path):
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ValueError('missing or unsafe artifact')
    if manifest_path.stat().st_size > 65536:
        raise ValueError('manifest too large')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'), object_pairs_hook=_unique,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    if not isinstance(manifest, dict) or type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1:
        raise ValueError('unsupported manifest schema')
    if manifest.get('clip_sha256') != _hash(clip):
        raise ValueError('clip checksum mismatch')
    if manifest.get('ev_is_conditional') is not True or manifest.get('gto_solution') is not False or manifest.get('human_review_of_export') is not False:
        raise ValueError('invalid evidence disclaimers')
    gate = manifest.get('evidence_gate')
    if not isinstance(gate, dict) or gate.get('can_label_error') is not False:
        raise ValueError('invalid evidence gate')
    if type(gate.get('table_id')) is not int or gate['table_id'] not in (1, 2, 3, 4) or manifest.get('table_id') != gate['table_id']:
        raise ValueError('table mismatch')
    status = gate.get('status')
    allowed = {'REVIEW_REQUIRED', 'INSUFFICIENT_MODEL', 'APPROVED_CONDITIONAL'}
    if status not in allowed:
        raise ValueError('invalid evidence status')
    missing = gate.get('missing_evidence')
    if not isinstance(missing, list) or any(not isinstance(x, str) or not x for x in missing):
        raise ValueError('invalid missing evidence')
    approved = status == 'APPROVED_CONDITIONAL'
    if gate.get('can_attach_conditional_ev') is not approved:
        raise ValueError('conditional EV flag contradicts evidence status')
    if (approved and missing) or (not approved and not missing):
        raise ValueError('evidence status contradicts missing fields')
    interval = manifest.get('requested_interval_seconds')
    duration = manifest.get('source_duration_seconds')
    if not isinstance(interval, list) or len(interval) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in interval):
        raise ValueError('invalid interval')
    start, end = interval
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 <= start < end <= duration + .001:
        raise ValueError('invalid source duration')
    if gate.get('start_pts') != start or gate.get('end_pts') != end:
        raise ValueError('gate interval mismatch')
    if source is not None:
        source = Path(source)
        if source.is_symlink() or not source.is_file() or manifest.get('source_sha256') != _hash(source):
            raise ValueError('source checksum mismatch')
    proc = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration:stream=codec_type',
                           '-of', 'json', str(clip)], capture_output=True, text=True,
                          check=True, timeout=timeout)
    probe = json.loads(proc.stdout)
    if not any(s.get('codec_type') == 'video' for s in probe.get('streams', [])):
        raise ValueError('video stream missing')
    clip_duration = float(probe['format']['duration'])
    if (not math.isfinite(clip_duration) or
            not max(0.0, end - start - .25) < clip_duration <= end - start + .25):
        raise ValueError('clip duration mismatch')
    return {'integrity_verified': True, 'source_checked': source is not None,
            'clip_sha256': manifest['clip_sha256'], 'clip_duration_seconds': clip_duration,
            'hand_verified': False, 'strategic_analysis_verified': False}
