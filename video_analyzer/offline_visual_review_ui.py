"""Generate a self-contained, offline ROI selector or human candidate-review page.

No upload, remote service, live poker connection, OCR assertion or automatic
hand classification. The page exports JSON accepted by offline_manual_roi_review.

    python offline_visual_review_ui.py roi recording.mp4 NEW_rois_editor.html
    python offline_visual_review_ui.py review recording.mp4 timeline.json NEW_review_editor.html
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import subprocess
from pathlib import Path

import offline_four_table_visual_timeline as core
import offline_manual_roi_review as manual

_TEMPLATE_GZIP_B64 = (
    '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'
)
MAX_PREVIEW_BYTES = 1_500_000


def generate(mode, video, output, timeline_path=None):
    manual.check(mode in ('roi', 'review'), 'unknown mode')
    inputs = [video] + ([timeline_path] if timeline_path else [])
    dest = Path(output)
    manual.check(dest.suffix.lower() == '.html' and dest.parent.is_dir() and
                 not dest.parent.is_symlink() and not dest.exists() and not dest.is_symlink() and
                 dest.resolve() not in {Path(p).resolve() for p in inputs},
                 'output must be a new HTML file')
    video_path, meta = core.inspect_video(video)
    before = core.sha256_file(video_path)
    data = {'mode': mode, 'video_sha256': before,
            'width': meta['width'], 'height': meta['height'],
            'duration_seconds': meta['duration_seconds']}
    if mode == 'roi':
        manual.check(timeline_path is None, 'ROI mode cannot use timeline')
        command = ['ffmpeg', '-nostdin', '-v', 'error', '-i', str(video_path),
                   '-frames:v', '1', '-vf', 'scale=w=960:h=960:force_original_aspect_ratio=decrease',
                   '-f', 'image2pipe', '-vcodec', 'mjpeg', '-q:v', '4', 'pipe:1']
        try:
            result = subprocess.run(command, capture_output=True, timeout=40, check=True)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise core.TimelineError('could not extract offline preview') from exc
        manual.check(0 < len(result.stdout) <= MAX_PREVIEW_BYTES and
                     result.stdout.startswith(b'\xff\xd8'), 'invalid or oversized preview')
        data['preview_jpeg_base64'] = base64.b64encode(result.stdout).decode('ascii')
    else:
        manual.check(timeline_path is not None, 'review mode requires timeline')
        timeline = manual.load_object(timeline_path, 10 * 1024 * 1024)
        manual.check(timeline.get('schema_version') == 1 and
                     timeline.get('video_sha256') == before and
                     type(timeline.get('tables')) is list and
                     1 <= len(timeline['tables']) <= 4,
                     'timeline does not match source video')
        manual.check(type(timeline.get('video')) is dict and
                     manual.number(timeline['video'].get('duration_seconds'), .01, core.MAX_DURATION) and
                     abs(timeline['video']['duration_seconds'] - meta['duration_seconds']) < .05,
                     'timeline duration mismatch')
        tables, seen, total = [], set(), 0
        for table in timeline['tables']:
            table_id = table.get('table_id') if type(table) is dict else None
            manual.check(type(table_id) is str and manual.ID.fullmatch(table_id) and
                         table_id not in seen and type(table.get('candidate_windows')) is list,
                         'invalid table in timeline')
            seen.add(table_id)
            candidates = table['candidate_windows']
            total += len(candidates)
            manual.check(total <= 1000, 'too many candidates for offline editor')
            for candidate in candidates:
                manual.check(type(candidate) is dict and
                             manual.number(candidate.get('start_seconds'), 0, meta['duration_seconds']) and
                             manual.number(candidate.get('end_seconds'), 0, meta['duration_seconds']) and
                             candidate['start_seconds'] < candidate['end_seconds'],
                             'invalid candidate window')
            tables.append({'table_id': table_id, 'candidate_windows': candidates})
        data['tables'] = tables
        data['source_timeline_sha256'] = core.sha256_file(Path(timeline_path))
    manual.check(core.sha256_file(video_path) == before, 'video changed while preparing editor')
    raw = gzip.decompress(base64.b64decode(_TEMPLATE_GZIP_B64)).decode('utf-8')
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    manual.check(raw.count('/*__BOOTSTRAP__*/') == 1, 'invalid UI template')
    html = raw.replace('/*__BOOTSTRAP__*/', payload)
    with dest.open('x', encoding='utf-8') as out:
        out.write(html)
    return {'mode': mode, 'output': str(dest), 'video_sha256': before,
            'candidate_count': sum(len(t['candidate_windows']) for t in data.get('tables', []))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    a = sub.add_parser('roi'); a.add_argument('video'); a.add_argument('output')
    b = sub.add_parser('review'); b.add_argument('video'); b.add_argument('timeline'); b.add_argument('output')
    args = parser.parse_args(argv)
    print(json.dumps(generate(args.mode, args.video, args.output,
                              getattr(args, 'timeline', None))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
