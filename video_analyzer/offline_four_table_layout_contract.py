"""Strict, offline 1–4 table layout/sampling contract; no poker detection."""
import hashlib
import json
import math
from table_regions import Region, grid_regions, validate_regions

STATUS = 'unverified_four_table_layout_and_sample_plan_only'


def build_plan(layout, width, height, duration, sample_times):
    """Return a deterministic, fail-closed plan for later FFmpeg sampling."""
    if (type(width) is not int or type(height) is not int or
            not 1 <= width <= 8192 or not 1 <= height <= 8192 or
            type(duration) not in (int, float) or not math.isfinite(duration) or
            not 0 < duration <= 3600):
        raise ValueError('Invalid recording metadata')
    if type(layout) is not dict or type(layout.get('schema_version')) is not int or layout['schema_version'] != 1:
        raise ValueError('Invalid layout version')
    if layout.get('layout') == 'grid':
        if set(layout) != {'schema_version', 'layout', 'rows', 'columns'}:
            raise ValueError('Unexpected grid fields')
        rows, cols = layout['rows'], layout['columns']
        if type(rows) is not int or type(cols) is not int or not 1 <= rows * cols <= 4:
            raise ValueError('Grid must contain 1–4 tables')
        regions = grid_regions(width, height, rows, cols)
    elif layout.get('layout') == 'manual':
        items = layout.get('regions')
        if set(layout) != {'schema_version', 'layout', 'regions'} or type(items) is not list or not 1 <= len(items) <= 4:
            raise ValueError('Invalid manual layout')
        regions = []
        for item in items:
            if (type(item) is not dict or set(item) != {'table_id', 'x', 'y', 'width', 'height'} or
                    any(type(v) is not int for v in item.values()) or not 1 <= item['table_id'] <= 4):
                raise ValueError('Invalid manual region')
            regions.append(Region(**item))
    else:
        raise ValueError('Unknown layout')
    validate_regions(regions, width, height)
    if type(sample_times) is not list or not 1 <= len(sample_times) <= 8:
        raise ValueError('Require 1–8 sample times')
    previous = -1.0
    for t in sample_times:
        if type(t) not in (int, float) or not math.isfinite(t) or not previous < t < duration:
            raise ValueError('Sample times must be ordered, finite and within recording')
        previous = t
    canonical = json.dumps(layout, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return {'schema_version': 1, 'analysis_status': STATUS,
            'layout_sha256': hashlib.sha256(canonical).hexdigest(),
            'recording': {'width': width, 'height': height, 'duration_seconds': float(duration)},
            'regions': [vars(r) for r in sorted(regions, key=lambda r: r.table_id)],
            'requested_seek_seconds': [float(t) for t in sample_times],
            'timestamp_semantics': 'requested_seconds_not_decoded_pts',
            'regions_human_confirmed': False, 'cards_actions_verified': False,
            'ready_for_equity_or_ev': False, 'automatic_clip_selection_authorized': False,
            'warning': 'Geometric/manual regions are not detected poker tables; no OCR or hand facts.'}
