"""Review-only FFmpeg/Tesseract probe of up to four declared table slots.

python offline_real_video_probe.py VIDEO CONFIG.json OUTPUT.json --times 5,60,600
The JSON layout uses slot rectangles in source pixels and a calibrated felt RGB.
It never verifies cards, hands, actions, equity, EV or poker decisions.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess

from PIL import Image, ImageEnhance, ImageOps

PROBES = ((.30, .52), (.70, .52), (.30, .68), (.70, .68))
PTS = re.compile(r'\bpts_time:\s*(-?\d+(?:\.\d+)?)')
BB = re.compile(r'(?<!\d)(\d{1,4}(?:[.,]\d{1,2})?)\s*BB\b', re.I)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def cmd(args, timeout=80, data=None):
    try:
        p = subprocess.run(args, input=data, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('offline tool unavailable/timed out') from exc
    require(p.returncode == 0 and len(p.stdout) < 2000000 and len(p.stderr) < 256000,
            'offline tool error: ' + args[0])
    return p


def config_read(path, size):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size < 20000,
            'invalid configuration path')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate config key')
            result[key] = value
        return result
    cfg = json.loads(path.read_text('utf-8'), object_pairs_hook=unique)
    require(type(cfg) is dict and set(cfg) == {'slots','felt_rgb','tolerance'} and
            type(cfg['slots']) is list and 1 <= len(cfg['slots']) <= 4 and
            type(cfg['felt_rgb']) is list and len(cfg['felt_rgb']) == 3 and
            all(type(c) is int and 0 <= c <= 255 for c in cfg['felt_rgb']) and
            type(cfg['tolerance']) is int and 1 <= cfg['tolerance'] <= 80,
            'invalid configuration schema')
    ids = set()
    for s in cfg['slots']:
        require(type(s) is dict and set(s) == {'table_id','x','y','width','height'} and
                all(type(v) is int for v in s.values()) and
                1 <= s['table_id'] <= 4 and s['table_id'] not in ids and
                min(s['x'],s['y']) >= 0 and s['width'] >= 300 and s['height'] >= 400 and
                s['x']+s['width'] <= size[0] and s['y']+s['height'] <= size[1],
                'invalid slot rectangle')
        ids.add(s['table_id'])
    for a in cfg['slots']:
        for b in cfg['slots']:
            if a['table_id'] >= b['table_id']:
                continue
            require(not (a['x'] < b['x']+b['width'] and b['x'] < a['x']+a['width'] and
                         a['y'] < b['y']+b['height'] and b['y'] < a['y']+a['height']),
                    'overlapping slots')
    return cfg


def classify(image, slot, rgb, tolerance):
    x,y,w,h = (slot[k] for k in ('x','y','width','height'))
    distances = []
    for px,py in PROBES:
        p = image.getpixel((x+round((w-1)*px), y+round((h-1)*py)))
        distances.append(round(math.sqrt(sum((p[i]-rgb[i])**2 for i in range(3))),1))
    match = sum(d <= tolerance for d in distances)
    return {'table_id':slot['table_id'],
            'proposal':'likely_visible' if match >= 3 else 'absent_or_uncertain',
            'matched_felt_probes':match, 'rgb_distances':distances,
            'human_verified':False}


def pot_ocr(image, slot):
    x,y,w,h=(slot[k] for k in ('x','y','width','height'))
    crop=image.crop((x+round(.392*w),y+round(.318*h),
                     x+round(.621*w),y+round(.365*h)))
    crop=ImageEnhance.Contrast(ImageOps.grayscale(crop.resize((crop.width*4,crop.height*4)))).enhance(2)
    blob=io.BytesIO()
    crop.save(blob,format='PNG')
    p=cmd(['tesseract','stdin','stdout','--psm','6','tsv'],30,blob.getvalue())
    words=[]
    for item in csv.DictReader(io.StringIO(p.stdout.decode('utf-8','replace')),delimiter='\t'):
        v=(item.get('text') or '').strip()
        try: conf=float(item.get('conf') or '-1')
        except ValueError: continue
        if v and math.isfinite(conf) and 0 <= conf <= 100:
            words.append((v,conf))
    raw=' '.join(word for word,_ in words)[:120]
    m=BB.search(raw)
    return {'raw_text':raw,'minimum_word_confidence':round(min((p for _,p in words),default=0)/100,4),
            'candidate_bb':float(m.group(1).replace(',','.')) if m else None,
            'status':'needs_human_review'}


def analyze(video, config, output, times):
    video,output=Path(video),Path(output)
    require(video.is_file() and not video.is_symlink() and
            video.suffix.lower() in ('.mp4','.webm') and
            0 < video.stat().st_size <= 8*1024**3, 'invalid offline video')
    require(output.suffix == '.json' and output.parent.is_dir() and
            not output.exists() and not output.is_symlink() and
            output.resolve() not in (video.resolve(),Path(config).resolve()),
            'output must be a distinct new JSON file')
    video_sha, layout_sha = sha256(video), sha256(config)
    raw=json.loads(cmd(['ffprobe','-v','error','-select_streams','v:0',
                        '-show_entries','stream=width,height,start_time,avg_frame_rate:format=duration',
                        '-of','json',str(video)],30).stdout)
    require(len(raw.get('streams',[])) == 1, 'missing video stream')
    s=raw['streams'][0]
    width,height=s['width'],s['height']
    duration,origin=float(raw['format']['duration']),float(s['start_time'])
    num,den=map(int,s['avg_frame_rate'].split('/'))
    require(300 <= width <= 8192 and 400 <= height <= 8192 and
            math.isfinite(duration) and .1 < duration <= 3900 and
            math.isfinite(origin) and den > 0 and .2 <= num/den <= 240,
            'unsupported video properties')
    require(type(times) is list and 1 <= len(times) <= 12 and
            all(type(t) in (int,float) and math.isfinite(t) and 0 <= t < duration
                for t in times) and times == sorted(set(times)), 'invalid sample times')
    cfg=config_read(config,(width,height))
    rows=[]
    for t in times:
        p=cmd(['ffmpeg','-hide_banner','-nostdin','-loglevel','info','-ss',str(t),
               '-copyts','-i',str(video),'-map','0:v:0','-an','-sn','-dn',
               '-vf','showinfo','-frames:v','1','-f','image2pipe','-vcodec','png','-'],90)
        points=[float(m.group(1)) for line in p.stderr.decode('utf-8','replace').splitlines()
                if 'Parsed_showinfo' in line for m in [PTS.search(line)] if m]
        require(len(points)==1 and abs(points[0]-(t+origin)) <= max(.25,den/num+.01),
                'decoded PTS not verifiable')
        with Image.open(io.BytesIO(p.stdout)) as im:
            image=im.convert('RGB')
        require(image.size==(width,height), 'frame geometry mismatch')
        candidates=[]
        for slot in cfg['slots']:
            present=classify(image,slot,cfg['felt_rgb'],cfg['tolerance'])
            present['pot_ocr']=pot_ocr(image,slot) if present['proposal']=='likely_visible' else None
            candidates.append(present)
        rows.append({'requested_playback_seconds':t,'decoded_source_pts_seconds':points[0],
                     'table_proposals':candidates})
    require(sha256(video) == video_sha and sha256(config) == layout_sha,
            'input changed during processing')
    report={'schema_version':1,'status':'real_video_ocr_and_layout_proposals_only',
            'source_video_sha256':video_sha, 'source_layout_sha256':layout_sha,
            'recording':{'width':width,'height':height,'duration_seconds':duration},
            'samples':rows,'hands_reconstructed':False,'equity_ev_authorized':False,
            'automatic_clip_selection_authorized':False,
            'warnings':['Manual slots and felt RGB; must visually confirm table presence.',
                        'OCR values are proposals and can be wrong; no poker math authorized.',
                        'Sparse samples are not complete hand histories.']}
    with output.open('x',encoding='utf-8') as f:
        json.dump(report,f,indent=2,ensure_ascii=False,allow_nan=False)
        f.write('\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video');parser.add_argument('config');parser.add_argument('new_output_json')
    parser.add_argument('--times',default='5,60,600,1800,3000')
    a=parser.parse_args()
    result=analyze(a.video,a.config,a.new_output_json,[float(v) for v in a.times.split(',')])
    print(json.dumps({'status':result['status'],
                      'visible_slot_proposals':[sum(t['proposal']=='likely_visible'
                       for t in s['table_proposals']) for s in result['samples']]}))


if __name__=='__main__':main()
