"""Validate crop manifest geometry; does not establish poker-hand correctness."""


def validate_manifest_geometry(tables, frame_width, frame_height):
    if not isinstance(tables, list) or not 1 <= len(tables) <= 4:
        raise ValueError('expected 1-4 table entries')
    if any(type(v) is not int or v <= 0 for v in (frame_width, frame_height)):
        raise ValueError('invalid source dimensions')
    rectangles = []
    ids = set()
    for table in tables:
        if not isinstance(table, dict):
            raise ValueError('invalid table entry')
        identifier = table.get('table_id')
        region = table.get('region')
        if type(identifier) is not int or identifier not in range(1, 5) or identifier in ids:
            raise ValueError('invalid table identifier')
        if not isinstance(region, dict) or set(region) != {'table_id', 'x', 'y', 'width', 'height'} or region['table_id'] != identifier:
            raise ValueError('invalid region identity or fields')
        x, y, w, h = (region[key] for key in ('x', 'y', 'width', 'height'))
        if any(type(v) is not int or v % 2 for v in (x, y, w, h)):
            raise ValueError('crop geometry must use even integer pixels')
        if x < 0 or y < 0 or w < 2 or h < 2 or x + w > frame_width or y + h > frame_height:
            raise ValueError('crop outside frame')
        for a, b, c, d in rectangles:
            if x < c and a < x + w and y < d and b < y + h:
                raise ValueError('overlapping table crops')
        rectangles.append((x, y, x + w, y + h))
        ids.add(identifier)
    return True
