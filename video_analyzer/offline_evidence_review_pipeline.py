"""Offline composition of unreviewed frame evidence, timeline and review queue."""
import argparse
import hashlib
import json
from pathlib import Path

try:
    from .offline_evidence_timeline import build_timeline
    from .offline_hand_review_queue import propose_review_intervals
except ImportError:
    from offline_evidence_timeline import build_timeline
    from offline_hand_review_queue import propose_review_intervals


def build_review_bundle(evidence, *, crop_start_seconds=None, min_gap_seconds=0.05,
                        max_gap_seconds=120.0):
    timeline = build_timeline(evidence, crop_start_seconds=crop_start_seconds)
    queue = propose_review_intervals(timeline, min_gap_seconds=min_gap_seconds,
                                     max_gap_seconds=max_gap_seconds)
    canonical = json.dumps(evidence, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return {'status': 'UNREVIEWED_EVIDENCE_REVIEW_BUNDLE',
            'evidence_json_sha256': hashlib.sha256(canonical).hexdigest(),
            'timeline': timeline, 'review_queue': queue,
            'hands_verified': False, 'ocr_verified': False,
            'equity_ev_verified': False, 'source_identity_verified': False}


def write_review_bundle(evidence_path, output_path, **kwargs):
    src, dst = Path(evidence_path), Path(output_path)
    if src.is_symlink() or not src.is_file() or dst.is_symlink() or src.resolve() == dst.resolve():
        raise ValueError('unsafe path')
    evidence = json.loads(src.read_text(encoding='utf-8'))
    bundle = build_review_bundle(evidence, **kwargs)
    with dst.open('x', encoding='utf-8') as f:
        json.dump(bundle, f, indent=2, ensure_ascii=False, allow_nan=False)
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence_json')
    parser.add_argument('output_json')
    parser.add_argument('--crop-start-seconds', type=float)
    parser.add_argument('--min-gap-seconds', type=float, default=0.05)
    parser.add_argument('--max-gap-seconds', type=float, default=120.0)
    args = parser.parse_args()
    result = write_review_bundle(args.evidence_json, args.output_json,
        crop_start_seconds=args.crop_start_seconds,
        min_gap_seconds=args.min_gap_seconds, max_gap_seconds=args.max_gap_seconds)
    print(json.dumps({'status': result['status'],
                      'candidate_intervals': len(result['review_queue']['proposals'])}))


if __name__ == '__main__':
    main()
