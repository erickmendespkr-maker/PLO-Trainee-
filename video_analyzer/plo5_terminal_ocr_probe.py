"""Targeted offline action-label probe near an unresolved river settlement.

Extracts only an aggregate, unverified OCR signal. Never decides whether the
player actually folded, won, rebought, or lost chips. This diagnostic is never
used as a strategic action or as an input to automatic settlement.
"""
import argparse
import json
import re
from hashlib import sha256
from fractions import Fraction
from pathlib import Path

from plo5_pre_gto_context import need


FOLD_WORDS = frozenset(('fold', 'folds', 'folded'))


def fold_text_candidate(raw, confidence, *, minimum=0.35):
    """Candidate from weak OCR; not a reliable visual action observation."""
    return (type(raw) is str and type(confidence) in (int, float)
            and minimum <= confidence <= 1.0
            and any(word in FOLD_WORDS for word in re.findall(r'[a-z]+', raw.lower())))


def probe(video, table, seat, start, seconds, *, fps=2, limit=64):
    from PIL import Image
    import cv2
    from plo5_mixed_money import STARTS, detect
    from plo5_seat_evidence import ACTIONS, SEATS, decode

    need(type(table) is int and 1 <= table <= 4 and seat in SEATS,
         'Invalid table/seat')
    need(type(start) in (int, float) and start >= 0 and type(seconds) in (int, float)
         and 0 < seconds <= 30 and type(fps) is int and 1 <= fps <= 4
         and type(limit) is int and 1 <= limit <= 128,
         'Invalid offline sample budget')
    p = Path(video)
    need(p.is_file() and not p.is_symlink() and p.suffix.lower() == '.mp4',
         'Local MP4 required')
    cap = cv2.VideoCapture(str(p))
    need(cap.isOpened(), 'Video unavailable')
    counts = dict(samples=0, weak_fold_readings=0, strong_fold_readings=0,
                  unknown=0, distinct_weak_roi_hashes=0)
    hashes = set()
    times = []
    try:
        count = min(limit, int(seconds * fps))
        for i in range(count):
            t = Fraction(str(start)) + Fraction(i, fps)
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            platform = detect(image, table)
            counts['samples'] += 1
            if platform not in ACTIONS:
                counts['unknown'] += 1
                continue
            a, b, c, d = ACTIONS[platform][SEATS.index(seat)]
            x = STARTS[table - 1]
            patch = image.crop((x+a, b, x+c, d))
            result = decode(patch, platform, 'action')
            if result['candidate'] == 'fold':
                counts['strong_fold_readings'] += 1
                times.append(str(t))
            elif fold_text_candidate(result.get('raw'), result.get('confidence')):
                counts['weak_fold_readings'] += 1
                hashes.add(sha256(patch.tobytes()).hexdigest())
                times.append(str(t))
            else:
                counts['unknown'] += 1
    finally:
        cap.release()
    counts['distinct_weak_roi_hashes'] = len(hashes)
    return dict(version='plo5-terminal-ocr-probe-v1', table_id=table, seat=seat,
                counts=counts, candidate_timestamps=times,
                fold_verified=False, payout_verified=False, rebuy_verified=False,
                financial_result_verified=False, strategy_authorized=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('--table', type=int, required=True)
    parser.add_argument('--seat', required=True)
    parser.add_argument('--start', type=float, required=True)
    parser.add_argument('--seconds', type=float, default=4.0)
    parser.add_argument('--fps', type=int, default=2)
    a = parser.parse_args(argv)
    print(json.dumps(probe(a.video, a.table, a.seat, a.start, a.seconds, fps=a.fps),
                     indent=2))


if __name__ == '__main__':
    main()
