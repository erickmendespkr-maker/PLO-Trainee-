"""Deterministic table-region coordinates for offline four-table recordings.

This module only assigns regions. It does not claim to detect poker tables.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    table_id: int
    x: int
    y: int
    width: int
    height: int


def grid_regions(frame_width: int, frame_height: int, rows: int = 2, columns: int = 2):
    """Partition a recording into non-overlapping regions, covering all pixels."""
    if not all(isinstance(v, int) for v in (frame_width, frame_height, rows, columns)):
        raise TypeError("Dimensions and grid counts must be integers")
    if min(frame_width, frame_height, rows, columns) <= 0:
        raise ValueError("Dimensions and grid counts must be positive")
    if frame_width < columns or frame_height < rows:
        raise ValueError("Grid cannot exceed frame dimensions")
    result = []
    for row in range(rows):
        y0 = row * frame_height // rows
        y1 = (row + 1) * frame_height // rows
        for col in range(columns):
            x0 = col * frame_width // columns
            x1 = (col + 1) * frame_width // columns
            result.append(Region(row * columns + col + 1, x0, y0, x1 - x0, y1 - y0))
    return result


def validate_regions(regions, frame_width: int, frame_height: int):
    """Validate manual table bounding boxes and reject overlaps."""
    ids = set()
    for r in regions:
        if r.table_id in ids:
            raise ValueError("Duplicate table ID")
        ids.add(r.table_id)
        if min(r.x, r.y) < 0 or min(r.width, r.height) <= 0:
            raise ValueError("Invalid region")
        if r.x + r.width > frame_width or r.y + r.height > frame_height:
            raise ValueError("Region outside frame")
    for i, a in enumerate(regions):
        for b in regions[i + 1:]:
            if a.x < b.x + b.width and b.x < a.x + a.width and a.y < b.y + b.height and b.y < a.y + a.height:
                raise ValueError("Overlapping table regions")
    return True
