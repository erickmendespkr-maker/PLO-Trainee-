"""Bridge human-reviewed four-table clip plans to existing offline FFmpeg exporter.

Requires explicit human-written explanations. The generated clips are not
independently proven poker hands, and no equity/EV is inferred here.
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path

import offline_four_table_visual_timeline as core
import offline_manual_roi_review as review
import offline_reviewed_clip_export as existing


def build_requests(video, plan, timeline, explanations):
    path, meta = core.inspect_video(video)
    review.check(plan.get('schema_version') == 1 and
                 plan.get('status') == 'human_reviewed_clip_plan_not_automated_hand_detection' and
                 plan.get('source_video_sha256') == core.sha256_file(path),
                 'review plan does not match video')
    review.check(timeline.get('schema_version') == 1 and
                 timeline.get('video_sha256') == plan['source_video_sha256'] and
                 type(timeline.get('tables')) is list, 'timeline does not match video')
    tables = timeline['tables']
    review.check(1 <= len(tables) <= 4, 'invalid table count')
    by_id = {}
    for index, table in enumerate(tables, 1):
        review.check(type(table) is dict and type(table.get('table_id')) is str and
                     table['table_id'] not in by_id and
                     type(table.get('source_pixel_rect')) is list and
                     len(table['source_pixel_rect']) == 4, 'invalid table geometry')
        by_id[table['table_id']] = (index, table['source_pixel_rect'])
    clips = plan.get('clips')
    review.check(type(clips) is list and 1 <= len(clips) <= 100, 'no reviewed clips')
    review.check(type(explanations.get('explanations')) is dict, 'explanations mapping required')
    notes = explanations['explanations']
    review.check(set(notes) == {c.get('hand_id') for c in clips if type(c) is dict},
                 'each reviewed hand needs exactly one human explanation')
    requests = []
    for clip in clips:
        review.check(type(clip) is dict and clip.get('table_id') in by_id and
                     clip.get('review_basis') == 'human_declared_boundaries_not_automatic_detection',
                     'unreviewed clip or unknown table')
        hand_id = clip.get('hand_id')
        review.check(type(hand_id) is str and review.ID.fullmatch(hand_id), 'invalid hand ID')
        table_number, rect = by_id[clip['table_id']]
        review.check(all(type(v) is int for v in rect), 'ROI crop requires integer source pixels')
        x, y, w, h = rect
        explanation = notes[hand_id]
        request = {'schema_version': 1, 'hand_id': hand_id, 'table_id': table_number,
                   'start_seconds': clip.get('start_seconds'),
                   'end_seconds': clip.get('end_seconds'),
                   'crop': {'x': x, 'y': y, 'width': w, 'height': h},
                   'explanation': explanation,
                   'source_video_sha256': plan['source_video_sha256'],
                   'reviewer_confirmed_offline': True}
        existing.validate_request(request, meta['width'], meta['height'],
                                  meta['duration_seconds'], plan['source_video_sha256'])
        requests.append((hand_id, request))
    review.check(len(set(x[0] for x in requests)) == len(requests), 'duplicate hand IDs')
    return requests


def export_bundle(video, plan_path, timeline_path, explanations_path, output_dir):
    plan = review.load_object(plan_path, 10 * 1024 * 1024)
    timeline = review.load_object(timeline_path, 10 * 1024 * 1024)
    explanations = review.load_object(explanations_path)
    review.check(plan.get('source_timeline_sha256') == core.sha256_file(Path(timeline_path)),
                 'timeline changed since human review')
    requests = build_requests(video, plan, timeline, explanations)
    dest = Path(output_dir)
    review.check(not dest.exists() and not dest.is_symlink() and
                 dest.parent.is_dir() and not dest.parent.is_symlink(),
                 'destination must be a new directory')
    result = []
    with tempfile.TemporaryDirectory(prefix='.plo_reviewed_', dir=dest.parent) as temp:
        stage = Path(temp)
        for hand_id, request in requests:
            request_file = stage / (hand_id + '.request.json')
            request_file.write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n',
                                    encoding='utf-8')
            clip = stage / (hand_id + '.mp4')
            info = existing.export(video, request_file, clip)
            result.append({'hand_id': hand_id, 'file': clip.name,
                           'clip_sha256': info['clip_sha256'],
                           'sidecar': clip.name + '.json',
                           'source_table_id': plan['clips'][len(result)]['table_id']})
        manifest = {'schema_version': 1, 'status': 'human_reviewed_clips_not_verified_hands',
                    'source_video_sha256': plan['source_video_sha256'],
                    'source_plan_sha256': core.sha256_file(Path(plan_path)),
                    'source_timeline_sha256': core.sha256_file(Path(timeline_path)),
                    'human_explanations_sha256': core.sha256_file(Path(explanations_path)),
                    'clips': result, 'equity_or_ev_calculated': False,
                    'automatic_hand_detection': False}
        review.write_new(stage / 'manifest.json', manifest)
        review.check(core.sha256_file(Path(video)) == plan['source_video_sha256'],
                     'video changed during clip export')
        stage.rename(dest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video'); parser.add_argument('plan'); parser.add_argument('timeline')
    parser.add_argument('explanations'); parser.add_argument('new_output_directory')
    a = parser.parse_args(argv)
    manifest = export_bundle(a.video, a.plan, a.timeline, a.explanations, a.new_output_directory)
    print(json.dumps({'clips_exported': len(manifest['clips']), 'output': a.new_output_directory}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
