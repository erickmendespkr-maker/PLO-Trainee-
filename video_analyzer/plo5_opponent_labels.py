"""Offline opponent label candidates. Never interprets persistent labels as new actions."""
import argparse, hashlib, io, json, math
from pathlib import Path
from fractions import Fraction
from functools import lru_cache
import cv2
import numpy as np
from PIL import Image
from plo5_mixed_money import STARTS, detect
from plo5_hero_actions import BOXES, TEMPLATES
import base64,zlib

SEATS=('top','upper_right','lower_right','lower_left','upper_left')
ANCHORS={'pppoker':((189,92),(295,204),(295,401),(41,401),(41,204)), 'suprema':((173,83),(323,192),(323,411),(24,411),(26,192))}
ACTIONS={'fold','bet','raise','call','check','all_in','pot'}
MARKERS={'sb','bb','straddle','new'}
PROFILE='opponent-labels-1504x696-v1'

def need(ok,msg):
    if not ok:raise ValueError(msg)

def dims(p):
    a,b,c,d=BOXES[p];return c-a,d-b

def load_bank(path):
    path=Path(path);need(path.is_file() and not path.is_symlink() and 0<path.stat().st_size<2**20,'Invalid bank')
    data=json.loads(path.read_bytes());need(data.get('profile')==PROFILE and set(data.get('templates',{}))==set(ANCHORS),'Invalid profile')
    bank={}
    for p,labels in data['templates'].items():
        w,h=dims(p);need(type(labels) is dict and set(labels)<=ACTIONS|MARKERS and bool(labels),'Invalid labels')
        bank[p]={}
        for label,values in labels.items():
            need(type(values) is list and 0<len(values)<=64,'Invalid templates')
            arr=[]
            for value in values:
                need(type(value) is str and len(value)==2*w*h,'Invalid glyph')
                g=np.frombuffer(bytes.fromhex(value),np.uint8).reshape(h,w)
                need(g.std()>5,'Blank glyph');arr.append(g)
            bank[p][label]=arr
    return bank

def observe(im,t,bank):
    need(im.size==(1504,696) and type(t) is int and 1<=t<=4,'Invalid geometry')
    p=detect(im,t);out={'table_id':t,'platform':p,'opponents':[],'actions_verified':False}
    if p not in ANCHORS:return out
    w,h=dims(p);a=np.asarray(im.crop((STARTS[t-1],0,STARTS[t-1]+372,696)).convert('L'))
    for seat,(x,y) in zip(SEATS,ANCHORS[p]):
        roi=a[y-4:y+h+5,x-4:x+w+5];scores={label:max(float(cv2.minMaxLoc(cv2.matchTemplate(roi,g,cv2.TM_CCOEFF_NORMED))[1]) for g in gs) for label,gs in bank[p].items()}
        ordered=sorted(scores.items(),key=lambda q:q[1],reverse=True);label=None
        if ordered and ordered[0][1]>=.85 and (len(ordered)==1 or ordered[0][1]-ordered[1][1]>=.10):label=ordered[0][0]
        out['opponents'].append({'seat':seat,'visible_label_candidate':label,'label_kind':('action' if label in ACTIONS else 'marker' if label in MARKERS else None),'scores':scores,'action_verified':False})
    return out

def combine(a,b):
    need(a['platform']==b['platform'] and a['table_id']==b['table_id'],'Mismatched observations')
    need([r['seat'] for r in a['opponents']]==list(SEATS) and [r['seat'] for r in b['opponents']]==list(SEATS),'Bad roster')
    rows=[]
    for x,y in zip(a['opponents'],b['opponents']):
        u,v=x['visible_label_candidate'],y['visible_label_candidate'];label=u if u==v and u in ACTIONS|MARKERS else None
        rows.append({'seat':x['seat'],'label_candidate':label,'label_kind':'action' if label in ACTIONS else 'marker' if label in MARKERS else None,'after_label':u,'peer_label':v,'action_verified':False,'action_street':None,'action_amount_bb':None})
    return rows

def run(root,bank_path):
    root=Path(root);p=root/'manifest.json';need(p.is_file() and not p.is_symlink() and p.stat().st_size<16*2**20,'Invalid manifest')
    raw=p.read_bytes();m=json.loads(raw);hz=m['sampling_hz'];need(m['variant']==5 and m['status']=='PIXEL_CHANGE_CANDIDATES_ONLY' and type(hz) is int and 2<=hz<=12,'Wrong manifest')
    bank_hash=hashlib.sha256(Path(bank_path).read_bytes()).hexdigest();bank=load_bank(bank_path);rows=[];seen=set()
    for e in m['events']:
        i,t,k=e['event_id'],e['table_id'],e['platform'];need(type(i) is int and i>0 and i not in seen and type(t) is int and 1<=t<=4,'Invalid event');seen.add(i)
        if e['status']!='stable_change_candidate' or k not in ANCHORS or 'peer' not in e:continue
        a,b=e['after'],e['peer'];u,v=Fraction(a['pts']),Fraction(b['pts']);need(abs(a['sample']-b['sample'])==1 and abs(int(u*hz)-int(v*hz))==1 and 0<abs(u-v)<=Fraction(2,hz) and (u<v)==(a['sample']<b['sample']) and m['start']<=min(u,v)<=max(u,v)<m['start']+m['seconds'],'Invalid pair')
        def read(entry,label):
            expected=f'prints/{i:04}_{label}.png';need(entry['file']==expected,'Unexpected path');q=root/expected;need(q.is_file() and not q.is_symlink() and not q.parent.is_symlink() and q.stat().st_size<=8*2**20,'Invalid print');data=q.read_bytes();need(hashlib.sha256(data).hexdigest()==entry['sha256'],'Print hash mismatch')
            with Image.open(io.BytesIO(data)) as im:
                need(im.size==(372,696),'Invalid crop');full=Image.new('RGB',(1504,696));full.paste(im.convert('RGB'),(STARTS[t-1],0))
            r=observe(full,t,bank);need(r['platform']==k,'Platform mismatch');return r
        rows.append({'event_id':i,'table_id':t,'platform':k,'after_pts':str(u),'peer_pts':str(v),'opponents':combine(read(a,'after'),read(b,'peer'))})
    need(p.read_bytes()==raw and hashlib.sha256(Path(bank_path).read_bytes()).hexdigest()==bank_hash,'Input changed')
    return {'variant':5,'status':'OPPONENT_LABEL_PAIR_CANDIDATES_ONLY','manifest_sha256':hashlib.sha256(raw).hexdigest(),'bank_sha256':bank_hash,'source_sha256':m['source_sha256'],'rows':rows,'actions_verified':False,'hands_reconstructed':False,'strategy_authorized':False}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');p.add_argument('bank');p.add_argument('output');a=p.parse_args(argv);r=run(a.report,a.bank)
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    return 0
if __name__=='__main__':raise SystemExit(main())
