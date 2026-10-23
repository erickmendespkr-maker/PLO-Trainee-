"""Export *human-selected* neutral PLO5/PLO6 review clips from recorded video.

This bridges the activity decision queue and its manually validated editor draft
with the existing FFmpeg table cropper. It does NOT use hypothetical EV to rank
hands, assert poker mistakes, validate OCR contents, or authorize live analysis.
The original video bytes are SHA-256 pinned and checked again after encoding.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import tempfile

from activity_review_editor import validate_draft
from activity_snapshot_chain import canonical_sha256
from clip_planner import ReviewCandidate, select_clips
from table_crop import crop_table_clip
from table_regions import Region, validate_regions
from video_validator import validate_recording
from video_segments import probe_video

STATUS = 'explicit_human_clip_selection_no_ev'
_FIELDS = {'schema_version', 'analysis_status', 'source_queue_sha256',
           'source_draft_sha256', 'recording_sha256', 'regions', 'selections',
           'seconds_before', 'seconds_after', 'max_clips', 'regions_human_confirmed'}
_SELECTION_FIELDS = {'table_id', 'hand_id', 'event_index', 'decision_timestamp',
                     'reviewer_approved', 'reviewer_priority', 'explanation'}
_REGION_FIELDS = {'table_id', 'x', 'y', 'width', 'height'}


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _number(value, name, lower=0, upper=None):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < lower or (upper is not None and value > upper)):
        raise ValueError(f'Invalid {name}')
    return float(value)


def build_review_clip_plan(video_path, queue, draft, selection):
    """Validate every human selection and return a *neutral*, EV-blocked plan.

    The reviewed action's confidence is subjective and is never treated as a
    calibrated probability of strategic correctness. Manual priority controls
    sorting, not modeled monetary impact.
    """
    info = validate_recording(video_path)
    if (not isinstance(queue, dict) or not isinstance(draft, dict)
            or not isinstance(selection, dict) or set(selection) != _FIELDS
            or selection['schema_version'] != 1 or selection['analysis_status'] != STATUS):
        raise ValueError('Invalid human clip selection schema')
    if (queue.get('ready_for_equity_or_ev') is not False
            or draft.get('ready_for_equity_or_ev') is not False
            or draft.get('source_visual_content_verified') is not False):
        raise ValueError('Review must remain EV-blocked and unverified')
    # Checks the complete queue identity, draft identity, typed fields, and
    # protection of all non-editable editor fields.
    validate_draft(queue, draft)
    queue_hash, draft_hash = canonical_sha256(queue), canonical_sha256(draft)
    if (selection['source_queue_sha256'] != queue_hash
            or selection['source_draft_sha256'] != draft_hash):
        raise ValueError('Queue or draft SHA-256 mismatch')
    video_hash = _file_sha256(video_path)
    if (selection['recording_sha256'] != video_hash
            or queue.get('recording_sha256') != video_hash
            or draft.get('recording_sha256') != video_hash):
        raise ValueError('Recording SHA-256 mismatch')

    if selection['regions_human_confirmed'] is not True:
        raise ValueError('Manual confirmation of table crop regions required')
    raw_regions = selection['regions']
    if not isinstance(raw_regions, list) or not 1 <= len(raw_regions) <= 4:
        raise ValueError('Require 1 to 4 manual table regions')
    regions = []
    for row in raw_regions:
        if (not isinstance(row, dict) or set(row) != _REGION_FIELDS
                or any(type(row[k]) is not int for k in _REGION_FIELDS)):
            raise ValueError('Invalid table region coordinates')
        if not 1 <= row['table_id'] <= 4:
            raise ValueError('Invalid table ID')
        regions.append(Region(**row))
    validate_regions(regions, info['width'], info['height'])
    region_by_table = {r.table_id: r for r in regions}

    before = _number(selection['seconds_before'], 'seconds_before', upper=60)
    after = _number(selection['seconds_after'], 'seconds_after', lower=.01, upper=60)
    max_clips = selection['max_clips']
    if type(max_clips) is not int or not 1 <= max_clips <= 20:
        raise ValueError('Invalid max_clips')
    raw = selection['selections']
    if not isinstance(raw, list) or not 1 <= len(raw) <= 100:
        raise ValueError('Require 1 to 100 explicit selections')
    entries = {(x['table_id'], x['hand_id'], x['event_index']): x for x in draft['entries']}
    candidates, lookup, seen = [], {}, set()
    for item in raw:
        if not isinstance(item, dict) or set(item) != _SELECTION_FIELDS:
            raise ValueError('Invalid selection fields')
        table, hand, index = item['table_id'], item['hand_id'], item['event_index']
        if (type(table) is not int or type(index) is not int or not isinstance(hand, str)
                or not hand or len(hand) > 200):
            raise ValueError('Invalid selection identity')
        key = (table, hand, index)
        if key not in entries or key in seen or table not in region_by_table:
            raise ValueError('Unknown, duplicate, or unconfigured selection')
        seen.add(key)
        entry = entries[key]
        timestamp = _number(item['decision_timestamp'], 'decision_timestamp',
                            upper=info['duration_seconds'])
        if abs(timestamp - entry['decision_timestamp']) > 1e-6:
            raise ValueError('Decision PTS mismatch')
        if item['reviewer_approved'] is not True:
            raise ValueError('Human clip approval required')
        priority = _number(item['reviewer_priority'], 'reviewer_priority', upper=1)
        explanation = item['explanation']
        if (not isinstance(explanation, str) or not explanation.strip()
                or len(explanation) > 500):
            raise ValueError('Explicit, bounded human explanation required')
        action = entry['reviewed_fields']['observed_action']
        if action['human_confirmed'] is not True or action['value'] not in ('fold', 'call', 'raise'):
            raise ValueError('Manually confirmed action required for neutral clip')
        confidence = _number(action['confidence'], 'action confidence', upper=1)
        _number(action['source_timestamp'], 'action source PTS', upper=timestamp)
        label = (f'Revisão humana do evento {index} ({action["value"]}): '
                 f'{explanation.strip()} [sem conclusão de erro]')
        candidate = ReviewCandidate(table, hand, timestamp, priority, confidence,
                                    label, 'Seleção manual, sem equity/EV e sem validação visual automática.')
        candidates.append(candidate)
        lookup[label] = {'event_index': index, 'decision_timestamp': timestamp,
                         'reviewed_action': action['value'], 'reviewer_priority': priority,
                         'subjective_action_confidence': confidence}
    clips = select_clips(candidates, video_duration=info['duration_seconds'],
                         min_confidence=0, max_clips=max_clips,
                         seconds_before=before, seconds_after=after)
    selected = []
    for clip in clips:
        metadata = lookup[clip['explanation']]
        selected.append({'table_id': clip['table_id'], 'hand_id': clip['hand_id'],
                         'start': clip['start'], 'end': clip['end'],
                         'explanation': clip['explanation'], **metadata})
    return {
        'schema_version': 1,
        'analysis_status': 'human_selected_neutral_review_clips_not_video_verified',
        'source_queue_sha256': queue_hash, 'source_draft_sha256': draft_hash,
        'source_selection_sha256': canonical_sha256(selection),
        'recording_sha256': video_hash,
        'video': {'filename': Path(video_path).name, **info},
        'regions': [asdict(r) for r in regions],
        'clips': selected,
        'selected_total_seconds': sum(c['end'] - c['start'] for c in selected),
        'ready_for_equity_or_ev': False, 'authorized_for_ev_based_ranking': False,
        'source_visual_content_verified': False,
        'warning': ('Clips are explicitly chosen by a human and not ranked by equity/EV. '
                    'The recording hash checks byte identity, not the truth of card/action labels. '
                    'No objective strategic error is established.'),
    }


def export_review_clips(video_path, queue_path, draft_path, selection_path, output_dir):
    """Encode clips in a temporary folder, then atomically publish a NEW folder."""
    paths = [Path(p) for p in (video_path, queue_path, draft_path, selection_path)]
    output = Path(output_dir)
    if (output.exists() or output.is_symlink() or
            any(output.resolve() == path.resolve() for path in paths)):
        raise ValueError('Output directory must be new and distinct from inputs')
    queue, draft, selection = (json.loads(path.read_text(encoding='utf-8'))
                               for path in paths[1:])
    plan = build_review_clip_plan(paths[0], queue, draft, selection)
    regions = {r['table_id']: Region(**r) for r in plan['regions']}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.plo_clips_', dir=output.parent) as temp:
        stage = Path(temp)
        generated = []
        for number, clip in enumerate(plan['clips'], 1):
            filename = f'review_{number:03d}_table_{clip["table_id"]}.mp4'
            destination = stage / filename
            crop_table_clip(paths[0], destination, regions[clip['table_id']],
                            plan['video']['width'], plan['video']['height'],
                            clip['start'], clip['end'])
            actual = probe_video(destination)
            if (not 0 < actual['duration'] <= clip['end'] - clip['start'] + .5
                    or actual['width'] != regions[clip['table_id']].width
                    or actual['height'] != regions[clip['table_id']].height):
                raise ValueError('Unexpected encoded clip dimensions or duration')
            generated.append({**clip, 'filename': filename,
                              'mp4_sha256': _file_sha256(destination),
                              'mp4_size_bytes': destination.stat().st_size,
                              'decoded_output': actual})
        if _file_sha256(paths[0]) != plan['recording_sha256']:
            raise ValueError('Recording changed during export')
        result = {**plan, 'clips': generated, 'clips_generated': len(generated)}
        (stage / 'review_clip_manifest.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
            encoding='utf-8')
        if output.exists() or output.is_symlink():
            raise ValueError('Output directory already exists')
        stage.rename(output)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'queue', 'draft', 'selection', 'output_dir'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    result = export_review_clips(args.video, args.queue, args.draft,
                                 args.selection, args.output_dir)
    print(json.dumps({'clips': result['clips_generated'],
                      'status': result['analysis_status']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
