"""Create an UNAPPROVED clip-selection template from a reviewed offline session.

All proposed table grid regions and candidate clips must be checked against the
original recording. Nothing in the template is approved or mathematically ranked.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from activity_review_clip_export import STATUS, _file_sha256
from activity_review_editor import validate_draft
from activity_snapshot_chain import canonical_sha256
from table_regions import grid_regions
from video_validator import validate_recording


def build_clip_selection_template(video_path, queue, draft):
    info = validate_recording(video_path)
    validate_draft(queue, draft)
    video_hash = _file_sha256(video_path)
    if (queue.get('recording_sha256') != video_hash
            or draft.get('recording_sha256') != video_hash):
        raise ValueError('Recording SHA-256 mismatch')
    entries = draft['entries']
    if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
        raise ValueError('Require 1 to 100 decision entries')
    tables = {e['table_id'] for e in entries}
    if any(type(t) is not int or not 1 <= t <= 4 for t in tables):
        raise ValueError('Invalid table identities')
    max_table = max(tables)
    rows, columns = (1, 1) if max_table == 1 else ((1, 2) if max_table == 2 else (2, 2))
    regions = [asdict(r) for r in grid_regions(info['width'], info['height'], rows, columns)
               if r.table_id in tables]
    return {
        'schema_version': 1, 'analysis_status': STATUS,
        'source_queue_sha256': canonical_sha256(queue),
        'source_draft_sha256': canonical_sha256(draft),
        'recording_sha256': video_hash,
        'regions': regions, 'regions_human_confirmed': False,
        'selections': [{
            'table_id': e['table_id'], 'hand_id': e['hand_id'],
            'event_index': e['event_index'], 'decision_timestamp': e['decision_timestamp'],
            'reviewer_approved': False, 'reviewer_priority': None, 'explanation': '',
        } for e in entries],
        'seconds_before': 2, 'seconds_after': 3, 'max_clips': min(10, len(entries)),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('video', 'queue', 'draft', 'output_json'):
        parser.add_argument(field)
    args = parser.parse_args(argv)
    source = [Path(p) for p in (args.video, args.queue, args.draft)]
    target = Path(args.output_json)
    if target.exists() or target.is_symlink() or any(target.resolve() == p.resolve() for p in source):
        raise ValueError('Output must be a new file distinct from inputs')
    result = build_clip_selection_template(source[0],
                 json.loads(source[1].read_text(encoding='utf-8')),
                 json.loads(source[2].read_text(encoding='utf-8')))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'decisions': len(result['selections']),
                      'clips_approved': 0, 'regions_confirmed': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
