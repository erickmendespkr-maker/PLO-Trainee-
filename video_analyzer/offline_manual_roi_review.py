"""Offline PLO5/PLO6 visual ROI timeline and human-reviewed hand clip plan.

This module never asserts automatic hand recognition. Input videos are recordings,
not live streams. ROI rectangles and hand boundaries are explicitly human supplied.

  python offline_manual_roi_review.py analyze recording.mp4 rois.json NEW_timeline.json
  python offline_manual_roi_review.py review recording.mp4 timeline.json decisions.json NEW_plan.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import offline_four_table_visual_timeline as core

ID = re.compile(r'^[a-zA-Z0-9_-]{1,40}$')
DECISIONS = {'confirmed_hand', 'not_hand', 'uncertain'}


def check(value, message):
    if not value:
        raise core.TimelineError(message)


def load_object(path, max_bytes=1024 * 1024):
    path = Path(path)
    check(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= max_bytes,
          'invalid or oversized JSON input')
    try:
        data = json.loads(path.read_text(encoding='utf-8'),
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    except (ValueError, UnicodeError) as exc:
        raise core.TimelineError('invalid JSON') from exc
    check(type(data) is dict, 'JSON root must be an object')
    return data


def number(value, low, high):
    return type(value) in (float, int) and math.isfinite(value) and low <= value <= high


def validate_rois(config):
    check(config.get('schema_version') == 1 and type(config.get('tables')) is list,
          'unsupported ROI configuration')
    tables = config['tables']
    check(1 <= len(tables) <= 4, 'ROI count must be 1..4')
    result = []
    for item in tables:
        check(type(item) is dict and type(item.get('table_id')) is str and
              ID.fullmatch(item['table_id']) is not None, 'invalid table ID')
        r = item.get('normalized_rect')
        check(type(r) is list and len(r) == 4 and all(number(v, 0, 1) for v in r),
              'ROI must be four finite normalized numbers')
        x, y, w, h = r
        check(w > 0 and h > 0 and x + w <= 1 + 1e-9 and y + h <= 1 + 1e-9,
              'ROI outside video')
        left, top = round(x * core.WIDTH), round(y * core.HEIGHT)
        right, bottom = round((x+w) * core.WIDTH), round((y+h) * core.HEIGHT)
        check(right-left >= 8 and bottom-top >= 8 and right <= core.WIDTH and bottom <= core.HEIGHT,
              'ROI too small or outside sampled image')
        check(all(item['table_id'] != old['table_id'] for old in result), 'duplicate table ID')
        rect = [left, top, right-left, bottom-top]
        check(all(not (left < old['pixel_rect'][0] + old['pixel_rect'][2] and
                       right > old['pixel_rect'][0] and
                       top < old['pixel_rect'][1] + old['pixel_rect'][3] and
                       bottom > old['pixel_rect'][1]) for old in result), 'overlapping ROIs')
        result.append({'table_id': item['table_id'], 'normalized_rect': r,
                       'pixel_rect': rect})
    return result


def custom_timeline(video, config, interval=1., threshold=.08):
    rois = validate_rois(config)
    check(number(interval, .5, 5) and number(threshold, .000001, 1), 'invalid sampling parameters')
    path, metadata = core.inspect_video(video)
    before = core.sha256_file(path)
    frames = core.sampled_frames(path, interval=interval)
    times = [t for t, _ in frames]
    check(bool(times) and all(a < b for a, b in zip(times, times[1:])), 'invalid source PTS')
    tables = []
    for roi in rois:
        events = []
        for (t, current), (_, previous) in zip(frames[1:], frames[:-1]):
            fraction = core.change_fraction(previous, current, roi['pixel_rect'])
            if fraction >= threshold:
                events.append({'pts_seconds': round(t, 6),
                               'changed_fraction': round(fraction, 6)})
        x, y, w, h = roi['normalized_rect']
        tables.append({**roi, 'source_pixel_rect': [round(x * metadata['width']),
                                                   round(y * metadata['height']),
                                                   round(w * metadata['width']),
                                                   round(h * metadata['height'])],
                       'events': events,
                       'candidate_windows': core.group_candidates(events, metadata['duration_seconds'])})
    check(core.sha256_file(path) == before, 'video changed during analysis')
    return {'schema_version': 1, 'analysis_status': 'visual_activity_only_not_hands',
            'roi_origin': 'human_configured_not_automatically_detected',
            'video': metadata, 'video_sha256': before,
            'roi_config_sha256': None, 'source_pts_kind':
            'ffmpeg_selected_source_frame_presentation_timestamp',
            'sample_interval_requested_seconds': interval,
            'sampled_frame_count': len(frames),
            'sample_pts_seconds': [round(t, 6) for t in times],
            'change_threshold_fraction': threshold, 'tables': tables,
            'ocr_performed': False, 'hand_boundaries_verified': False,
            'manual_review_required': True}


def review_plan(video, timeline, decisions, timeline_hash, decisions_hash):
    path, metadata = core.inspect_video(video)
    check(timeline.get('schema_version') == 1 and
          timeline.get('video_sha256') == core.sha256_file(path),
          'timeline video SHA-256 mismatch')
    check(type(timeline.get('video')) is dict and
          number(timeline['video'].get('duration_seconds'), .01, core.MAX_DURATION) and
          abs(timeline['video']['duration_seconds'] - metadata['duration_seconds']) < .05,
          'timeline video duration mismatch')
    tables = timeline.get('tables')
    check(type(tables) is list and 1 <= len(tables) <= 4, 'invalid timeline tables')
    by_id = {}
    for table in tables:
        check(type(table) is dict and type(table.get('table_id')) is str and
              ID.fullmatch(table['table_id']) and table['table_id'] not in by_id and
              type(table.get('candidate_windows')) is list,
              'invalid timeline table')
        for candidate in table['candidate_windows']:
            check(type(candidate) is dict and
                  number(candidate.get('start_seconds'), 0, metadata['duration_seconds']) and
                  number(candidate.get('end_seconds'), 0, metadata['duration_seconds']) and
                  candidate['start_seconds'] < candidate['end_seconds'],
                  'invalid candidate interval')
        by_id[table['table_id']] = table
    check(decisions.get('schema_version') == 1 and
          type(decisions.get('reviews')) is list and len(decisions['reviews']) <= 1000,
          'invalid review list')
    if 'video_sha256' in decisions:
        check(decisions['video_sha256'] == timeline['video_sha256'], 'review video mismatch')
    clips, reviewed, seen = [], [], set()
    for entry in decisions['reviews']:
        check(type(entry) is dict, 'invalid review entry')
        table_id, index, decision = entry.get('table_id'), entry.get('candidate_index'), entry.get('decision')
        check(type(table_id) is str and table_id in by_id and type(index) is int and
              0 <= index < len(by_id[table_id]['candidate_windows']) and
              decision in DECISIONS, 'review references unknown candidate or decision')
        key = (table_id, index)
        check(key not in seen, 'duplicate candidate review')
        seen.add(key)
        note = entry.get('notes', '')
        check(type(note) is str and len(note) <= 500, 'invalid review note')
        row = {'table_id': table_id, 'candidate_index': index, 'decision': decision,
               'notes': note, 'candidate_window': by_id[table_id]['candidate_windows'][index]}
        if decision == 'confirmed_hand':
            hand_id = entry.get('hand_id')
            start, end = entry.get('start_seconds'), entry.get('end_seconds')
            check(type(hand_id) is str and ID.fullmatch(hand_id) and
                  number(start, 0, metadata['duration_seconds']) and
                  number(end, 0, metadata['duration_seconds']) and
                  .1 <= end-start <= 300, 'confirmed hand requires valid manual boundaries and ID')
            check(all(hand_id != c['hand_id'] for c in clips), 'duplicate hand ID')
            clip = {'hand_id': hand_id, 'table_id': table_id,
                    'start_seconds': start, 'end_seconds': end,
                    'duration_seconds': round(end-start, 6),
                    'review_basis': 'human_declared_boundaries_not_automatic_detection',
                    'candidate_index': index, 'source_candidate_window': row['candidate_window']}
            clips.append(clip)
            row['hand_id'] = hand_id
        else:
            check(not any(k in entry for k in ('hand_id', 'start_seconds', 'end_seconds')),
                  'nonconfirmed candidate cannot define hand boundaries')
        reviewed.append(row)
    check(core.sha256_file(path) == timeline['video_sha256'], 'video changed during review')
    return {'schema_version': 1, 'status': 'human_reviewed_clip_plan_not_automated_hand_detection',
            'source_video_sha256': timeline['video_sha256'],
            'source_video_duration_seconds': metadata['duration_seconds'],
            'source_timeline_sha256': timeline_hash, 'review_input_sha256': decisions_hash,
            'source_pts_kind': timeline.get('source_pts_kind'),
            'reviews': reviewed, 'clips': clips, 'clip_mp4_exported': False,
            'equity_or_ev_calculated': False,
            'limitations': ['Human decisions are assertions, not independently verified poker facts.',
                            'Unreviewed candidates remain unknown, not discarded hands.',
                            'Clip boundaries may differ from nearest video frame PTS.']}


def new_output(path, input_paths):
    path = Path(path)
    check(path.suffix.lower() == '.json' and path.parent.is_dir() and
          not path.parent.is_symlink() and not path.exists() and not path.is_symlink() and
          path.resolve() not in [Path(p).resolve() for p in input_paths],
          'output must be a new JSON file')
    return path


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    a = commands.add_parser('analyze')
    a.add_argument('video'); a.add_argument('rois'); a.add_argument('output')
    a.add_argument('--interval', type=float, default=1.)
    a.add_argument('--threshold', type=float, default=.08)
    r = commands.add_parser('review')
    r.add_argument('video'); r.add_argument('timeline'); r.add_argument('decisions'); r.add_argument('output')
    args = parser.parse_args(argv)
    if args.mode == 'analyze':
        out = new_output(args.output, [args.video, args.rois])
        config = load_object(args.rois)
        result = custom_timeline(args.video, config, args.interval, args.threshold)
        result['roi_config_sha256'] = core.sha256_file(Path(args.rois))
    else:
        out = new_output(args.output, [args.video, args.timeline, args.decisions])
        timeline, decisions = load_object(args.timeline, 10 * 1024 * 1024), load_object(args.decisions)
        result = review_plan(args.video, timeline, decisions,
                             core.sha256_file(Path(args.timeline)), core.sha256_file(Path(args.decisions)))
    write_new(out, result)
    print(json.dumps({'mode': args.mode, 'output': str(out),
                      'clips_planned': len(result.get('clips', []))}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
