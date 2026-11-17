"""Conservative review journal for offline PTS evidence. Never authorizes strategic commentary."""
import hashlib
import json
import math

def create_review_journal(handoff, decisions=()):
    if not isinstance(handoff, dict) or handoff.get('source') != 'offline_recorded_video':
        raise ValueError('invalid recorded-video handoff')
    video_hash = handoff.get('video_sha256')
    if not isinstance(video_hash, str) or len(video_hash) != 64 or any(c not in '0123456789abcdef' for c in video_hash):
        raise ValueError('invalid video hash')
    tasks = handoff.get('tasks')
    if not isinstance(tasks, list) or not isinstance(decisions, (list, tuple)):
        raise ValueError('invalid tasks or decisions')
    by_id = {}
    for task in tasks:
        if not isinstance(task, dict) or task.get('review_status') != 'PENDING' or task.get('strategic_commentary_allowed') is not False:
            raise ValueError('untrusted task')
        rid = task.get('review_id')
        if not isinstance(rid, str) or len(rid) != 64 or any(c not in '0123456789abcdef' for c in rid) or rid in by_id:
            raise ValueError('invalid or duplicate review id')
        evidence = task.get('evidence')
        if not isinstance(evidence, dict):
            raise ValueError('missing evidence')
        lo, hi = evidence.get('earliest_pts'), evidence.get('latest_pts')
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (lo, hi)) or not 0 <= lo <= hi:
            raise ValueError('invalid timestamps')
        by_id[rid] = task
    applied = {}
    for decision in decisions:
        if not isinstance(decision, dict) or set(decision) - {'review_id', 'status', 'reviewer_note'}:
            raise ValueError('invalid decision')
        rid, status, note = (decision.get(k) for k in ('review_id', 'status', 'reviewer_note'))
        if rid not in by_id or rid in applied or status not in {'PENDING', 'NEEDS_CORRECTION', 'REJECTED', 'REVIEWED'} or not isinstance(note, str) or len(note) > 2000:
            raise ValueError('invalid review')
        if status == 'REVIEWED' and not note.strip():
            raise ValueError('review note required')
        applied[rid] = {'status': status, 'reviewer_note': note}
    entries = [{'review_id': rid, 'evidence': by_id[rid]['evidence'],
                'decision': applied.get(rid, {'status': 'PENDING', 'reviewer_note': ''}),
                'strategic_commentary_allowed': False, 'equity_or_ev_computed': False}
               for rid in sorted(by_id)]
    result = {'schema_version': 1, 'source': 'offline_recorded_video',
              'video_sha256': video_hash, 'entries': entries,
              'requires_separate_strategic_evidence_validation': True}
    canonical = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False)
    result['journal_sha256'] = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return result
