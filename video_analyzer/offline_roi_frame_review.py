"""Offline multi-timestamp ROI calibration from an authorized recorded PLO session.

Usage: python offline_roi_frame_review.py VIDEO PLAN.json TEMPLATE.json FRAMES.json NEW_DIRECTORY

FRAMES.json: {"schema_version":1,"status":"human_selected_frame_timestamps_unverified",
 "frames":[{"hand_id":"H1","pts_seconds":1.5}, ...]}

Outputs a portable index and one independent offline geometry editor per frame.
Frame boundaries and ROIs are human declarations; no tracking, card recognition,
review confirmation, or equity/EV occurs. Output directory must not exist.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import shutil
import tempfile

from PIL import Image
import offline_ffmpeg_tesseract_proposals as extractor
import offline_reviewed_hand_math_queue as queue
import offline_table_roi_editor as editor
import offline_table_roi_sampler as sampler

MAX_FRAMES = 12
MAX_TOTAL_FRAME_BYTES = 64 * 1024 * 1024
STATUS = 'human_selected_frame_timestamps_unverified'


def validate_frames(spec, clips, duration):
    queue.require(type(spec) is dict and set(spec) == {'schema_version', 'status', 'frames'} and
                  type(spec['schema_version']) is int and spec['schema_version'] == 1 and
                  spec['status'] == STATUS and type(spec['frames']) is list and
                  1 <= len(spec['frames']) <= MAX_FRAMES, 'invalid frame selection')
    selected = []
    seen = set()
    for row in spec['frames']:
        queue.require(type(row) is dict and set(row) == {'hand_id', 'pts_seconds'} and
                      type(row['hand_id']) is str and row['hand_id'] in clips and
                      queue.number(row['pts_seconds'], 0, duration),
                      'invalid hand/timestamp selection')
        clip = clips[row['hand_id']]
        pts = row['pts_seconds']
        queue.require(clip['start_seconds'] <= pts < clip['end_seconds'] and
                      pts < duration - .001, 'frame timestamp outside reviewed hand/video')
        key = (row['hand_id'], pts)
        queue.require(key not in seen, 'duplicate hand/timestamp selection')
        seen.add(key)
        selected.append({'hand_id': row['hand_id'], 'table_id': clip['table_id'],
                         'pts_seconds': pts})
    return selected


def index_page(entries):
    rows = []
    for row in entries:
        hand = html.escape(row['hand_id'], quote=True)
        table = html.escape(row['table_id'], quote=True)
        stamp = format(row['pts_seconds'], '.3f')
        frame = html.escape(row['frame'], quote=True)
        edit = html.escape(row['editor'], quote=True)
        rows.append(f'<tr><td>{hand}</td><td>{table}</td><td>{stamp}s</td>'
                    f'<td><a href="{edit}">Editar regiões</a></td>'
                    f'<td><a href="{frame}">Ver quadro</a></td></tr>')
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
            '<title>PLO Trainee — quadros para revisão</title>'
            '<style>body{font:16px system-ui;background:#111827;color:#e5e7eb;'
            'max-width:1100px;margin:30px auto;padding:15px}table{width:100%;border-collapse:collapse}'
            'td,th{padding:12px;border-bottom:1px solid #374151;text-align:left}'
            'a{color:#5eead4}p{line-height:1.6}.warning{color:#fbbf24}</style></head><body>'
            '<h1>PLO Trainee · revisão offline de regiões por timestamp</h1>'
            '<p class="warning">Geometria e limites das mãos declarados manualmente. '
            'Nenhum OCR foi confirmado. Não habilita Monte Carlo nem EV.</p>'
            '<p>Abra cada editor, ajuste regiões e baixe o JSON individual. '
            'Cada quadro começa com o mesmo template inicial: ajustes não são '
            'transferidos automaticamente entre timestamps.</p>'
            '<table><thead><tr><th>Mão</th><th>Mesa</th><th>Timestamp</th>'
            '<th>Editor local</th><th>Imagem</th></tr></thead><tbody>' +
            ''.join(rows) + '</tbody></table><p>Verifique hashes no manifest.json. '
            'Sem upload, sem rede, sem rastreamento de mesas.</p></body></html>\n')


def generate(video, plan_path, template_path, frames_path, output):
    inputs = (video, plan_path, template_path, frames_path)
    queue.require(len({p.resolve() for p in (*inputs, output)}) == 5 and
                  output.parent.is_dir() and not output.parent.is_symlink() and
                  not output.exists() and not output.is_symlink() and
                  output.name not in ('.', '..'), 'output must be a new distinct directory')
    queue.require(video.is_file() and not video.is_symlink() and
                  video.suffix.lower() in ('.mp4', '.webm') and
                  0 < video.stat().st_size <= extractor.MAX_VIDEO_BYTES,
                  'invalid local video')
    before = {p.name: queue.digest(p) for p in inputs}
    queue.require(len(before) == len(inputs), 'input basenames must be distinct')
    plan, template, spec = (queue.read(p) for p in (plan_path, template_path, frames_path))
    clips = queue.validate_plan(plan)
    queue.require(plan['source_video_sha256'] == before[video.name],
                  'source video SHA-256 mismatch')
    width, height, duration = extractor.probe(video)
    sampler.validate_template(template, clips, width, height)
    selected = validate_frames(spec, clips, duration)
    stage = Path(tempfile.mkdtemp(prefix='.plo_roi_frames_', dir=output.parent))
    entries, total = [], 0
    try:
        for i, row in enumerate(selected, 1):
            name = f'frame_{i:03d}'
            png, page = stage / (name + '.png'), stage / (name + '.html')
            extractor.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                           '-ss', str(row['pts_seconds']), '-i', str(video),
                           '-map', '0:v:0', '-frames:v', '1', '-y', str(png)], 60)
            queue.require(png.is_file() and not png.is_symlink() and
                          0 < png.stat().st_size <= editor.MAX_FRAME_BYTES,
                          'invalid extracted frame')
            with Image.open(png) as img:
                queue.require(img.format == 'PNG' and img.size == (width, height),
                              'extracted frame geometry mismatch')
                img.verify()
            total += png.stat().st_size
            queue.require(total <= MAX_TOTAL_FRAME_BYTES, 'extracted frames exceed byte limit')
            page.write_text(editor.create(png, template), encoding='utf-8')
            entries.append({**row, 'frame': png.name, 'frame_sha256': queue.digest(png),
                            'editor': page.name, 'editor_sha256': queue.digest(page)})
        (stage / 'index.html').write_text(index_page(entries), encoding='utf-8')
        manifest = {'schema_version': 1,
                    'status': 'offline_multiframe_roi_geometry_unverified',
                    'source_video_sha256': before[video.name],
                    'source_plan_sha256': before[plan_path.name],
                    'source_template_sha256': before[template_path.name],
                    'source_selection_sha256': before[frames_path.name],
                    'index_sha256': queue.digest(stage / 'index.html'),
                    'frames': entries, 'eligible_for_equity': 0,
                    'ocr_confirmed': False, 'tracking_performed': False,
                    'manual_review_required': True}
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False,
                                                       allow_nan=False) + '\n', encoding='utf-8')
        queue.require(all(queue.digest(p) == before[p.name] for p in inputs),
                      'input changed during extraction')
        queue.require(not output.exists() and not output.is_symlink(),
                      'output appeared during extraction')
        # mkdir is exclusive: unlike POSIX rename it cannot replace an empty
        # directory created concurrently by another process.
        output.mkdir()
        try:
            for item in stage.iterdir():
                os.rename(item, output / item.name)
        except Exception:
            for item in stage.iterdir():
                if item.is_file():
                    item.unlink()
            # Remove only files written by this invocation.
            for item in output.iterdir():
                if item.name in {'index.html', 'manifest.json'} or item.name.startswith('frame_'):
                    item.unlink()
            output.rmdir()
            raise
        return manifest
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'plan_json', 'template_json', 'frames_json', 'new_output_directory'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    paths = [Path(getattr(args, name)) for name in
             ('video', 'plan_json', 'template_json', 'frames_json', 'new_output_directory')]
    result = generate(*paths)
    print(json.dumps({'output': str(paths[-1]), 'frames': len(result['frames']),
                      'offline': True, 'eligible_for_equity': 0,
                      'manual_review_required': True}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
