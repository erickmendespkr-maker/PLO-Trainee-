"""Offline-only deterministic crop planner for recorded multi-table footage.

Coordinates are explicit and must be reviewed; no table detection is claimed.
"""
import math


def crop_filter(frame_width, frame_height, region):
    """Validate a pixel ROI and return a safe FFmpeg crop filter expression."""
    if any(type(v) is not int or v <= 0 for v in (frame_width, frame_height)):
        raise ValueError('frame dimensions must be positive integers')
    if not isinstance(region, dict) or set(region) != {'x', 'y', 'width', 'height'}:
        raise ValueError('region requires x, y, width, height')
    if any(type(region[k]) is not int for k in region):
        raise ValueError('crop coordinates must be integers')
    x, y, w, h = (region[k] for k in ('x', 'y', 'width', 'height'))
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x+w > frame_width or y+h > frame_height:
        raise ValueError('crop outside source frame')
    if any(v % 2 for v in (x, y, w, h)):
        raise ValueError('crop coordinates must be even for yuv420p encoding')
    return f'crop={w}:{h}:{x}:{y}'


def table_crop_filters(frame_width, frame_height, regions):
    """Map at most four table IDs to crop filters, rejecting overlapping ROIs."""
    if not isinstance(regions, dict) or not 1 <= len(regions) <= 4:
        raise ValueError('expected one to four table regions')
    if any(type(table_id) is not int or not 1 <= table_id <= 4 for table_id in regions):
        raise ValueError('invalid table ID')
    filters = {}
    for table_id, roi in regions.items():
        filters[table_id] = crop_filter(frame_width, frame_height, roi)
    ids = sorted(regions)
    for i, first in enumerate(ids):
        a = regions[first]
        for second in ids[i+1:]:
            b = regions[second]
            if a['x'] < b['x']+b['width'] and b['x'] < a['x']+a['width'] and a['y'] < b['y']+b['height'] and b['y'] < a['y']+a['height']:
                raise ValueError('overlapping table regions')
    return dict(sorted(filters.items()))
