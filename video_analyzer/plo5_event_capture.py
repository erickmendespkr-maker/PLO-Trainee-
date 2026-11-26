"""Offline change-triggered evidence capture for recorded PLO5, not action recognition."""
import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import cv2
import numpy as np
from PIL import Image
from plo5_mixed_money import STARTS, detect

SIZE=(1504,696)
# Local coordinates: broad regions include moving/animated cards. Labels describe pixels only.
ROIS={
 'pppoker':{'hero':(210,550,320,622),'board':(70,270,307,355),'pot':(145,235,235,280),'stack':(150,620,225,645),'hero_action':(140,550,211,588),'left_actions':(4,190,82,485),'right_actions':(290,190,371,485),'top_action':(135,85,246,170)},
 'suprema':{'hero':(220,535,330,595),'board':(60,236,320,318),'pot':(145,220,235,260),'stack':(150,590,225,620),'hero_action':(150,560,223,590),'left_actions':(4,180,86,455),'right_actions':(292,180,371,455),'top_action':(140,75,240,165)}}

def need(ok,msg):
    if not ok:raise ValueError(msg)

def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def signatures(crop,platform):
    out={}
    for field,(x,y,a,b) in ROIS[platform].items():
        roi=crop[y:b,x:a]
        out[field]=cv2.resize(roi,(max(1,(a-x)//2),max(1,(b-y)//2)),interpolation=cv2.INTER_AREA)
    return out

def changed(a,b,threshold=.07):
    return [k for k in a if np.mean(np.max(cv2.absdiff(a[k],b[k]),axis=2)>24)>=threshold]

def sharp(crop,platform):
    scores=[]
    for f in ('hero','board'):
        x,y,a,b=ROIS[platform][f]
        scores.append(float(cv2.Laplacian(cv2.cvtColor(crop[y:b,x:a],cv2.COLOR_RGB2GRAY),cv2.CV_32F).var()))
    return sum(scores)

class Tracker:
    def __init__(self,hz):self.hz=hz;self.state={}
    def step(self,t,platform,crop,idx,bucket):
        old=self.state.get(t);events=[]
        if platform not in ROIS:
            self.state.pop(t,None);return events
        sig=signatures(crop,platform);now=(idx,crop.copy(),sig,bucket)
        if old is None or old['platform']!=platform or bucket!=old['last'][3]+1:
            self.state[t]={'platform':platform,'last':now,'base':now,'pending':None}
            return [('initial_or_gap',[],None,now,now)]
        base=old['base'];last=old['last'];delta=changed(base[2],sig);pending=old['pending']
        if not delta:
            old['pending']=None;old['base']=now
        else:
            if pending is None:
                pending={'first':now,'before':last,'fields':set(delta)};old['pending']=pending
            pending['fields'].update(delta)
            stable=not changed(last[2],sig,.04) and last[0]>=pending['first'][0]
            timeout=bucket-pending['first'][3]>=self.hz
            if stable or timeout:
                best=max((last,now),key=lambda q:sharp(q[1],platform)) if stable else now
                events.append(('stable_change_candidate' if stable else 'unstable_change_candidate',sorted(pending['fields']),pending['before'],pending['first'],best))
                old['base']=now;old['pending']=None
        old['last']=now
        return events

def probe(source,start,seconds,hz):
    p=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-read_intervals',f'{start}%{start+seconds+1}','-show_entries','stream=time_base,width,height:frame=best_effort_timestamp','-of','json',str(source)],capture_output=True,text=True,timeout=60,check=True)
    data=json.loads(p.stdout);s=data['streams'][0];need((s['width'],s['height'])==SIZE,'Unsupported geometry');tb=Fraction(s['time_base'])
    known=sorted({int(x['best_effort_timestamp']) for x in data['frames'] if 'best_effort_timestamp' in x});buckets={}
    for pts in known:
        if start<=pts*tb<start+seconds:buckets.setdefault(int(pts*tb*hz),pts)
    need(buckets,'Empty video window');return tb,buckets

def run(source,out,start=1250,seconds=20,hz=8):
    need(type(start) is int and start>=0 and type(seconds) is int and 2<=seconds<=60 and type(hz) is int and 2<=hz<=12,'Invalid window or sampling rate')
    source=Path(source);out=Path(out);need(source.is_file() and source.suffix.lower()=='.mp4' and not source.is_symlink(),'Local recording required');need(out.parent.is_dir() and not out.exists() and not out.is_symlink(),'New output required')
    started=time.perf_counter();source_hash=digest(source);tb,buckets=probe(source,start,seconds,hz);ordered=list(buckets);tracker=Tracker(hz);events=[];counts={};n=0
    with tempfile.TemporaryDirectory(dir=out.parent,prefix='.event-') as tmp:
        stage=Path(tmp)/'report';stage.mkdir();prints=stage/'prints';prints.mkdir();log=Path(tmp)/'decode.log';size=SIZE[0]*SIZE[1]*3
        def save(crop,name):
            p=prints/name;Image.fromarray(crop).save(p);return {'file':'prints/'+name,'sha256':digest(p)}
        vf=f"select='gte(t,{start})*lt(t,{start+seconds})*(isnan(prev_selected_t)+gt(floor(t*{hz}),floor(prev_selected_t*{hz})))',showinfo"
        args=['ffmpeg','-nostdin','-hide_banner','-loglevel','info','-threads','1','-filter_threads','1','-ss',str(start),'-t',str(seconds+1),'-copyts','-i',str(source),'-map','0:v:0','-vf',vf,'-frames:v',str(len(ordered)),'-fps_mode','passthrough','-pix_fmt','rgb24','-c:v','rawvideo','-threads:v','1','-an','-sn','-dn','-f','rawvideo','pipe:1']
        with log.open('wb') as err:
            p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=err)
            try:
                while True:
                    raw=p.stdout.read(size)
                    if not raw:break
                    need(len(raw)==size and n<len(ordered),'Truncated or excess decoded frame');rgb=np.frombuffer(raw,dtype=np.uint8).reshape(SIZE[1],SIZE[0],3);im=Image.fromarray(rgb)
                    for t,x in enumerate(STARTS,1):
                        platform=detect(im,t);counts[str(platform)]=counts.get(str(platform),0)+1;crop=rgb[:,x:x+372]
                        for reason,fields,before,first,after in tracker.step(t,platform,crop,n,ordered[n]):
                            i=len(events)+1;row={'event_id':i,'table_id':t,'platform':platform,'status':reason,'changed_regions':fields,'action_verified':False,'hand_verified':False,'financial_result_verified':False}
                            for label,item in [('before',before),('first',first),('after',after)]:
                                if item is not None:
                                    idx,c,_,_=item;row[label]={'sample':idx,'pts':str(buckets[ordered[idx]]*tb),**save(c,f'{i:04}_{label}.png')}
                            for f in ('hero','board'):
                                a,b,c,d=ROIS[platform][f];zoom=Image.fromarray(after[1][b:d,a:c]).resize(((c-a)*4,(d-b)*4),Image.Resampling.LANCZOS)
                                z=prints/f'{i:04}_{f}_zoom.png';zoom.save(z);row[f+'_zoom']={'file':'prints/'+z.name,'sha256':digest(z),'scale':4,'derived_from':'after','roi':[a,b,c,d]}
                            events.append(row)
                    n+=1
                need(p.wait(timeout=30)==0,'FFmpeg failed')
            finally:
                if p.poll() is None:p.kill();p.wait()
                p.stdout.close()
        logs=log.read_text();bases=re.findall(r'config in time_base: (\d+/\d+)',logs);stamps=[(int(i),int(v)) for i,v in re.findall(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:',logs)]
        need(bases and all(Fraction(x)==tb for x in bases) and stamps==list(enumerate(buckets.values())) and n==len(ordered),'Decoded PTS roster differs from source probe')
        need(digest(source)==source_hash,'Source changed')
        report={'variant':5,'status':'PIXEL_CHANGE_CANDIDATES_ONLY','source_sha256':source_hash,'start':start,'seconds':seconds,'sampling_hz':hz,'sample_count':n,'missing_buckets':sorted(set(range(start*hz,(start+seconds)*hz))-set(ordered)),'platform_samples':counts,'events':events,'wall_seconds':time.perf_counter()-started,'actions_verified':False,'hands_reconstructed':False,'financial_result_verified':False}
        (stage/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8');page=['<!doctype html><meta charset="utf-8"><title>PLO5 — Eventos visuais</title><style>body{font:16px system-ui;max-width:1000px;margin:auto}img{max-width:100%}article{border-top:1px solid #aaa;padding:12px}</style><h1>Eventos visuais candidatos</h1><p>Mudanças de pixels, não ações confirmadas. Zoom digital não cria detalhe.</p>']
        for r in events:
            page.append(f'<article><h2>Mesa {r["table_id"]} — {r["after"]["pts"]} s ({r["status"]})</h2><p>{", ".join(r["changed_regions"])}</p>')
            for k in ('before','first','after','hero_zoom','board_zoom'):
                if k in r:page.append(f'<a href="{r[k]["file"]}">{k}</a> ')
            page.append(f'<p><img loading="lazy" src="{r["hero_zoom"]["file"]}"><img loading="lazy" src="{r["board_zoom"]["file"]}"></p></article>')
        (stage/'index.html').write_text(''.join(page),encoding='utf-8');need(not out.exists() and not out.is_symlink(),'Output appeared');os.rename(stage,out)
    return report

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('output');p.add_argument('--start',type=int,default=1250);p.add_argument('--seconds',type=int,default=20);p.add_argument('--hz',type=int,default=8);a=p.parse_args(argv);r=run(a.source,a.output,a.start,a.seconds,a.hz);print(json.dumps({k:v for k,v in r.items() if k!='events'}));return 0
if __name__=='__main__':raise SystemExit(main())
