"""Resolve offline PLO decision timestamps against HUMAN-CLAIMED temporal crops.

Fail closed at geometry transitions. Never turns OCR/ranges/equity into facts.
Only works with offline_table_temporal_review.py review schema v1.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import re

import offline_table_region_proposals as base

STATUS = 'manual_offline_temporal_layout_claim_unverified'
ID = re.compile(r'T[1-4]\Z')


def validate_review(review, video_sha256, width, height, duration):
    base.require(type(review) is dict and review.get('schema_version') == 1 and
                 review.get('status') == STATUS and
                 review.get('source_video_sha256') == video_sha256 and
                 review.get('source_width') == width and
                 review.get('source_height') == height and
                 review.get('source_duration_seconds') == duration and
                 review.get('human_confirmation_claimed') is True and
                 review.get('table_identity_verified') is False and
                 review.get('automatic_ocr_math_authorization') is False,
                 'untrusted temporal review')
    segments = review.get('segments')
    base.require(type(segments) is list and 1 <= len(segments) <= 12,
                 'invalid temporal segment list')
    end_previous = 0.0
    ids_previous = None
    for seg in segments:
        base.require(type(seg) is dict and set(seg) ==
                     {'start_seconds', 'end_seconds', 'regions'}, 'invalid segment schema')
        a, b = seg['start_seconds'], seg['end_seconds']
        base.require(type(a) in (int, float) and type(b) in (int, float) and
                     math.isfinite(a) and math.isfinite(b) and
                     abs(a - end_previous) <= 0.001 and b - a >= .5 and
                     b <= duration + .001, 'noncontiguous/out-of-bounds timeline')
        end_previous = b
        regions = seg['regions']
        base.require(type(regions) is list and 1 <= len(regions) <= 4,
                     'invalid table count')
        ids = []
        for r in regions:
            base.require(type(r) is dict and set(r) ==
                         {'table_id', 'x', 'y', 'width', 'height'}, 'invalid region schema')
            tid = r['table_id']
            base.require(type(tid) is str and ID.fullmatch(tid) and tid not in ids,
                         'invalid table ID')
            ids.append(tid)
            x, y, w, h = (r[k] for k in ('x', 'y', 'width', 'height'))
            base.require(all(type(n) is int for n in (x, y, w, h)) and
                         x >= 0 and y >= 0 and w >= 32 and h >= 32 and
                         x % 2 == y % 2 == w % 2 == h % 2 == 0 and
                         x + w <= width and y + h <= height,
                         'invalid crop coordinates')
        base.require(ids_previous is None or ids == ids_previous,
                     'table identity changed without mapping')
        ids_previous = ids
        for i, r in enumerate(regions):
            for s in regions[i + 1:]:
                base.require(min(r['x'] + r['width'], s['x'] + s['width']) <=
                             max(r['x'], s['x']) or
                             min(r['y'] + r['height'], s['y'] + s['height']) <=
                             max(r['y'], s['y']), 'overlapping crops')
    base.require(abs(end_previous - duration) <= .001, 'incomplete timeline')
    return segments


def locate(review, *, video_sha256, width, height, duration,
           table_id, timestamp, boundary_guard_seconds=.25):
    """Return claimed crop or a blocked reason; no auto math authorization."""
    segments = validate_review(review, video_sha256, width, height, duration)
    base.require(type(table_id) is str and ID.fullmatch(table_id), 'invalid table ID')
    base.require(type(timestamp) in (int, float) and math.isfinite(timestamp) and
                 0 <= timestamp < duration, 'invalid timestamp')
    base.require(type(boundary_guard_seconds) in (int, float) and
                 math.isfinite(boundary_guard_seconds) and
                 0 <= boundary_guard_seconds <= 2, 'invalid boundary guard')
    for index, seg in enumerate(segments):
        if seg['start_seconds'] <= timestamp < seg['end_seconds'] or (
                index == len(segments) - 1 and timestamp < duration):
            for boundary in (seg['start_seconds'], seg['end_seconds']):
                if 0 < boundary < duration and abs(timestamp - boundary) <= boundary_guard_seconds:
                    return {'status': 'blocked_transition_uncertainty',
                            'timestamp_seconds': timestamp,
                            'boundary_seconds': boundary,
                            'automatic_ocr_math_authorization': False}
            region = next((r for r in seg['regions'] if r['table_id'] == table_id), None)
            base.require(region is not None, 'table ID missing from reviewed segment')
            return {'status': 'manual_geometry_claim_only',
                    'segment_index': index + 1, 'table_id_claim': table_id,
                    'timestamp_seconds': timestamp, 'region_claim': region,
                    'source_video_sha256': video_sha256,
                    'automatic_ocr_math_authorization': False,
                    'table_identity_verified': False}
    raise ValueError('timestamp outside segments')


def locate_files(video, review_json, table_id, timestamp, *, boundary_guard_seconds=.25):
    video, review_json = Path(video), Path(review_json)
    base.safe_file(video)
    review = base.read_json(review_json)
    w, h, duration = base.probe(video)
    return locate(review, video_sha256=base.sha256(video), width=w, height=h,
                  duration=duration, table_id=table_id, timestamp=timestamp,
                  boundary_guard_seconds=boundary_guard_seconds)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('video')
    p.add_argument('review_json')
    p.add_argument('table_id')
    p.add_argument('timestamp', type=float)
    a = p.parse_args()
    print(json.dumps(locate_files(a.video, a.review_json, a.table_id, a.timestamp),
                     indent=2, ensure_ascii=False))
