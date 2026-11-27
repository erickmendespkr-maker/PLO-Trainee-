"""Offline whole-text reference matches for known PPPoker payout displays.

Not OCR: a match can only reproduce a previously labelled amount. Do not use
it as an accounting entry, even when consecutive frames agree.
"""
import argparse, hashlib, io, json, re
from decimal import Decimal
from pathlib import Path
import numpy as np
from PIL import Image
from plo5_payout_display import REGIONS, STARTS, detect, mask

PROFILE='pppoker-payout-whole-text-1504x696-v1'
MAX_DISTANCE=.20
MIN_MARGIN=.20


def need(ok,msg):
    if not ok:raise ValueError(msg)


def feature(roi):
    if mask(roi) is None:return None
    a=np.asarray(roi.convert('RGB'),dtype=np.int16);r,g,b=a.transpose(2,0,1)
    a=np.clip(np.minimum(r,g)-b,0,255);m=a>80
    if m.sum()<80:return None
    yy,xx=np.where(m);x0,x1=xx.min(),xx.max();ys=np.where(m.sum(axis=1)>=5)[0]
    if not len(ys):return None
    y0=ys[0]
    if not 36<=x1-x0+1<=80 or y0+12>len(a):return None
    return np.clip((a[y0:y0+12,x0:x1+1]-30)/170,0,1).astype(np.float32)


def distance(a,b):
    if abs(a.shape[1]-b.shape[1])>3:return 1.
    h,w=16,max(a.shape[1],b.shape[1])+8;aa=np.zeros((h,w),np.float32);aa[2:14,w-4-a.shape[1]:w-4]=a
    best=1.
    for dy in (-1,0,1):
        for dx in (-2,-1,0,1,2):
            bb=np.zeros_like(aa);bb[2+dy:14+dy,w-4-b.shape[1]+dx:w-4+dx]=b
            best=min(best,float(np.abs(aa-bb).sum()/max(1.,np.maximum(aa,bb).sum())))
    return best


def load_bank(path):
    p=Path(path);need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<2**20,'Invalid bank')
    d=json.loads(p.read_bytes());need(type(d) is dict and set(d)=={'profile','templates'} and d['profile']==PROFILE,'Invalid profile')
    rows=d['templates'];need(type(rows) is dict and 2<=len(rows)<=128,'Invalid reference count');out={}
    for label,items in rows.items():
        need(re.fullmatch(r'\d{1,5}(?:\.\d{1,2})?',label) and Decimal(label)>0 and format(Decimal(label).normalize(),'f')==label,'Invalid amount label')
        need(type(items) is list and 1<=len(items)<=16,'Invalid template count');out[label]=[]
        for row in items:
            need(type(row) is dict and set(row)=={'width','pixels'} and type(row['width']) is int and 36<=row['width']<=80,'Invalid template shape')
            need(type(row['pixels']) is str and len(row['pixels'])==24*row['width'],'Invalid template data')
            a=np.frombuffer(bytes.fromhex(row['pixels']),np.uint8).reshape(12,row['width']).astype(np.float32)/255
            need(float(a.sum())>=30,'Blank template');out[label].append(a)
    return out


def classify(roi,bank):
    out={'reference_amount_candidate':None,'distance':None,'margin':None,'reference_only':True,'payout_verified':False}
    a=feature(roi)
    if a is None:return out
    scores=sorted((min(distance(a,b) for b in vv),k) for k,vv in bank.items());need(len(scores)>=2,'Missing competitors')
    d,label=scores[0];gap=scores[1][0]-d;out.update(distance=d,margin=gap)
    if d<=MAX_DISTANCE and gap>=MIN_MARGIN:out['reference_amount_candidate']=label
    return out


def scan(im,table,bank):
    need(im.size==(1504,696) and type(table) is int and 1<=table<=4,'Unsupported geometry')
    if detect(im,table)!='pppoker':return []
    x=STARTS[table-1];return [{'seat':s,**classify(im.crop((x+a,b,x+c,d)),bank)} for s,(a,b,c,d) in REGIONS.items()]


def run(root,bank_path):
    root=Path(root);p=root/'manifest.json';need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=32*2**20,'Invalid manifest')
    raw=p.read_bytes();m=json.loads(raw);need(m.get('variant')==5 and m.get('status')=='MIXED_LAYOUT_DISPLAY_REVIEW_ONLY' and 0<len(m['frames'])<=120,'Wrong manifest')
    bh=hashlib.sha256(Path(bank_path).read_bytes()).hexdigest();bank=load_bank(bank_path);rows=[];seen=set()
    for f in m['frames']:
        name=f['file'];q=root/'prints'/name;need(name not in seen and Path(name).name==name and q.is_file() and not q.is_symlink() and not q.parent.is_symlink() and q.stat().st_size<=8*2**20,'Invalid print');seen.add(name)
        data=q.read_bytes();need(hashlib.sha256(data).hexdigest()==f['sha256'],'Print hash mismatch')
        with Image.open(io.BytesIO(data)) as im:
            im=im.convert('RGB')
            for t in range(1,5):
                for r in scan(im,t,bank):
                    if r['distance'] is not None:rows.append({'file':name,'pts':f['pts'],'table_id':t,'sha256':f['sha256'],**r})
    need(p.read_bytes()==raw and hashlib.sha256(Path(bank_path).read_bytes()).hexdigest()==bh,'Input changed')
    return {'variant':5,'status':'KNOWN_PAYOUT_REFERENCE_MATCHES_ONLY','source_sha256':m['source_sha256'],'manifest_sha256':hashlib.sha256(raw).hexdigest(),'bank_sha256':bh,'rows':rows,'payouts_verified':False,'financial_results_verified':False,'strategy_authorized':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');p.add_argument('bank');p.add_argument('output');a=p.parse_args(argv);r=run(a.report,a.bank)
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    return 0
if __name__=='__main__':raise SystemExit(main())
