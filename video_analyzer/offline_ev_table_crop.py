"""Offline table-region MP4 export from an audited conditional-EV batch.

Usage: python offline_ev_table_crop.py VIDEO.mp4 BATCH_OUTPUT_DIR LAYOUT.json OUTPUT_DIR

Layout schema v1: {"schema_version":1,"status":"manual_offline_table_regions_unverified",
"source_video_sha256":"<sha256>","regions":[{"table_id":"T1","x":0,"y":0,
"width":320,"height":240}, ...]}. Regions are manual hypotheses, not detections.
No live capture, poker clients, betting, or automatic OCR authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
HEX = re.compile(r'[a-f0-9]{64}\Z')
MAX_JSON = 5_000_000
MAX_CLIPS = 20
MAX_VIDEO_SECONDS = 7200


def check(ok, message):
    if not ok:
        raise ValueError(message)


def safe_file(path, *, json_file=False):
    path = Path(path)
    check(path.is_file() and not path.is_symlink(), f'unsafe or missing file: {path.name}')
    if json_file:
        check(path.stat().st_size <= MAX_JSON, 'JSON too large')
    return path


def digest(path):
    h = hashlib.sha256()
    with safe_file(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    safe_file(path, json_file=True)
    def unique_pairs(pairs):
        out = {}
        for k, v in pairs:
            check(k not in out, 'duplicate JSON key')
            out[k] = v
        return out
    def reject_constant(value):
        raise ValueError(f'nonfinite JSON value: {value}')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_pairs,
                      parse_constant=reject_constant)


def media_info(path):
    p = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                        '-show_entries', 'stream=width,height:format=duration',
                        '-of', 'json', str(path)], capture_output=True, text=True,
                       timeout=30, check=True)
    info = json.loads(p.stdout)
    check(len(info.get('streams', [])) == 1, 'video stream missing')
    stream = info['streams'][0]
    w, h = stream['width'], stream['height']
    d = float(info['format']['duration'])
    check(type(w) is int and type(h) is int and 2 <= w <= 16384 and 2 <= h <= 16384
          and math.isfinite(d) and 0.5 <= d <= MAX_VIDEO_SECONDS, 'invalid media dimensions/duration')
    return w, h, d


def validate(video, batch_dir, layout_file, output_dir):
    video, batch_dir, layout_file, output_dir = map(Path, (video, batch_dir, layout_file, output_dir))
    check(video.suffix.lower() in ('.mp4', '.mov', '.webm'), 'unsupported video extension')
    safe_file(video)
    check(batch_dir.is_dir() and not batch_dir.is_symlink() and
          output_dir.is_dir() and not output_dir.is_symlink(), 'unsafe input/output directory')
    check(len({p.resolve() for p in (video, batch_dir, layout_file, output_dir)}) == 4,
          'inputs and output must be distinct')
    w, h, duration = media_info(video)
    video_sha = digest(video)
    layout = read_json(layout_file)
    check(type(layout) is dict and set(layout) == {'schema_version', 'status', 'source_video_sha256', 'regions'}
          and type(layout['schema_version']) is int and layout['schema_version'] == 1
          and layout['status'] == 'manual_offline_table_regions_unverified'
          and layout['source_video_sha256'] == video_sha
          and type(layout['regions']) is list and 1 <= len(layout['regions']) <= 4,
          'invalid layout or source hash')
    regions = {}
    for item in layout['regions']:
        check(type(item) is dict and set(item) == {'table_id', 'x', 'y', 'width', 'height'},
              'invalid region schema')
        table = item['table_id']
        check(type(table) is str and ID.fullmatch(table) and table not in regions,
              'invalid or repeated table ID')
        x, y, rw, rh = (item[k] for k in ('x', 'y', 'width', 'height'))
        check(all(type(v) is int for v in (x, y, rw, rh)) and x >= 0 and y >= 0
              and rw >= 2 and rh >= 2 and rw % 2 == 0 and rh % 2 == 0
              and x + rw <= w and y + rh <= h, 'invalid/out-of-bounds crop')
        regions[table] = item
    batch_path = batch_dir / 'batch_report.json'
    batch = read_json(batch_path)
    check(type(batch) is dict and batch.get('schema_version') == 1
          and batch.get('status') == 'offline_conditional_ev_batch_unverified_not_strategy_verdict'
          and batch.get('automatic_ocr_math_authorization') is False
          and batch.get('source_video_sha256') == video_sha
          and type(batch.get('clips')) is list and len(batch['clips']) <= MAX_CLIPS
          and type(batch.get('rendered_count')) is int
          and batch['rendered_count'] == len(batch['clips']), 'invalid batch ledger')
    check(not (output_dir / 'crop_batch_report.json').exists() and
          not (output_dir / 'crop_batch_report.json').is_symlink(), 'output report exists')
    inputs = [(video, video_sha), (layout_file, digest(layout_file)), (batch_path, digest(batch_path))]
    plans = []
    used = set()
    for item in batch['clips']:
        check(type(item) is dict, 'invalid clip entry')
        cid, table = item.get('clip_id'), item.get('table_id')
        check(type(cid) is str and ID.fullmatch(cid) and cid not in used
              and type(table) is str and table in regions, 'missing table region or unsafe clip ID')
        used.add(cid)
        mp4_name, report_name = cid + '.mp4', cid + '.json'
        check(item.get('clip_filename') == mp4_name and
              item.get('clip_report_filename') == report_name, 'unsafe batch filenames')
        full_clip, report_path = batch_dir / mp4_name, batch_dir / report_name
        clip_sha = digest(full_clip)
        report = read_json(report_path)
        check(item.get('clip_sha256') == clip_sha and
              report.get('rendered_clip_sha256') == clip_sha
              and report.get('status') == 'offline_conditional_ev_clip_not_strategy_verdict'
              and report.get('automatic_ocr_math_authorization') is False
              and report.get('source_video_sha256') == video_sha
              and report.get('table_id') == table and report.get('hand_id') == item.get('hand_id')
              and report.get('clip_filename') == mp4_name, 'clip provenance mismatch')
        start, length = report.get('clip_start_seconds'), report.get('clip_duration_seconds')
        check(type(start) in (int, float) and type(length) in (int, float)
              and math.isfinite(start) and math.isfinite(length)
              and 0 <= start and length >= .5 and start + length <= duration + .05
              and abs(start - item.get('clip_start_seconds', -999)) <= 1e-5
              and abs(length - item.get('clip_duration_seconds', -999)) <= 1e-5,
              'invalid clip time provenance')
        check(type(report.get('variant')) is str and report['variant'] in ('PLO5', 'PLO6', '5', '6')
              and type(report.get('street')) is str and report['street'] in ('preflop','flop','turn','river'),
              'invalid variant/street')
        for name in ('crop_' + cid + '.mp4', 'crop_' + cid + '.json'):
            check(not (output_dir / name).exists() and not (output_dir / name).is_symlink(),
                  'crop output exists')
        inputs.extend([(full_clip, clip_sha), (report_path, digest(report_path))])
        plans.append((cid, table, report, regions[table]))
    check(all(digest(p) == sha for p, sha in inputs), 'inputs changed during preflight')
    return plans, inputs, output_dir, video, w, h


def export(video, batch_dir, layout_file, output_dir):
    plans, inputs, out, video, w, h = validate(video, batch_dir, layout_file, output_dir)
    created = []
    try:
        clips = []
        for cid, table, report, region in plans:
            with tempfile.TemporaryDirectory(prefix='plo_crop_', dir=out) as folder:
                tmp = Path(folder)
                # Overlay after crop: full-frame overlays would otherwise disappear.
                text = (f"PLO {report['variant']} | {report['street']} | Mesa {table}\n"
                        f"Acao declarada: {report.get('action_taken_claim_unverified', 'incerta')}\n"
                        "EV condicional; ranges e cartas nao verificados.")
                (tmp / 'overlay.txt').write_text(text, encoding='utf-8')
                result = tmp / 'crop.mp4'
                r = region
                filt = (f"crop={r['width']}:{r['height']}:{r['x']}:{r['y']},"
                        "drawtext=textfile=overlay.txt:expansion=none:fontcolor=white:"
                        "fontsize=12:box=1:boxcolor=black@0.75:x=4:y=4")
                subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                                '-ss', f"{report['clip_start_seconds']:.6f}", '-i', str(video),
                                '-t', f"{report['clip_duration_seconds']:.6f}", '-map', '0:v:0',
                                '-vf', filt, '-an', '-c:v', 'libx264', '-preset', 'ultrafast',
                                '-crf', '28', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                                str(result)], cwd=tmp, check=True, capture_output=True,
                               text=True, timeout=180)
                cw, ch, cd = media_info(result)
                check((cw, ch) == (r['width'], r['height']) and cd >= .4,
                      'crop output dimensions/duration mismatch')
                check(all(digest(p) == sha for p, sha in inputs), 'inputs changed during export')
                filename = 'crop_' + cid + '.mp4'
                output = out / filename
                meta = {'schema_version': 1, 'status': 'offline_manual_table_crop_unverified',
                        'clip_id': cid, 'table_id': table, 'hand_id': report['hand_id'],
                        'source_video_sha256': report['source_video_sha256'],
                        'source_clip_report_sha256': digest(Path(batch_dir) / (cid + '.json')),
                        'source_layout_sha256': digest(Path(layout_file)),
                        'region_claim': region, 'source_width': w, 'source_height': h,
                        'clip_start_seconds': report['clip_start_seconds'],
                        'clip_duration_seconds_claim': report['clip_duration_seconds'],
                        'rendered_duration_seconds': cd, 'crop_filename': filename,
                        'crop_sha256': digest(result), 'automatic_ocr_math_authorization': False,
                        'warning': 'Manual table geometry and math assumptions are unverified; not a strategy verdict.'}
                meta_file = tmp / 'meta.json'
                meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False, allow_nan=False) + '\n',
                                     encoding='utf-8')
                for src, dst in ((result, output), (meta_file, out / ('crop_' + cid + '.json'))):
                    check(not dst.exists() and not dst.is_symlink(), 'crop output appeared during render')
                    os.link(src, dst)
                    created.append(dst)
                clips.append({'clip_id': cid, 'table_id': table, 'filename': filename,
                              'sha256': meta['crop_sha256'], 'metadata': 'crop_' + cid + '.json'})
        check(all(digest(p) == sha for p, sha in inputs), 'inputs changed before publishing ledger')
        ledger = {'schema_version': 1, 'status': 'offline_table_crop_batch_unverified',
                  'source_video_sha256': inputs[0][1], 'source_layout_sha256': inputs[1][1],
                  'source_batch_report_sha256': inputs[2][1], 'rendered_count': len(clips),
                  'clips': clips, 'automatic_ocr_math_authorization': False,
                  'warning': 'Table regions manually specified; no poker error verdict.'}
        with tempfile.TemporaryDirectory(prefix='plo_crop_ledger_', dir=out) as folder:
            temp = Path(folder) / 'ledger.json'
            temp.write_text(json.dumps(ledger, indent=2, ensure_ascii=False, allow_nan=False) + '\n',
                            encoding='utf-8')
            dest = out / 'crop_batch_report.json'
            check(not dest.exists() and not dest.is_symlink(), 'crop ledger output appeared')
            os.link(temp, dest)
            created.append(dest)
        return ledger
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'batch_dir', 'layout_json', 'output_dir'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    ledger = export(args.video, args.batch_dir, args.layout_json, args.output_dir)
    print(json.dumps({'status': ledger['status'], 'rendered': ledger['rendered_count']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
