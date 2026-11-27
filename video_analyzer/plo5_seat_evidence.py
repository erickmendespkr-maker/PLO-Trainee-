"""Offline fixed-slot stack/action/dealer candidates; no dealt roster or position proof."""
from concurrent.futures import ThreadPoolExecutor
import io
import os
import subprocess
from PIL import Image, ImageOps, ImageChops
import json
from pathlib import Path
from plo5_mixed_money import STARTS,detect,parse
from plo5_singleflight import SingleFlight
from plo5_pre_gto_context import need

SEATS=('top','upper_right','lower_right','hero_bottom','lower_left','upper_left')
STACKS={'pppoker':((156,156,222,171),(303,269,370,284),(303,466,370,481),(159,627,218,640),(8,466,75,481),(8,269,75,284)),
        'suprema':((155,108,223,124),(305,218,372,232),(305,437,372,452),(162,601,218,612),(5,437,74,452),(5,218,74,232))}
ACTIONS={'pppoker':((188,90,232,105),(294,202,339,217),(294,399,339,415),(146,560,190,577),(40,399,85,415),(40,202,85,217)),
         'suprema':((168,79,210,94),(320,187,360,203),(320,407,360,423),(168,569,210,585),(20,407,61,423),(20,187,61,203))}
CENTERS={'pppoker':((235,132),(292,244),(292,443),(145,548),(86,443),(86,244)),
         'suprema':((224,95),(304,203),(304,423),(143,527),(75,423),(75,203))}
GLYPHS={
'pppoker':'5f5f7986aaecf2f1eccd8b80615f6a8998d7ebeee6e7e9eae9b3877f86c1e4f1ee827b7997b5edf2d48f88e3e4e3d92e2b2a212441e6ebb68ee2e0e5b03455d9c13526bee4b88ee2dfe5992d86eee7542f9ee7b88ee2dfed6332bce9e95a35cae5b58ee2dff05031c9eeac474be6dfb391ddd8d54441606a4936bbe0dfb888dfe0c03a403f3b61bee1deecac7592c9e0d6d8dbd9e8eaddd5af9c446597b3eaedf1f4f1efbd9e7365473f517cabc0dee0d7baa760443d554e42456d90b6c1ad8851414855',
'suprema':'252a2de0b69cddf9ebb59ff04e24213df196fbfefbfbfffcfbcbce7120f4a8fffbfffdfcfafffafdecdcad82fcff481916171b1ebbfdfcc2f3e4ffff502120281f2021c1fcfbb6fefcff532027f9ff3e2432fcfb7cffffff512025fdff8e2019fffa72fefffc522428ffff8b2019fefea7ffffff53202bfdff79211ff9fff4f2fdff4e2027c1ad242266fafcbd95fcff51201f261e1f3af9feda24f7d0ffa3979a9c9aeffffcfaad2157e6ccfffffcfffdfffff799a0261f36fc70edfefcfffc76ee751f'}
LABELS={'fold':'fold','check':'check','call':'call','bet':'bet','raise':'raise','all-in':'all_in','all in':'all_in','allin':'all_in','pot':'pot_label','sb':'sb_label','bb':'bb_label'}


def decode(image,platform,field):
    gray=image.convert('L');gray=gray.crop((3,1,gray.width-3,gray.height-2));lo,hi=gray.getextrema()
    if hi-lo<15:return dict(raw='',confidence=None,candidate=None)
    gray=ImageOps.autocontrast(gray)
    if field=='stack' or platform=='suprema':gray=ImageOps.invert(gray)
    gray=gray.resize((gray.width*6,gray.height*6),Image.Resampling.LANCZOS);gray=ImageOps.expand(gray,border=24,fill=255)
    stream=io.BytesIO();gray.save(stream,format='PNG')
    p=subprocess.run(['tesseract','stdin','stdout','--psm','7' if field=='stack' else '8','tsv'],input=stream.getvalue(),capture_output=True,timeout=15,check=True,env=dict(os.environ,OMP_THREAD_LIMIT='1'))
    need(len(p.stdout)<=65536,'OCR output exceeds budget')
    words=[];conf=[]
    for line in p.stdout.decode('utf-8').splitlines()[1:]:
        cols=line.split('\t',11)
        if len(cols)==12 and cols[0]=='5' and cols[11].strip():words.append(cols[11]);conf.append(float(cols[10])/100)
    raw=' '.join(words);confidence=min(conf) if conf else None;candidate=None
    if confidence is not None and confidence>=.75:
        candidate=parse(raw,platform,'stack') if field=='stack' else LABELS.get(raw.strip().lower())
    return dict(raw=raw,confidence=confidence,candidate=candidate)



def action_patch(image):
    # Preserve color as well as glyph; remove border pixels from fixed ROIs.
    return image.crop((3,2,image.width-3,image.height-3)).convert('RGB').resize((36,10),Image.Resampling.BILINEAR)


