"""Strict adapter from list-style table ROIs to validated FFmpeg crop filters.

No detection or poker interpretation is performed. Regions must be calibrated
externally and reviewed. This module has no live-poker integration.
"""
try:
    from .offline_table_crop_geometry import table_crop_filters
except ImportError:  # standalone test execution from video_analyzer/
    from offline_table_crop_geometry import table_crop_filters


def validated_table_regions(frame_width, frame_height, regions):
    """Return sorted ROI records and filters after checking all four-table constraints.

    Reject duplicate IDs, odd pixel coordinates, overlap, extra/missing fields,
    and out-of-frame ROIs before any output file is created.
    """
    if not isinstance(regions, list) or not 1 <= len(regions) <= 4:
        raise ValueError('expected 1-4 table regions')
    by_id = {}
    for record in regions:
        if not isinstance(record, dict) or set(record) != {'table_id', 'x', 'y', 'width', 'height'}:
            raise ValueError('invalid region fields')
        table_id = record['table_id']
        if type(table_id) is not int or not 1 <= table_id <= 4 or table_id in by_id:
            raise ValueError('invalid or duplicate table ID')
        by_id[table_id] = {key: record[key] for key in ('x', 'y', 'width', 'height')}
    filters = table_crop_filters(frame_width, frame_height, by_id)
    return [
        {'table_id': table_id, **by_id[table_id], 'ffmpeg_filter': filters[table_id]}
        for table_id in sorted(filters)
    ]
