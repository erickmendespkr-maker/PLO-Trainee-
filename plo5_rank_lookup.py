"""Read-only PLO5 P5RANK01 shard catalog; exact absolute rank, never GTO."""
from bisect import bisect_right
from collections import OrderedDict
import hashlib
import json
import mmap
from pathlib import Path
import re
import struct
import tempfile
import os

HEADER = struct.Struct('<8sQQQQ')
LIMITS = {3: 1800975787, 4: 78124329712, 5: 3337988096872}
SCHEMA = 'P5RANK01/catalog-v1'
INDEX = 'canonical-matrix-v1'
RANK = 'five-card-high-7462-v1'


def _bounds(street, start, count):
    if (type(street) is not int or street not in LIMITS or
            type(start) is not int or type(count) is not int or
            start < 0 or not 1 <= count <= 10000000 or
            start + count > LIMITS[street]):
        raise ValueError('invalid shard interval')


def _name(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.bin', name):
        raise ValueError('invalid shard filename')
    return name


def _header(mm):
    if len(mm) < HEADER.size:
        raise ValueError('truncated header')
    magic, street, start, count, checksum = HEADER.unpack_from(mm)
    if magic != b'P5RANK01':
        raise ValueError('incompatible format')
    _bounds(street, start, count)
    if len(mm) != HEADER.size + 2 * count:
        raise ValueError('wrong shard length')
    return street, start, count, checksum


def _validate_original(mm):
    street, start, count, checksum = _header(mm)
    # Original FNV-1a covers header fields 8..31 and payload, not magic/checksum.
    h = 14695981039346656037
    for block in (mm[8:32], mm[40:]):
        for v in block:
            h = ((h ^ v) * 1099511628211) & 0xffffffffffffffff
    if h != checksum:
        raise ValueError('FNV checksum mismatch')
    if any(not 1 <= v <= 7462 for (v,) in struct.iter_unpack('<H', mm[40:])):
        raise ValueError('rank outside 1..7462')
    return street, start, count


def _catalog(entries):
    groups = {s: [] for s in LIMITS}
    names = set()
    for e in entries:
        if set(e) != {'file', 'street', 'start', 'count', 'sha256'}:
            raise ValueError('invalid catalog entry')
        name = _name(e['file'])
        if name in names:
            raise ValueError('duplicate filename')
        names.add(name)
        _bounds(e['street'], e['start'], e['count'])
        if not isinstance(e['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', e['sha256']):
            raise ValueError('invalid SHA-256')
        groups[e['street']].append(e)
    for group in groups.values():
        group.sort(key=lambda e: e['start'])
        if any(a['start'] + a['count'] > b['start'] for a, b in zip(group, group[1:])):
            raise ValueError('overlapping intervals')
    return groups


def build_catalog(directory, filenames, output='rank_catalog.json'):
    """Validate original shards once and atomically write the manifest. No overwrite."""
    root = Path(directory)
    if Path(output).name != output or not output.endswith('.json'):
        raise ValueError('invalid catalog filename')
    dest = root / output
    if dest.exists():
        raise FileExistsError(dest)
    entries = []
    for name in filenames:
        name = _name(name)
        with (root / name).open('rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            street, start, count = _validate_original(mm)
            entries.append(dict(file=name, street=street, start=start, count=count,
                                sha256=hashlib.sha256(mm).hexdigest()))
    groups = _catalog(entries)
    data = dict(schema=SCHEMA, index=INDEX, rank=RANK,
                shards=[e for s in LIMITS for e in groups[s]])
    # Publish using a no-overwrite hard link, same directory; no half-written manifest.
    fd, tmp = tempfile.mkstemp(dir=root, prefix='.catalog-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.link(tmp, dest)
    finally:
        os.unlink(tmp)
    return dest


class RankLookup:
    """Single-thread reader with bounded mmap LRU; use only immutable shards/catalog."""
    def __init__(self, catalog, max_open=4):
        if type(max_open) is not int or max_open < 1:
            raise ValueError('max_open must be positive')
        path = Path(catalog)
        self.root = path.parent
        data = json.loads(path.read_text(encoding='utf-8'))
        if (data.get('schema'), data.get('index'), data.get('rank')) != (SCHEMA, INDEX, RANK):
            raise ValueError('incompatible catalog version')
        self.groups = _catalog(data['shards'])
        self.starts = {s: [e['start'] for e in g] for s, g in self.groups.items()}
        self.max_open = max_open
        self.maps = OrderedDict()
        self.closed = False

    def coverage(self):
        return {s: sum(e['count'] for e in group) for s, group in self.groups.items()}

    def _open(self, e):
        name = e['file']
        if name in self.maps:
            self.maps.move_to_end(name)
            return self.maps[name]
        with (self.root / name).open('rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            if _header(mm)[:3] != (e['street'], e['start'], e['count']):
                raise ValueError('catalog/header mismatch')
            if hashlib.sha256(mm).hexdigest() != e['sha256']:
                raise ValueError('SHA-256 mismatch')
        except BaseException:
            mm.close()
            raise
        if len(self.maps) >= self.max_open:
            self.maps.popitem(last=False)[1].close()
        self.maps[name] = mm
        return mm

    def lookup(self, street, index):
        if self.closed:
            raise RuntimeError('reader closed')
        if type(street) is not int or street not in LIMITS or type(index) is not int or not 0 <= index < LIMITS[street]:
            raise ValueError('invalid street/index')
        i = bisect_right(self.starts[street], index) - 1
        if i < 0:
            return None
        e = self.groups[street][i]
        if index >= e['start'] + e['count']:
            return None
        mm = self._open(e)
        rank = struct.unpack_from('<H', mm, HEADER.size + 2 * (index - e['start']))[0]
        if not 1 <= rank <= 7462:
            raise ValueError('rank outside 1..7462')
        return rank

    def close(self):
        for mm in self.maps.values():
            mm.close()
        self.maps.clear()
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
