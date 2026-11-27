"""Read explicit yellow +BB display candidates in recorded PPPoker only."""
import argparse, hashlib, io, json, os, re, subprocess
from pathlib import Path
from decimal import Decimal
from fractions import Fraction
import numpy as np
from PIL import Image, ImageOps
from plo5_mixed_money import STARTS, detect
from plo5_singleflight import SingleFlight

REGIONS={'top':(135,65,240,89),'upper_left':(0,177,80,202),'upper_right':(292,177,372,202),'lower_left':(0,374,80,399),'lower_right':(292,374,372,399),'hero_bottom':(135,539,240,561)}


def parse(raw):
    m=re.fullmatch(r'\+\s*(\d{1,5}[,.]\d{1,2})\s*BB',' '.join(raw.split()))
    if not m:return None
    n=Decimal(m[1].replace(',','.'))
    return format(n.normalize(),'f') if n>0 else None


def mask(roi):
    a=np.asarray(roi.convert('RGB'),dtype=np.int16);r,g,b=a.transpose(2,0,1)
    m=(r>=130)&(g>=120)&(r>b+60)&(g>b+60)&(abs(r-g)<100)
    if m.sum()<80:return None
    y,x=np.where(m)
    if x.max()-x.min()<24:return None
    y0=max(0,int(np.argmax(m.sum(axis=1)))-6);y1=min(roi.height,y0+13)
    return ImageOps.invert(ImageOps.autocontrast(roi.crop((max(0,int(x.min())-2),y0,min(roi.width,int(x.max())+3),y1)).convert('L')))


def ocr(im):
    im=ImageOps.expand(im.resize((im.width*6,im.height*6),Image.Resampling.LANCZOS),border=24,fill=255);s=io.BytesIO();im.save(s,format='PNG')
    p=subprocess.run(['tesseract','stdin','stdout','--psm','7','tsv'],input=s.getvalue(),capture_output=True,timeout=15,check=True,env=dict(os.environ,OMP_THREAD_LIMIT='1'))
    words=[];scores=[]
    for line in p.stdout.decode().splitlines()[1:]:
        c=line.split('\t',11)
        if len(c)==12 and c[0]=='5' and c[11].strip():words.append(c[11]);scores.append(float(c[10])/100)
    raw=' '.join(words);confidence=min(scores) if scores else None
    return {'raw':raw,'confidence':confidence,'displayed_plus_bb':parse(raw) if confidence is not None and confidence>=.75 else None}


class Reader:
    def __init__(self):self.cache=SingleFlight(256)
    def scan(self,image,t):
        k=detect(image,t);out=[]
        if k!='pppoker':return out
        for seat,(a,b,c,d) in REGIONS.items():
            x=STARTS[t-1];im=mask(image.crop((x+a,b,x+c,d)))
            if im is None:r={'raw':'','confidence':None,'displayed_plus_bb':None}
            else:r=self.cache.get((im.size,im.tobytes()),lambda:ocr(im))
            out.append({'seat':seat,'yellow_display_candidate':im is not None,**r,'payout_verified':False,'winner_verified':False})
        return out


def episodes(frames):
    """Group color-screened regions, retaining unreadable text and repeated amounts."""
    active={};out=[];previous=None;seen=set()
    for f in frames:
        pts=Fraction(f['pts']);name=f['file']
        if name in seen or (previous is not None and pts<=previous):raise ValueError('Unordered or duplicate samples')
        seen.add(name)
        if previous is None or int(pts//1)-int(previous//1)!=1 or pts-previous>Fraction(3,2):active.clear()
        previous=pts;next_active={}
        if set(f['tables'])!={'1','2','3','4'}:raise ValueError('Invalid table roster')
        for t in range(1,5):
            rows=f['tables'][str(t)]
            if rows and (len(rows)!=len(REGIONS) or {q['seat'] for q in rows}!=set(REGIONS)):raise ValueError('Invalid seat roster')
            for row in rows:
                if not row['yellow_display_candidate']:continue
                v=row['displayed_plus_bb'];seat=row['seat'];key=(t,seat)
                old=active.get(key)
                if old is None:
                    old={'table_id':t,'seat':seat,'first':{'file':name,'pts':str(pts)},'evidence':[],'samples':0,'payout_verified':False,'winner_verified':False};out.append(old)
                old['last']={'file':name,'pts':str(pts)};old['samples']+=1
                old['evidence'].append({'file':name,'pts':str(pts),'sha256':f['sha256'],'raw':row['raw'],'displayed_plus_bb':v})
                next_active[key]=old
        active=next_active
    for e in out:
        values=[q['displayed_plus_bb'] for q in e['evidence']];accepted={v for v in values if v is not None}
        agreed=len(accepted)==1 and any(a is not None and a==b for a,b in zip(values,values[1:]))
        e['repeated_displayed_plus_bb_candidate']=next(iter(accepted)) if agreed else None
        e['status']='REPEATED_PLUS_BB_TEXT_CANDIDATE' if agreed else 'YELLOW_REGION_REVIEW_ONLY'
    return out


def run(root):
    root=Path(root);p=root/'manifest.json'
    if not p.is_file() or p.is_symlink() or not 0<p.stat().st_size<=32*2**20:raise ValueError('Invalid manifest')
    raw=p.read_bytes();m=json.loads(raw)
    if m.get('variant')!=5 or m.get('status')!='MIXED_LAYOUT_DISPLAY_REVIEW_ONLY' or not 0<len(m['frames'])<=120:raise ValueError('Wrong manifest')
    frames=[];reader=Reader()
    for f in m['frames']:
        name=f['file'];q=root/'prints'/name
        if Path(name).name!=name or not q.is_file() or q.is_symlink() or q.parent.is_symlink() or q.stat().st_size>8*2**20:raise ValueError('Invalid print')
        data=q.read_bytes()
        if hashlib.sha256(data).hexdigest()!=f['sha256']:raise ValueError('Print hash mismatch')
        with Image.open(io.BytesIO(data)) as im:tables={str(t):reader.scan(im.convert('RGB'),t) for t in range(1,5)}
        frames.append({'file':name,'pts':f['pts'],'sha256':f['sha256'],'tables':tables})
    if p.read_bytes()!=raw:raise ValueError('Manifest changed')
    return {'variant':5,'status':'VISIBLE_PLUS_BB_CANDIDATES_ONLY','manifest_sha256':hashlib.sha256(raw).hexdigest(),'source_sha256':m['source_sha256'],'frames':frames,'episodes':episodes(frames),'cache':reader.cache.stats(),'payouts_verified':False,'financial_results_verified':False,'strategy_authorized':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');p.add_argument('output');a=p.parse_args(argv);r=run(a.report)
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    return 0
if __name__=='__main__':raise SystemExit(main())
