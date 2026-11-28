"""Offline PLO5 amount candidates for recorded 1504x696 four-table sessions.
Explicit per-table platform profiles; no inferred financial results.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import io
import hashlib
import json
import os
from pathlib import Path
from statistics import median
import re
import subprocess
import time
from PIL import Image, ImageOps

STARTS=(0,378,755,1131)
REGIONS={'pppoker':{'stack':(159,627,218,640),'pot':(151,261,230,279)},
         'suprema':{'stack':(160,598,220,611),'pot':(151,232,230,251)}}


def parse(text,platform,field):
    text=' '.join(text.strip().split())
    prefix=r'Pot:\s*' if platform=='pppoker' and field=='pot' else ''
    match=re.fullmatch(prefix+r'(\d{1,5}(?:[,.]\d{1,2})?)\s*BB',text,re.IGNORECASE)
    if not match or (platform=='pppoker' and field=='stack' and not any(c in match[1] for c in ',.')):return None
    return format(Decimal(match[1].replace(',','.')).normalize(),'f')


def read(image,table,platform,field):
    if image.size!=(1504,696) or type(table) is not int or not 1<=table<=4 or platform not in REGIONS or field not in ('stack','pot'):
        raise ValueError('Invalid recorded layout or field')
    x=STARTS[table-1];a,b,c,d=REGIONS[platform][field]
    roi=image.crop((x+a,b,x+c,d)).convert('L')
    if roi.getextrema()[1]-roi.getextrema()[0]<15:return {'value_bb':None,'raw':'','confidence':None}
    scale=6 if field=='stack' else 5
    mask=ImageOps.invert(ImageOps.autocontrast(roi)).resize((roi.width*scale,roi.height*scale),Image.Resampling.LANCZOS)
    mask=ImageOps.expand(mask,border=24 if field=='stack' else 18,fill=255)
    stream=io.BytesIO();mask.save(stream,format='PNG')
    env=dict(os.environ,OMP_THREAD_LIMIT='1')
    p=subprocess.run(['tesseract','stdin','stdout','--psm','7','tsv'],input=stream.getvalue(),capture_output=True,timeout=15,check=True,env=env)
    words=[];scores=[]
    for line in p.stdout.decode('utf-8').splitlines()[1:]:
        columns=line.split('\t',11)
        if len(columns)==12 and columns[0]=='5' and columns[11].strip():
            words.append(columns[11]);scores.append(float(columns[10]))
    raw=' '.join(words);confidence=min(scores)/100 if scores else None
    return {'value_bb':parse(raw,platform,field) if confidence is not None and confidence>=.65 else None,'raw':raw,'confidence':confidence}


def detect(image,table):
    """Candidate layout based on felt colors and the matching window title bar."""
    if image.size!=(1504,696) or type(table) is not int or not 1<=table<=4:
        raise ValueError('Invalid recorded layout')
    x=STARTS[table-1]
    def rgb(box):
        pixels=list(image.crop(box).convert('RGB').getdata())
        return tuple(median(c[i] for c in pixels) for i in range(3))
    header=rgb((x+120,5,x+245,22));green=blue=0
    for px,py in ((.25,.43),(.75,.43),(.30,.52),(.70,.52),(.30,.66),(.70,.66),(.5,.45),(.5,.75)):
        u,v=x+round(372*px),round(696*py);r,g,b=rgb((u-3,v-3,u+4,v+4))
        green+=g>=r+25 and g>=b+12 and 60<=g<=190
        blue+=b>=g+10 and g>=r+5 and 30<=b<=145
    if green>=4 and blue<=1 and max(header)<65 and max(header)-min(header)<=15:return 'pppoker'
    if blue>=4 and green<=1 and min(header)>=235:return 'suprema'
    return None


def scan(image,platforms=None,workers=3):
    if (platforms is not None and (len(platforms)!=4 or any(p not in REGIONS for p in platforms))) or type(workers) is not int or not 1<=workers<=3:
        raise ValueError('Invalid platform profiles or workers')
    image=image.convert("RGB")
    detected=[detect(image,t) for t in range(1,5)]
    jobs=[(t,p,f) for t,p in enumerate(detected,1) for f in ('stack','pot')]
    def task(j):
        t,p,f=j
        active=p is not None and (platforms is None or platforms[t-1]==p)
        result=read(image,t,p,f) if active else {'value_bb':None,'raw':'','confidence':None}
        return {'table_id':t,'platform':p,'field':f,**result,'layout_candidate_active':active,'financial_result_verified':False}
    with ThreadPoolExecutor(max_workers=workers) as pool:return list(pool.map(task,jobs))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('frame');p.add_argument('--platforms',default='auto');a=p.parse_args()
    start=time.perf_counter()
    raw=Path(a.frame).read_bytes()
    with Image.open(io.BytesIO(raw)) as im:rows=scan(im.convert('RGB'),None if a.platforms=='auto' else a.platforms.split(','))
    print(json.dumps({'variant':5,'status':'DISPLAY_CANDIDATES_ONLY','frame_sha256':hashlib.sha256(raw).hexdigest(),'observations':rows,'wall_seconds':time.perf_counter()-start,'financial_result_verified':False},indent=2))
if __name__=='__main__':main()
