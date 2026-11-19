"""Batch export of human-reviewed offline clips using FFmpeg; never claims GTO."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
from offline_clip_plan_handoff import build_export_requests

SAFE_ID = re.compile(r'^[A-Za-z0-9_-]{1,80}$')

def _run(args):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=120)

def video_info(video):
    data=json.loads(_run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height:format=duration','-of','json',str(video)]).stdout)
    streams=data.get('streams',[])
    if not streams: raise ValueError('video stream missing')
    width,height=streams[0]['width'],streams[0]['height']
    duration=float(data['format']['duration'])
    if not math.isfinite(duration) or duration<=0: raise ValueError('invalid duration')
    return width,height,duration

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def export_reviewed_clips(video_path,plan_path,output_dir):
    video,plan_file,out=Path(video_path),Path(plan_path),Path(output_dir)
    if not video.is_file() or not plan_file.is_file(): raise ValueError('missing input')
    source_hash=sha256_file(video)
    plan=json.loads(plan_file.read_text(encoding='utf-8'))
    requests=build_export_requests(plan,source_hash)['export_requests']
    width,height,duration=video_info(video)
    for item in requests:
        crop=item['crop']
        if not SAFE_ID.fullmatch(item['hand_id']): raise ValueError('unsafe hand id')
        if item['end_seconds']>duration+0.001: raise ValueError('interval exceeds video')
        if crop['x']+crop['width']>width or crop['y']+crop['height']>height: raise ValueError('crop exceeds frame')
    out.mkdir(parents=True,exist_ok=True)
    results=[]
    for item in requests:
        crop=item['crop']
        name=f"table{item['table_id']}_{item['hand_id']}.mp4"
        target=out/name
        if target.exists(): raise FileExistsError(f'will not overwrite {target}')
        with tempfile.NamedTemporaryFile(prefix='.clip_',suffix='.mp4',dir=out,delete=False) as tmp: temp=Path(tmp.name)
        try:
            _run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-ss',str(item['start_seconds']),'-i',str(video),'-t',str(item['end_seconds']-item['start_seconds']),'-vf',f"crop={crop['width']}:{crop['height']}:{crop['x']}:{crop['y']}",'-an','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(temp)])
            if temp.stat().st_size==0: raise ValueError('empty clip')
            temp.replace(target)
        finally: temp.unlink(missing_ok=True)
        results.append({'hand_id':item['hand_id'],'table_id':item['table_id'],'clip':name,'sha256':sha256_file(target),'start_seconds':item['start_seconds'],'end_seconds':item['end_seconds'],'analysis_label':'INSUFFICIENT_DATA','strategy_verified':False})
    manifest={'schema_version':1,'source_video_sha256':source_hash,'analysis_verified':False,'is_gto':False,'clips':results}
    manifest_path=out/'clip_manifest.json'
    if manifest_path.exists(): raise FileExistsError('will not overwrite manifest')
    manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    return manifest

def main():
    p=argparse.ArgumentParser(description='Export reviewed offline PLO clips')
    p.add_argument('video');p.add_argument('plan_json');p.add_argument('output_dir')
    args=p.parse_args()
    manifest=export_reviewed_clips(args.video,args.plan_json,args.output_dir)
    print(f"Exported {len(manifest['clips'])} clips; strategy NOT VERIFIED")

if __name__=='__main__': main()
