"""Offline PLO5 preflight: scan real MP4 layouts without card calibration.

This diagnostic only counts layout/OCR candidates. It cannot reconstruct or
certify hands and never saves private card, stack or screenshot evidence.
"""
import argparse
import json
from collections import Counter
from pathlib import Path


def scan(source, *, step_seconds=15, max_samples=512, ocr_samples=0):
    if not (type(step_seconds) is int and 1 <= step_seconds <= 300
            and type(max_samples) is int and 1 <= max_samples <= 512
            and type(ocr_samples) is int and 0 <= ocr_samples <= max_samples):
        raise ValueError('Invalid preflight sampling budget')
    source = Path(source)
    if not (source.is_file() and not source.is_symlink()
            and source.suffix.lower() == '.mp4'):
        raise ValueError('Local MP4 required')
    import cv2
    from PIL import Image
    from plo5_mixed_money import detect, read
    from plo5_video_stream import digest
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        capture.release()
        raise ValueError('Video cannot be opened')
    counts = {str(t): Counter() for t in range(1, 5)}
    ocr = {name: Counter() for name in ('stack', 'pot')}
    sampled = 0
    try:
        frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        fps = capture.get(cv2.CAP_PROP_FPS)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if not (fps > 0 and frame_count > 0 and (width, height) == (1504, 696)):
            raise ValueError('Unsupported video duration or layout geometry')
        duration = frame_count / fps
        timestamps = list(range(0, min(int(duration) + 1, step_seconds * max_samples), step_seconds))
        # OCR targets are spread over the same independent interval grid.
        targets = (set() if not ocr_samples else
                   {round(i * (len(timestamps) - 1) / max(1, ocr_samples - 1))
                    for i in range(ocr_samples)})
        for index, second in enumerate(timestamps):
            capture.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
            ok, frame = capture.read()
            if not ok:
                break
            sampled += 1
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            for table in range(1, 5):
                platform = detect(image, table)
                counts[str(table)][platform or 'undetected'] += 1
                if platform and index in targets:
                    for field in ('stack', 'pot'):
                        candidate = read(image, table, platform, field)['value_bb']
                        ocr[field]['candidate' if candidate is not None else 'unknown'] += 1
    finally:
        capture.release()
    return dict(version='plo5-video-preflight-v1', source_sha256=digest(source),
                duration_seconds=duration, frame_geometry=[width, height],
                sample_interval_seconds=step_seconds, samples=sampled,
                layout_candidates={k: dict(v) for k, v in counts.items()},
                ocr_availability={k: dict(v) for k, v in ocr.items()},
                hands_reconstructed=False, financial_result_verified=False,
                strategy_authorized=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('--step', type=int, default=15)
    parser.add_argument('--samples', type=int, default=512)
    parser.add_argument('--ocr-samples', type=int, default=0)
    args = parser.parse_args(argv)
    print(json.dumps(scan(args.video, step_seconds=args.step,
                          max_samples=args.samples, ocr_samples=args.ocr_samples),
                     indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
