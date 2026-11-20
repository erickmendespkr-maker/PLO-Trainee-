"""Bridge imported Poker Cortes CSV candidates to multitable OCR evidence routing.

All outputs remain review-only; source row identifies each hand proposal.
"""
import hashlib
import json
from pathlib import Path

try:
    from .poker_cortes_review_import import import_report
    from .poker_cortes_multitable_gate import route_evidence
except ImportError:
    from poker_cortes_review_import import import_report
    from poker_cortes_multitable_gate import route_evidence


def build_evidence_review(csv_path, observations, *, video_sha256, duration_seconds, max_tables=4):
    candidates = import_report(csv_path, video_sha256=video_sha256,
                               duration_seconds=duration_seconds, max_tables=max_tables)
    hands = []
    for candidate in candidates:
        item = dict(candidate)
        item['hand_id'] = f"csv-row-{item['source_row']}"
        hands.append(item)
    routed = route_evidence(hands, observations, max_tables=max_tables)
    routed['source_csv_sha256'] = hashlib.sha256(Path(csv_path).read_bytes()).hexdigest()
    routed['review_status'] = 'UNVERIFIED'
    routed['ev_authorized'] = False
    routed['mp4_loss_label_authorized'] = False
    return routed


def write_review_json(result, output_path):
    """Write new review without replacing existing results."""
    path = Path(output_path)
    payload = (json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(payload)
    return path
