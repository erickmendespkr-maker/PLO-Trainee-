"""Offline-only bridge: visual proposals -> validated pending-review ledger.

Does not infer confirmed hands or strategic results.
"""
import hashlib
from pathlib import Path
from offline_proposal_review_ledger import build_review_ledger
from offline_review_ledger_io import validate_ledger, save_ledger, load_ledger

def sha256_file(path, chunk_size=1024 * 1024):
    if type(chunk_size) is not int or chunk_size <= 0:
        raise ValueError('invalid chunk size')
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        while True:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()

def persist_proposals(proposal_result, *, video_path, duration_seconds, destination):
    """Bind proposals to local video bytes and save without overwriting.

    Duration must be independently measured; no media probing or hand recognition.
    """
    video = Path(video_path)
    if not video.is_file():
        raise FileNotFoundError(video)
    sha = sha256_file(video)
    ledger = build_review_ledger(proposal_result, video_sha256=sha,
                                 duration_seconds=duration_seconds)
    validate_ledger(ledger)
    saved = save_ledger(ledger, destination)
    recovered = load_ledger(saved)
    if recovered != ledger:
        raise RuntimeError('persisted ledger verification failed')
    return {'ledger_path': str(saved), 'video_sha256': sha,
            'proposal_count': len(recovered['entries']),
            'confirmed_hands': 0, 'strategy_verified': False}