class ActionBank:
    def __init__(self,path):
        p=Path(path);need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=2*1024**2,'Invalid action bank')
        raw=json.loads(p.read_text());need(type(raw) is dict and set(raw)<=set(ACTIONS),'Invalid profiles');self.rows={}
        for platform,rows in raw.items():
            need(type(rows) is list and 1<=len(rows)<=256,'Invalid action rows');self.rows[platform]=[]
            for label,h in rows:
                need(label in LABELS.values() and type(h) is str and len(h)==2160,'Invalid template')
                self.rows[platform].append((label,Image.frombytes('RGB',(36,10),bytes.fromhex(h))))
    def match(self,image,platform):
        q=action_patch(image);scores={}
        for label,ref in self.rows.get(platform,[]):
            hist=ImageChops.difference(q,ref).histogram();d=sum((i%256)*n for i,n in enumerate(hist))/(1080*255)
            scores[label]=min(scores.get(label,1.),d)
        ordered=sorted((v,k) for k,v in scores.items());out=dict(raw='',confidence=None,candidate=None,source='VISUAL_ACTION_UNKNOWN')
        if len(ordered)>=2:
            d,label=ordered[0];gap=ordered[1][0]-d
            out.update(distance=d,margin=gap)
            if d<=.045 and gap>=.018:out.update(candidate=label,source='VISUAL_LABEL_CANDIDATE')
        return out


def dealer(image,t,p):
    try:import cv2;import numpy as np
    except ImportError:return dict(seat=None,scores=[],status='OPTIONAL_OPENCV_UNAVAILABLE')
    gray=np.asarray(image.convert('L'));glyph=np.frombuffer(bytes.fromhex(GLYPHS[p]),np.uint8).reshape(14,14);scores=[]
    for seat,(x,y) in zip(SEATS,CENTERS[p]):
        x+=STARTS[t-1];roi=gray[y-17:y+18,x-17:x+18]
        m=cv2.matchTemplate(roi,glyph,cv2.TM_CCOEFF_NORMED);_,v,_,_=cv2.minMaxLoc(m);scores.append(dict(seat=seat,score=float(v)))
    z=sorted(scores,key=lambda r:r['score'],reverse=True)
    return dict(seat=z[0]['seat'] if z[0]['score']>=.75 and z[0]['score']-z[1]['score']>=.20 else None,scores=scores,status='DEALER_CANDIDATE_ONLY')


class SeatReader:
    def __init__(self,capacity=1024,workers=2,decoder=decode,action_bank=None):
        need(type(workers) is int and 1<=workers<=3,'Invalid workers');self.cache=SingleFlight(capacity);self.workers=workers;self.decoder=decoder;self.action_bank=ActionBank(action_bank) if action_bank else None
    def scan(self,image):
        need(image.size==(1504,696) and image.mode=='RGB','Unsupported geometry')
        rows=[];jobs=[]
        for t in range(1,5):
            p=detect(image,t);row=dict(table_id=t,platform=p,dealer=dealer(image,t,p) if p else None,seats=[],positions_verified=False,actions_verified=False,financial_result_verified=False);rows.append(row)
            if p is None:continue
            for i,s in enumerate(SEATS):
                seat=dict(seat=s);row['seats'].append(seat)
                for f,boxes in [('stack',STACKS),('action',ACTIONS)]:
                    a,b,c,d=boxes[p][i];x=STARTS[t-1];patch=image.crop((x+a,b,x+c,d));jobs.append((seat,p,f,patch))
        def read(job):
            seat,p,f,patch=job;key=(p,f,patch.size,patch.tobytes());seat[f]=self.cache.get(key,lambda:self.action_bank.match(patch,p) if f=='action' and self.action_bank is not None else self.decoder(patch,p,f))
        with ThreadPoolExecutor(max_workers=self.workers) as pool:list(pool.map(read,jobs))
        return rows
    def stats(self):return self.cache.stats()


def summarize(frames):
    """Count observed candidates, never distinct actions or financial outcomes."""
    counts=dict(table_samples=0,seat_samples=0,stack_candidates=0,label_candidates=0,dealer_candidates=0,complete_stack_rosters=0)
    details=[]
    for frame in frames:
        for row in frame.get('cards',[]):
            e=row.get('seat_evidence')
            if e is None or not e['platform']:continue
            need(e['table_id']==row['table_id'] and e['platform']==row['platform'] and [s['seat'] for s in e['seats']]==list(SEATS),'Invalid seat evidence')
            need(e['actions_verified'] is False and e['positions_verified'] is False and e['financial_result_verified'] is False,'Unexpected verification flag')
            counts['table_samples']+=1;counts['seat_samples']+=6
            stacks=sum(s['stack']['candidate'] is not None for s in e['seats']);labels=sum(s['action']['candidate'] is not None for s in e['seats'])
            counts['stack_candidates']+=stacks;counts['label_candidates']+=labels;counts['dealer_candidates']+=e['dealer']['seat'] is not None;counts['complete_stack_rosters']+=stacks==6
            details.append(dict(pts=frame['pts'],table_id=e['table_id'],dealer=e['dealer']['seat'],seats=e['seats']))
    return dict(counts,details=details,actions_verified=False,positions_verified=False,financial_result_verified=False)
