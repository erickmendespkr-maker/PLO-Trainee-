"""Offline adaptive PLO5 card-only observations, never fill a missing frame by inference."""
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path
from threading import Timer
from PIL import Image
from plo5_pre_gto_context import need
from plo5_video_stream import roster, digest, SIZE, FRAME_BYTES
from plo5_error_prints import frame_index
from plo5_bounded_session import load_interval
from plo5_mixed_cards_v2 import MixedCardReader


def plan(manifest,start,seconds,budget=12):
    """Select partial card states first; a gap is a request, never a synthetic frame."""
    need(type(start) is int and start>=0 and type(seconds) is int and 2<=seconds<=120,'Invalid window')
    need(type(budget) is int and 1<=budget<=32,'Invalid refinement budget')
    frames=frame_index(manifest);by={}
    for pts,f in frames.items():
        s=int(pts//1);need(start<=s<start+seconds and s not in by,'Expected one coarse frame per second');by[s]=f
    requests=[]
    for s in range(start,start+seconds):
        f=by.get(s)
        if f is None:
            requests.append(dict(second=s,tables=[1,2,3,4],reason='MISSING_SAMPLE',priority=0));continue
        targets=[];partial=0
        for c in f.get('cards',[]):
            t=c['table_id'];need(type(t) is int and 1<=t<=4,'Invalid table')
            if c['platform'] not in ('pppoker','suprema'):continue
            if c['hero_cards'] is not None and c['board_cards'] is not None:continue
            targets.append(t);partial+=sum(x.get('card') is not None for field in ('hero_slots','board_slots') for x in c.get(field,[]))
        if targets:requests.append(dict(second=s,tables=sorted(set(targets)),reason='INCOMPLETE_CARDS',priority=1+partial))
    return sorted(sorted(requests,key=lambda r:(-r['priority'],r['second']))[:budget],key=lambda r:r['second'])


def choose_ticks(tb,known,requests,existing):
    """First actual source frame in each quarter bucket, excluding coarse frames."""
    buckets={r['second']:r for r in requests};chosen={};occupied=set()
    for tick in sorted(known):
        pts=tick*tb;s=int(pts//1)
        if s not in buckets or pts in existing:continue
        quarter=int((pts-s)*4)
        if quarter==0 and buckets[s]['reason']!='MISSING_SAMPLE':continue
        key=(s,quarter)
        if key not in occupied:
            chosen[tick]=buckets[s];occupied.add(key)
    return chosen


def refine(source,manifest,start,seconds,reader,*,budget=12,timeout=120):
    """Card-only additional source frames, independently classified and PTS audited."""
    need(type(timeout) is int and 1<=timeout<=300,'Invalid timeout')
    source=Path(source);need(source.is_file() and not source.is_symlink() and source.suffix.lower()=='.mp4','Local MP4 required')
    requests=plan(manifest,start,seconds,budget);h=digest(source);need(h==manifest['source_sha256'],'Source hash mismatch')
    existing=frame_index(manifest);rows=[]
    if requests:
        tb,known,_=roster(source,start,seconds);chosen=choose_ticks(tb,known,requests,existing);ticks=list(chosen)
        need(len(ticks)<=4*budget and all(0<=t<2**53 for t in ticks),'Refinement tick budget exceeded')
        if ticks:
            expr='+'.join(f'eq(pts,{t})' for t in ticks)
            cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','info','-threads','1','-filter_threads','1','-ss',str(start),'-t',str(seconds+1),'-copyts','-i',str(source),'-map','0:v:0','-vf',f"select='{expr}',showinfo",'-frames:v',str(len(ticks)),'-fps_mode','passthrough','-pix_fmt','rgb24','-c:v','rawvideo','-threads:v','1','-an','-sn','-dn','-f','rawvideo','pipe:1']
            with tempfile.TemporaryFile() as log:
                with subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=log) as p:
                    timer=Timer(timeout,p.kill);timer.daemon=True;timer.start()
                    try:
                        for t in ticks:
                            raw=p.stdout.read(FRAME_BYTES);need(len(raw)==FRAME_BYTES,'Incomplete refined RGB frame')
                            cards=reader.scan(Image.frombytes('RGB',SIZE,raw));target=chosen[t]['tables']
                            rows.append(dict(pts=str(t*tb),rgb_sha256=hashlib.sha256(raw).hexdigest(),target_tables=target,cards=[c for c in cards if c['table_id'] in target]))
                        need(p.stdout.read(1)==b'' and p.wait()==0,'Refinement decoding failed')
                    finally:
                        timer.cancel();timer.join()
                        if p.poll() is None:p.kill()
                        p.wait()
                need(log.tell()<=8*1024**2,'Refinement log budget');log.seek(0);logs=log.read().decode('utf-8')
            bases=re.findall(r'config in time_base: (\d+/\d+)',logs)
            stamps=[(int(n),int(v)) for n,v in re.findall(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:',logs)]
            need(bases and all(Fraction(x)==tb for x in bases) and stamps==list(enumerate(ticks)),'Refinement PTS mismatch')
    need(digest(source)==h,'Source changed')
    complete={(int(Fraction(r['pts'])//1),c['table_id']) for r in rows for c in r['cards'] if c['hero_cards'] is not None and c['board_cards'] is not None}
    return dict(version='plo5-card-refinement-v1',variant=5,source_sha256=h,start=start,seconds=seconds,requests=requests,frames=rows,additional_complete_second_tables=len(complete),cards_verified=False,hands_reconstructed=False,strategy_authorized=False,coarse_frames_replaced=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('video');p.add_argument('session');p.add_argument('output');p.add_argument('--start',type=int,required=True);p.add_argument('--seconds',type=int,required=True);p.add_argument('--budget',type=int,default=12);p.add_argument('--ppp');p.add_argument('--suprema');a=p.parse_args(argv)
    out=Path(a.output);need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON required')
    banks={k:digest(v) for k,v in [('pppoker',a.ppp),('suprema',a.suprema)] if v};m=load_interval(a.session,a.start,a.seconds);r=refine(a.video,m,a.start,a.seconds,MixedCardReader(a.ppp,a.suprema),budget=a.budget)
    need(all(digest(v)==banks[k] for k,v in [('pppoker',a.ppp),('suprema',a.suprema)] if v),'Bank changed');r['card_bank_sha256']=banks
    with out.open('x',encoding='utf-8') as f:json.dump(r,f,ensure_ascii=False,allow_nan=False,indent=2)
    print(json.dumps({k:v for k,v in r.items() if k not in ('frames','requests')}));return 0

if __name__=='__main__':raise SystemExit(main())
