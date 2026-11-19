"""Validate and persist unverified offline review ledgers without overwriting files."""
import json
import math
import os
import tempfile
from pathlib import Path

REQUIRED = {'proposal_id', 'video_sha256', 'table_id', 'start_observed_seconds', 'end_observed_seconds', 'review_status', 'hand_verified', 'clip_export_allowed', 'loss_bb', 'equity', 'ev'}

def validate_ledger(ledger):
    if not isinstance(ledger, dict) or ledger.get('schema_version') != 1:
        raise ValueError('unsupported ledger schema')
    sha = ledger.get('video_sha256')
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('invalid video SHA256')
    duration = ledger.get('duration_seconds')
    if type(duration) not in (int, float) or not (0 < duration < float('inf')):
        raise ValueError('invalid duration')
    if ledger.get('confirmed_hands') != 0 or ledger.get('strategy_verified') is not False:
        raise ValueError('unexpected verification promotion')
    entries = ledger.get('entries')
    if not isinstance(entries, list):
        raise ValueError('entries must be a list')
    seen = set()
    for e in entries:
        if not isinstance(e, dict) or not REQUIRED.issubset(e):
            raise ValueError('invalid entry')
        pid = e['proposal_id']
        if not isinstance(pid, str) or not pid or pid in seen:
            raise ValueError('duplicate or invalid proposal ID')
        seen.add(pid)
        if e['video_sha256'] != sha or type(e['table_id']) is not int or not 1 <= e['table_id'] <= 4:
            raise ValueError('invalid provenance or table')
        a, b = e['start_observed_seconds'], e['end_observed_seconds']
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in (a, b)) or not (0 <= a < b <= duration):
            raise ValueError('invalid timestamps')
        if (e['review_status'] != 'pending_human_review' or e['hand_verified'] is not False
                or e['clip_export_allowed'] is not False or any(e[k] is not None for k in ('loss_bb', 'equity', 'ev'))):
            raise ValueError('unverified proposal promoted')
    return True

def save_ledger(ledger, destination):
    """Write atomically and refuse existing paths, including symlinks."""
    validate_ledger(ledger)
    dest = Path(destination)
    if not dest.parent.is_dir() or dest.exists() or dest.is_symlink():
        raise FileExistsError('destination unavailable')
    payload = (json.dumps(ledger, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')
    fd, tmp = tempfile.mkstemp(prefix='.ledger-', suffix='.tmp', dir=dest.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.link(tmp, dest)
    finally:
        os.unlink(tmp)
    return dest

def load_ledger(source):
    with open(source, 'r', encoding='utf-8') as f:
        data = json.load(f)
    validate_ledger(data)
    return data
