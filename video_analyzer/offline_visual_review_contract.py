"""Validate browser-exported ROI/review JSON against a recorded video and timeline.

No OCR, poker action inference, live capture, network access or automatic hand
verification. This contract is intended for offline_visual_review_ui.html.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import offline_four_table_visual_timeline as core
import offline_manual_roi_review as review


def validate_bundle(video, roi_file, timeline_file, decisions_file):
    """Return a reviewed clip plan only if all files belong to the same video.

    The browser does not compute a source-video SHA-256. Python independently
    hashes the recorded video and checks the timeline and review declarations.
    """
    rois = review.load_object(roi_file)
    timeline = review.load_object(timeline_file, 10 * 1024 * 1024)
    decisions = review.load_object(decisions_file)
    expected = review.validate_rois(rois)
    tables = timeline.get('tables')
    review.check(type(tables) is list and len(tables) == len(expected),
                 'ROI/timeline table count mismatch')
    for roi, table in zip(expected, tables):
        review.check(type(table) is dict and
                     table.get('table_id') == roi['table_id'] and
                     table.get('normalized_rect') == roi['normalized_rect'] and
                     table.get('pixel_rect') == roi['pixel_rect'],
                     'ROI geometry or table order differs from timeline')
    review.check(timeline.get('roi_config_sha256') == core.sha256_file(Path(roi_file)),
                 'ROI JSON differs from the file used for timeline analysis')
    review.check(type(decisions.get('video_sha256')) is str and
                 decisions['video_sha256'] == timeline.get('video_sha256'),
                 'browser review is not bound to this video')
    plan = review.review_plan(video, timeline, decisions,
                              core.sha256_file(Path(timeline_file)),
                              core.sha256_file(Path(decisions_file)))
    plan['source_roi_config_sha256'] = core.sha256_file(Path(roi_file))
    plan['ui_review_contract'] = 'browser_declarations_verified_against_local_video_hash'
    plan['ui_review_contract_limitations'] = [
        'Browser decisions are human declarations, not independently verified hands.',
        'Timeline candidates represent visual changes, not proven poker actions.',
        'The Python SHA-256 checks file identity, not visual correctness.']
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('rois')
    parser.add_argument('timeline')
    parser.add_argument('decisions')
    parser.add_argument('new_plan')
    args = parser.parse_args(argv)
    output = review.new_output(args.new_plan,
                               [args.video, args.rois, args.timeline, args.decisions])
    plan = validate_bundle(args.video, args.rois, args.timeline, args.decisions)
    review.write_new(output, plan)
    print(json.dumps({'plan': str(output), 'clips_planned': len(plan['clips']),
                      'status': plan['status']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
