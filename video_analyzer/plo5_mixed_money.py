"""Offline PLO5 amount candidates for recorded 1504x696 four-table sessions.
Explicit per-table platform profiles; no inferred financial results.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time
from PIL import Image, ImageOps

STARTS=(0,378,755,1131)
REGIONS={'pppoker':{'stack':(159,627,218,640),'pot':(151,261,230,279)},
         'suprema':{'stack':(162,601,218,612),'pot':(151,232,230,251)}}


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


def scan(image,platforms,workers=3):
    if len(platforms)!=4 or any(p not in REGIONS for p in platforms) or type(workers) is not int or not 1<=workers<=3:
        raise ValueError('Four explicit platform profiles required')
    image=image.convert("RGB")
    jobs=[(t,p,f) for t,p in enumerate(platforms,1) for f in ('stack','pot')]
    def task(j):
        t,p,f=j;return {'table_id':t,'platform':p,'field':f,**read(image,t,p,f),'financial_result_verified':False}
    with ThreadPoolExecutor(max_workers=workers) as pool:return list(pool.map(task,jobs))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('frame');p.add_argument('--platforms',required=True);a=p.parse_args()
    start=time.perf_counter()
    with Image.open(a.frame) as im:rows=scan(im.convert('RGB'),a.platforms.split(','))
    print(json.dumps({'variant':5,'status':'DISPLAY_CANDIDATES_ONLY','observations':rows,'wall_seconds':time.perf_counter()-start,'financial_result_verified':False},indent=2))
if __name__=='__main__':main()
