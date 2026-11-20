"""Offline Poker Cortes CSV -> unverified PLO review queue.

No inferred financial result is confirmed or forwarded to EV or automatic clips.
Run as: python -m video_analyzer.poker_cortes_pipeline report.csv VIDEO_SHA DURATION output.json
"""
import argparse
import json
import os
import tempfile
from pathlib import Path

try:
    from .poker_cortes_review_import import import_report
    from .poker_cortes_review_queue import build_review_queue
except ImportError:
    from poker_cortes_review_import import import_report
    from poker_cortes_review_queue import build_review_queue


def prepare_review_queue(csv_path, *, video_sha256, duration_seconds, min_loss_bb=30, max_tables=4):
    candidates = import_report(csv_path, video_sha256=video_sha256,
                               duration_seconds=duration_seconds, max_tables=max_tables)
    queue = build_review_queue(candidates, min_loss_bb=min_loss_bb, max_tables=max_tables)
    if queue['total'] != len(candidates):
        raise RuntimeError('candidate count mismatch')
    return queue


def save_review_queue(queue, destination):
    """Create a new output exclusively; never overwrite a previous review."""
    target = Path(destination)
    if not target.parent.is_dir():
        raise ValueError('output directory does not exist')
    payload = (json.dumps(queue, ensure_ascii=False, sort_keys=True, indent=2,
                          allow_nan=False) + '\n').encode('utf-8')
    fd, temp = tempfile.mkstemp(prefix='.plo-review-', suffix='.tmp', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, target)
    finally:
        os.unlink(temp)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description='Import Poker Cortes report as unverified review queue')
    parser.add_argument('report_csv')
    parser.add_argument('video_sha256')
    parser.add_argument('duration_seconds', type=float)
    parser.add_argument('output_json')
    parser.add_argument('--min-loss-bb', type=float, default=30)
    args = parser.parse_args(argv)
    queue = prepare_review_queue(args.report_csv, video_sha256=args.video_sha256,
                                 duration_seconds=args.duration_seconds, min_loss_bb=args.min_loss_bb)
    save_review_queue(queue, args.output_json)
    print(f"Queued {queue['total']} unverified candidate(s): {args.output_json}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
