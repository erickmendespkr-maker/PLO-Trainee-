"""Offline, unverified board-card / street candidates from a recorded PLO video.

Designed for a calibrated, fixed four-table capture. Only bright card-face
backgrounds are detected; this is NOT OCR, hand reconstruction, or GTO.

python offline_board_street_proposals.py VIDEO.mp4 CONFIG.json NEW_REPORT.json \
    --times 5,15,25,35

The JSON configuration declares 1..4 fixed table rectangles and a relative
five-card board sample strip. No network, user video upload or live integrations.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from PIL import Image

PTS_RE = re.compile(r'\bpts_time:\s*(-?\d+(?:\.\d+)?)')
MAX_VIDEO_BYTES = 8 * 1024**3
MAX_JSON_BYTES = 65536
MAX_SAMPLES = 24


def check(ok, msg):
    if not ok:
        raise ValueError(msg)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as file:
        for block in iter(lambda: file.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def unique(pairs):
    result = {}
    for k, v in pairs:
        check(k not in result, 'duplicate JSON key')
        result[k] = v
    return result


def load_config(path, width, height):
    p = Path(path)
    check(p.is_file() and not p.is_symlink() and
          0 < p.stat().st_size <= MAX_JSON_BYTES, 'unsafe config')
    cfg = json.loads(p.read_text('utf-8'), object_pairs_hook=unique,
                     parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite number')))
    check(type(cfg) is dict and set(cfg) == {'schema_version', 'slots', 'board_strip'} and
          type(cfg['schema_version']) is int and cfg['schema_version'] == 1 and
          type(cfg['slots']) is list and 1 <= len(cfg['slots']) <= 4 and
          type(cfg['board_strip']) is dict and
          set(cfg['board_strip']) == {'offset_x', 'offset_y', 'step_x', 'width', 'height',
                                     'white_min_rgb', 'min_white_fraction'},
          'invalid config schema')
    strip = cfg['board_strip']
    check(all(type(strip[k]) is int and 0 <= strip[k] <= 8192
              for k in ('offset_x', 'offset_y', 'step_x', 'width', 'height')) and
          strip['step_x'] >= strip['width'] >= 8 and strip['height'] >= 8 and
          type(strip['white_min_rgb']) is int and 170 <= strip['white_min_rgb'] <= 250 and
          type(strip['min_white_fraction']) in (int, float) and
          math.isfinite(strip['min_white_fraction']) and
          0.25 <= strip['min_white_fraction'] <= 0.90, 'invalid sample strip')
    ids = set()
    for slot in cfg['slots']:
        check(type(slot) is dict and set(slot) == {'table_id', 'x', 'y', 'width', 'height'} and
              all(type(v) is int for v in slot.values()) and
              type(slot['table_id']) is int and
              1 <= slot['table_id'] <= 4 and slot['table_id'] not in ids and
              slot['x'] >= 0 and slot['y'] >= 0 and
              slot['width'] >= 200 and slot['height'] >= 200 and
              slot['x'] + slot['width'] <= width and
              slot['y'] + slot['height'] <= height and
              strip['offset_x'] + 4*strip['step_x'] + strip['width'] <= slot['width'] and
              strip['offset_y'] + strip['height'] <= slot['height'], 'invalid table ROI')
        ids.add(slot['table_id'])
    for a in cfg['slots']:
        for b in cfg['slots']:
            if a['table_id'] >= b['table_id']:
                continue
            check(not (a['x'] < b['x']+b['width'] and b['x'] < a['x']+a['width'] and
                       a['y'] < b['y']+b['height'] and b['y'] < a['y']+a['height']),
                  'overlapping table slots')
    return cfg


def call(args, timeout=60):
    try:
        p = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                           timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('offline media tool unavailable or timed out') from exc
    check(p.returncode == 0 and len(p.stdout) <= 16*1024*1024 and
          len(p.stderr) <= 512*1024, 'offline media tool failed')
    return p


def inspect_video(video):
    info = json.loads(call(['ffprobe','-v','error','-select_streams','v:0',
        '-show_entries','stream=width,height,start_time,avg_frame_rate:format=duration',
        '-of','json',str(video)],30).stdout)
    check(type(info.get('streams')) is list and len(info['streams']) == 1,
          'no unique source video stream')
    stream = info['streams'][0]
    w, h = stream.get('width'), stream.get('height')
    try:
        duration = float(info['format']['duration'])
        origin = float(stream.get('start_time','0'))
        num, den = map(int, stream['avg_frame_rate'].split('/'))
    except (ValueError, TypeError, KeyError, ZeroDivisionError) as exc:
        raise ValueError('invalid video timing metadata') from exc
    check(type(w) is int and type(h) is int and
          640 <= w <= 8192 and 400 <= h <= 8192 and
          math.isfinite(duration) and .2 <= duration <= 5400 and
          math.isfinite(origin) and -86400 <= origin <= 86400 and
          den > 0 and .5 <= num / den <= 240, 'unsupported recording')
    return w, h, duration, origin, den/num


def sample_board(image, slot, strip):
    check(image.mode == 'RGB', 'expected RGB frame')
    fractions = []
    for k in range(5):
        x = slot['x'] + strip['offset_x'] + k*strip['step_x']
        y = slot['y'] + strip['offset_y']
        tile = image.crop((x,y,x+strip['width'],y+strip['height']))
        pixels = tile.get_flattened_data() if hasattr(tile,'get_flattened_data') else tile.getdata()
        white = sum(1 for p in pixels if min(p) >= strip['white_min_rgb'])
        fractions.append(round(white / (strip['width']*strip['height']), 4))
    flags = [v >= strip['min_white_fraction'] for v in fractions]
    count = sum(flags)
    contiguous = flags == ([True]*count+[False]*(5-count))
    # If some but not 3/4/5 bright cards appear, or cards are noncontiguous,
    # do not call it a street: shadows/overlays/calibration may be wrong.
    stage = ('no_faceup_board_detected' if count == 0 else
             {3:'flop_candidate',4:'turn_candidate',5:'river_candidate'}.get(count,'ambiguous'))
    if not contiguous:
        stage = 'ambiguous'
    return {'table_id': slot['table_id'], 'white_fraction_by_card_roi':fractions,
            'bright_card_roi_flags':flags, 'faceup_card_count_candidate':count if contiguous else None,
            'street_proposal':stage, 'verified_by_human':False,
            'board_rank_or_suit_recognized':False}


def decode_frame(video, t, origin, frame_tolerance, frame_size):
    p = call(['ffmpeg','-nostdin','-hide_banner','-loglevel','info','-ss',str(t),
        '-copyts','-i',str(video),'-map','0:v:0','-an','-sn','-dn',
        '-vf','showinfo','-frames:v','1','-f','image2pipe','-vcodec','png','-'],90)
    matches = [float(m.group(1)) for line in p.stderr.decode('utf-8','replace').splitlines()
               if 'Parsed_showinfo' in line for m in [PTS_RE.search(line)] if m]
    check(len(matches) == 1 and math.isfinite(matches[0]) and
          abs(matches[0] - (t+origin)) <= max(.25, frame_tolerance + .01),
          'unverifiable source frame PTS')
    try:
        with Image.open(io.BytesIO(p.stdout)) as frame:
            check(frame.size == frame_size and frame.format == 'PNG',
                  'decoded frame mismatch')
            img = frame.convert('RGB')
    except (OSError, ValueError) as exc:
        raise ValueError('invalid decoded frame') from exc
    return matches[0], img


def analyze(video_path, config_path, times):
    video, config = map(Path, (video_path, config_path))
    check(video.is_file() and not video.is_symlink() and
          video.suffix.lower() in ('.mp4','.webm') and
          0 < video.stat().st_size <= MAX_VIDEO_BYTES, 'invalid local recording')
    video_sha, config_sha = sha256(video), sha256(config)
    w, h, duration, origin, tolerance = inspect_video(video)
    cfg = load_config(config, w, h)
    check(type(times) is list and 2 <= len(times) <= MAX_SAMPLES and
          all(type(t) in (float,int) and math.isfinite(t) and 0 <= t < duration
              for t in times) and times == sorted(set(times)),
          'invalid strictly increasing timestamps')
    rows = []
    for t in times:
        pts, img = decode_frame(video,t,origin,tolerance,(w,h))
        rows.append({'playback_seconds_requested':float(t),
                     'source_decoded_pts_seconds':pts,
                     'tables':[sample_board(img, s, cfg['board_strip']) for s in cfg['slots']]})
    transitions = []
    for earlier, later in zip(rows, rows[1:]):
        old = {t['table_id']:t for t in earlier['tables']}
        for table in later['tables']:
            prev = old[table['table_id']]
            if table['street_proposal'] != prev['street_proposal']:
                transitions.append({'table_id':table['table_id'],
                    'between_playback_seconds':[earlier['playback_seconds_requested'],
                                                later['playback_seconds_requested']],
                    'from_street_proposal':prev['street_proposal'],
                    'to_street_proposal':table['street_proposal'],
                    'time_of_change_known':False,'hand_boundary_verified':False,
                    'street_confirmed':False,'requires_human_review':True})
    check(sha256(video)==video_sha and sha256(config)==config_sha,
          'recording or configuration changed during sampling')
    return {'schema_version':1,'analysis_status':'unverified_faceup_board_street_proposals_only',
            'source_video_sha256':video_sha,'source_config_sha256':config_sha,
            'recording':{'width':w,'height':h,'duration_seconds':duration,'frame_origin_pts_seconds':origin},
            'samples':rows,'transition_candidates':transitions,
            'hands_reconstructed':False,'cards_recognized':False,
            'actions_recognized':False,'equity_or_ev_authorized':False,
            'automatic_clip_selection_authorized':False,
            'warnings':['Face-up white card ROIs only; face-down backs/overlays may be ambiguous.',
                        'No face-up board detected does not prove a preflop state or a new hand.',
                        'Sparse sample transitions are intervals, NOT exact street change timestamps.',
                        'Independent visual validation is required before poker hand reconstruction.']}


def save_report(video, config, times, output):
    target = Path(output)
    check(target.suffix == '.json' and target.parent.is_dir() and
          not target.parent.is_symlink() and not target.exists() and
          not target.is_symlink() and
          target.resolve() not in (Path(video).resolve(),Path(config).resolve()),
          'output must be a new distinct JSON')
    data = analyze(video,config,times)
    with tempfile.TemporaryDirectory(prefix='.plo_board_probes_',dir=target.parent) as temp:
        staged = Path(temp)/'report.json'
        staged.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n','utf-8')
        os.link(staged,target)
    return data


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video');parser.add_argument('config');parser.add_argument('new_report_json')
    parser.add_argument('--times',default='5,15,25,35,45,55,65,75,85,95,105,115')
    args=parser.parse_args(argv)
    result=save_report(args.video,args.config,[float(x) for x in args.times.split(',')],args.new_report_json)
    print(json.dumps({'samples':len(result['samples']),
                      'transition_candidates':len(result['transition_candidates']),
                      'analysis_status':result['analysis_status']}))

if __name__=='__main__':main()
