"""Audit hashes, timing and conservative labels for offline exported MP4 clips."""
import hashlib
import json
import math
from pathlib import Path

class ManifestAuditError(ValueError):
    pass

def _sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def audit_clip_manifest(source, clip, manifest_path):
    source, clip, manifest_path = map(Path, (source, clip, manifest_path))
    if not all(p.is_file() for p in (source, clip, manifest_path)):
        raise ManifestAuditError('missing artifact')
    if source.resolve() == clip.resolve():
        raise ManifestAuditError('source equals clip')
    try:
        m = json.loads(manifest_path.read_text(encoding='utf-8'),
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
    except (ValueError, UnicodeError) as exc:
        raise ManifestAuditError('invalid manifest') from exc
    if not isinstance(m, dict) or type(m.get('schema_version')) is not int or m['schema_version'] != 1:
        raise ManifestAuditError('unsupported schema')
    if m.get('source_sha256') != _sha(source) or m.get('clip_sha256') != _sha(clip):
        raise ManifestAuditError('digest mismatch')
    interval, duration = m.get('requested_interval_seconds'), m.get('source_duration_seconds')
    if (not isinstance(interval, list) or len(interval) != 2 or
        any(type(x) not in (int, float) or not math.isfinite(x) for x in interval) or
        type(duration) not in (int, float) or not math.isfinite(duration) or
        not 0 <= interval[0] < interval[1] <= duration + 0.001):
        raise ManifestAuditError('invalid interval')
    table = m.get('table_id')
    if type(table) is not int or not 1 <= table <= 4:
        raise ManifestAuditError('invalid table')
    gate = m.get('evidence_gate')
    if not isinstance(gate, dict) or gate.get('table_id') != table or gate.get('start_pts') != interval[0] or gate.get('end_pts') != interval[1]:
        raise ManifestAuditError('gate mismatch')
    if m.get('ev_is_conditional') is not True or m.get('gto_solution') is not False or m.get('human_review_of_export') is not False:
        raise ManifestAuditError('unverified claim')
    return {'status': 'INTEGRITY_VERIFIED_ONLY', 'source_sha256': m['source_sha256'],
            'clip_sha256': m['clip_sha256'], 'table_id': table,
            'requested_interval_seconds': interval, 'hand_verified': False,
            'financial_result_verified': False, 'ev_verified': False}
