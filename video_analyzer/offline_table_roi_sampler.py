"""Generate *unverified* FFmpeg/Tesseract sample ROIs from human-declared table geometry.

Usage: python offline_table_roi_sampler.py VIDEO PLAN.json TEMPLATE.json NEW_SAMPLES.json NEW_PREVIEW.png

The user declares every table rectangle and every field rectangle inside its table.
The program composes normalized coordinates, samples reviewed hand intervals, and
renders a visual alignment preview. It does NOT detect cards, hands or actions,
confirm OCR, or enable equity. Review the preview before running OCR.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import tempfile

import offline_ffmpeg_tesseract_proposals as extractor
import offline_ocr_review_bridge as bridge
import offline_reviewed_hand_math_queue as queue

MAX_FIELDS_PER_TABLE = 32
MAX_FRACTIONS = 5


def rect(rectangle, name):
    queue.require(type(rectangle) is dict and set(rectangle) == {'x', 'y', 'w', 'h'} and
                  all(bridge.number(rectangle.get(k), 0, 1) for k in ('x', 'y', 'w', 'h')) and
                  rectangle['w'] > 0 and rectangle['h'] > 0 and
                  rectangle['x'] + rectangle['w'] <= 1 + 1e-9 and
                  rectangle['y'] + rectangle['h'] <= 1 + 1e-9,
                  'invalid ' + name + ' rectangle')
    return rectangle


def compose(table, field):
    return {k: (table[k] + table['w' if k == 'x' else 'h'] * field[k]
                if k in ('x', 'y') else table[k] * field[k])
            for k in ('x', 'y', 'w', 'h')}


def overlap(a, b):
    return (min(a['x'] + a['w'], b['x'] + b['w']) > max(a['x'], b['x']) + 1e-9 and
            min(a['y'] + a['h'], b['y'] + b['h']) > max(a['y'], b['y']) + 1e-9)


def validate_template(template, clips, width, height):
    queue.require(type(template) is dict and set(template) ==
                  {'schema_version', 'status', 'fractions', 'tables'} and
                  template['schema_version'] == 1 and
                  template['status'] == 'human_declared_table_geometry_unverified' and
                  type(template['fractions']) is list and
                  1 <= len(template['fractions']) <= MAX_FRACTIONS and
                  all(bridge.number(f, .01, .99) for f in template['fractions']) and
                  len(set(template['fractions'])) == len(template['fractions']) and
                  template['fractions'] == sorted(template['fractions']) and
                  type(template['tables']) is list and
                  1 <= len(template['tables']) <= 4,
                  'invalid table template or sample fractions')
    table_ids = {clip['table_id'] for clip in clips.values()}
    tables = {}
    for entry in template['tables']:
        queue.require(type(entry) is dict and set(entry) == {'table_id', 'roi', 'fields'} and
                      type(entry['table_id']) is str and entry['table_id'] in table_ids and
                      entry['table_id'] not in tables and
                      type(entry['fields']) is list and
                      1 <= len(entry['fields']) <= MAX_FIELDS_PER_TABLE,
                      'invalid table template entry')
        table = rect(entry['roi'], 'table')
        extractor.pixel_crop(table, width, height)
        for other in tables.values():
            queue.require(not overlap(table, other['roi']), 'overlapping table rectangles')
        keys = set()
        for field in entry['fields']:
            queue.require(type(field) is dict and set(field) == {'field', 'slot', 'roi'} and
                          type(field['field']) is str and field['field'] in bridge.FIELDS,
                          'invalid field template')
            kind, slot = field['field'], field['slot']
            if kind in ('hero_card', 'board_card'):
                queue.require(type(slot) is int and 0 <= slot < (6 if kind == 'hero_card' else 5),
                              'invalid card slot')
            else:
                queue.require(slot is None, 'non-card field must have null slot')
            key = (kind, slot)
            queue.require(key not in keys, 'duplicate field/slot template')
            keys.add(key)
            local = rect(field['roi'], 'field')
            extractor.pixel_crop(compose(table, local), width, height)
        tables[entry['table_id']] = entry
    queue.require(set(tables) == table_ids, 'template must cover all reviewed tables')
    return tables


def build(plan, template, width, height, duration):
    clips = queue.validate_plan(plan)
    tables = validate_template(template, clips, width, height)
    samples = []
    for hand_id, clip in sorted(clips.items(), key=lambda item:
                                (item[1]['start_seconds'], item[1]['table_id'], item[0])):
        start, end = clip['start_seconds'], clip['end_seconds']
        queue.require(end <= duration + 1e-6, 'reviewed hand exceeds video duration')
        table = tables[clip['table_id']]
        for fraction in template['fractions']:
            pts = start + (end - start) * fraction
            queue.require(pts < duration, 'sample exceeds video duration')
            for field in table['fields']:
                samples.append({'hand_id': hand_id, 'table_id': clip['table_id'],
                                'field': field['field'], 'slot': field['slot'],
                                'pts_seconds': pts,
                                'roi': compose(table['roi'], field['roi'])})
    queue.require(len(samples) <= extractor.MAX_SAMPLES,
                  'too many samples for offline OCR limit')
    spec = {'schema_version': 1, 'status': 'human_declared_offline_roi_samples',
            'samples': samples}
    extractor.validate_spec(spec, clips, duration)
    return spec


def preview(video, template, width, height, timestamp, path):
    """Create one annotated *geometry-only* frame; no OCR or semantic verification."""
    from PIL import Image, ImageDraw, ImageFont
    with tempfile.TemporaryDirectory(prefix='plo_roi_preview_') as directory:
        frame = Path(directory) / 'frame.png'
        extractor.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                       '-ss', str(timestamp), '-i', str(video), '-map', '0:v:0',
                       '-frames:v', '1', '-y', str(frame)], 60)
        queue.require(frame.is_file() and frame.stat().st_size > 0, 'preview frame missing')
        with Image.open(frame) as original:
            queue.require(original.size == (width, height), 'preview geometry mismatch')
            image = original.convert('RGB')
        draw = ImageDraw.Draw(image)
        for table in template['tables']:
            x, y, w, h = extractor.pixel_crop(table['roi'], width, height)
            draw.rectangle((x, y, x + w - 1, y + h - 1), outline='#ffb000', width=3)
            draw.text((x + 4, y + 4), table['table_id'], fill='#ffb000')
            for field in table['fields']:
                fx, fy, fw, fh = extractor.pixel_crop(
                    compose(table['roi'], field['roi']), width, height)
                draw.rectangle((fx, fy, fx + fw - 1, fy + fh - 1),
                               outline='#00ff9f', width=2)
                label = field['field'] + ('' if field['slot'] is None else ':' + str(field['slot']))
                draw.text((fx + 2, fy + 2), label, fill='#00ff9f',
                          stroke_width=1, stroke_fill='#000000')
        image.save(path, format='PNG')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'plan_json', 'template_json', 'new_samples_json', 'new_preview_png'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    video, plan_path, template_path, spec_path, preview_path = map(Path,
        (args.video, args.plan_json, args.template_json,
         args.new_samples_json, args.new_preview_png))
    paths = (video, plan_path, template_path, spec_path, preview_path)
    queue.require(len({p.resolve() for p in paths}) == 5 and
                  spec_path.suffix.lower() == '.json' and
                  preview_path.suffix.lower() == '.png' and
                  all(p.parent.is_dir() and not p.parent.is_symlink() and
                      not p.exists() and not p.is_symlink()
                      for p in (spec_path, preview_path)),
                  'outputs must be distinct new JSON/PNG files')
    queue.require(video.is_file() and not video.is_symlink() and
                  video.suffix.lower() in ('.mp4', '.webm') and
                  0 < video.stat().st_size <= extractor.MAX_VIDEO_BYTES,
                  'invalid local video')
    input_hashes = [queue.digest(p) for p in (video, plan_path, template_path)]
    plan, template = queue.read(plan_path), queue.read(template_path)
    queue.require(input_hashes[0] == plan.get('source_video_sha256'),
                  'video SHA-256 differs from reviewed plan')
    width, height, duration = extractor.probe(video)
    spec = build(plan, template, width, height, duration)
    clips = queue.validate_plan(plan)
    timestamp = min(clip['start_seconds'] for clip in clips.values()) + .05
    written = []
    try:
        # Exclusive creation; never overwrite existing output.
        with preview_path.open('xb') as out:
            written.append(preview_path)
            with tempfile.TemporaryDirectory(prefix='plo_roi_render_') as directory:
                temp = Path(directory) / 'preview.png'
                preview(video, template, width, height, timestamp, temp)
                out.write(temp.read_bytes())
        queue.require(input_hashes == [queue.digest(p) for p in
                      (video, plan_path, template_path)], 'inputs changed during sampling')
        with spec_path.open('x', encoding='utf-8') as out:
            written.append(spec_path)
            json.dump(spec, out, indent=2, ensure_ascii=False, allow_nan=False)
            out.write('\n')
    except Exception:
        for p in written:
            p.unlink(missing_ok=True)
        raise
    print(json.dumps({'unverified_samples': len(spec['samples']),
                      'reviewed_tables': len(template['tables']),
                      'preview_geometry_only': str(preview_path),
                      'eligible_for_equity': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
