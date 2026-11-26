"""Offline preflop displayed stake candidates; amounts do not prove forced blinds."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
from PIL import Image,ImageOps
import numpy as np
from plo5_mixed_money import STARTS,detect,parse
from plo5_singleflight import SingleFlight

# (text ROI, chip center). Suprema upper/lower left calibrated; other seats unknown.
REGIONS={
 'pppoker':{'top':((177,174,230,190),(167,181)), 'upper_right':((253,261,299,278),(243,269)), 'lower_right':((253,459,299,476),(243,467)), 'hero_bottom':((177,522,230,538),(167,529)), 'lower_left':((98,459,149,476),(89,467)), 'upper_left':((98,261,149,278),(89,269))},
 'suprema':{'lower_left':((78,426,125,440),(104,415)), 'upper_left':((63,231,124,249),(94,224))}}


def chip_present(im,platform):
    a=np.asarray(im.convert('RGB'),dtype=np.int16);r,g,b=a.transpose(2,0,1)
    if platform=='pppoker':return int(((r>=125)&(r>g+35)&(r>b+25)).sum())>=8
    return int(((r>=135)&(g>=150)&(b>=150)&(np.maximum(np.maximum(r,g),b)-np.minimum(np.minimum(r,g),b)<=65)).sum())>=12


def read_text(roi,platform):
    mask=ImageOps.invert(ImageOps.autocontrast(roi.convert('L'))).resize((roi.width*6,roi.height*6),Image.Resampling.LANCZOS)
    mask=ImageOps.expand(mask,border=24,fill=255);stream=io.BytesIO();mask.save(stream,format='PNG')
    p=subprocess.run(['tesseract','stdin','stdout','--psm','7','tsv'],input=stream.getvalue(),capture_output=True,timeout=15,check=True,env=dict(os.environ,OMP_THREAD_LIMIT='1'))
    words=[];scores=[]
    for l in p.stdout.decode('utf-8').splitlines()[1:]:
        c=l.split('\t',11)
        if len(c)==12 and c[0]=='5' and c[11].strip():words.append(c[11]);scores.append(float(c[10])/100)
    raw=' '.join(words);confidence=min(scores) if scores else None
    return {'raw':raw,'confidence':confidence,'value_bb':parse(raw,platform,'bet') if confidence is not None and confidence>=.75 else None}


class Reader:
    def __init__(self,capacity=256):self.cache=SingleFlight(capacity)
    def scan(self,image,table):
        p=detect(image,table);x=STARTS[table-1];rows=[]
        for seat,(box,(u,v)) in REGIONS.get(p,{}).items():
            a,b,c,d=box;roi=image.crop((x+a,b,x+c,d)).convert('L');chip=image.crop((x+u-8,v-8,x+u+9,v+9))
            present=chip_present(chip,p)
            if present:
                result=self.cache.get((p,roi.size,roi.tobytes()),lambda:read_text(roi,p))
            else:result={'value_bb':None,'raw':'','confidence':None}
            rows.append({'seat':seat,'chip_pattern_candidate':present,**result,'bet_verified':False})
        return {'table_id':table,'platform':p,'stakes':rows,'all_stakes_verified':False}


def compare(group,obs,pot):
    if group['table_id']!=obs['table_id'] or group['platform']!=obs['platform']:raise ValueError('Roster/amount mismatch')
    positions=group['positions_if_standard_blinds_and_full_roster'];sb=next((s for s,v in positions.items() if v in ('SB','BTN/SB')),None);bb=next((s for s,v in positions.items() if v=='BB'),None)
    amounts={r['seat']:r['value_bb'] for r in obs['stakes']}
    match=sb is not None and bb is not None and amounts.get(sb)=='0.5' and amounts.get(bb)=='1'
    extra=any(v is not None and v!='0' for s,v in amounts.items() if s not in (sb,bb))
    return {'expected_sb':sb,'expected_bb':bb,'displayed_amounts_match':match,'other_positive_stake_detected':extra,'pot_1_5_candidate':pot=='1.5','status':'STANDARD_BLIND_AMOUNTS_COMPATIBLE_CANDIDATE' if match and not extra and pot=='1.5' else 'INCONCLUSIVE_OR_OTHER_ACTION','blinds_verified':False,'positions_verified':False,'strategy_authorized':False}


def run(root):
    root=Path(root);p=root/'manifest.json';raw=p.read_bytes();m=json.loads(raw)
    if m.get('variant')!=5 or m.get('status')!='MIXED_LAYOUT_DISPLAY_REVIEW_ONLY':raise ValueError('Wrong manifest')
    byfile={r['file']:r for r in m['frames']};reader=Reader();out=[]
    for g in m.get('preflop_roster_candidates',[]):
        f=g['first']['file'];t=g['table_id']
        if Path(f).name!=f or f not in byfile or byfile[f]['pts']!=g['first']['pts']:raise ValueError('Unbound evidence')
        row=byfile[f];path=root/'prints'/f
        if path.is_symlink() or path.parent.is_symlink():raise ValueError('Unsafe print')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('Print hash mismatch')
        with Image.open(io.BytesIO(data)) as im:obs=reader.scan(im.convert('RGB'),t)
        pot=next((r['value_bb'] for r in row['observations'] if r['table_id']==t and r['field']=='pot' and r['platform']==g['platform']),None)
        out.append({'first':g['first'],'table_id':t,'platform':g['platform'],'observations':obs,'comparison':compare(g,obs,pot),'pot_bb_candidate':pot})
    if p.read_bytes()!=raw:raise ValueError('Manifest changed')
    return {'variant':5,'status':'PREFLOP_DISPLAY_AMOUNTS_ONLY','manifest_sha256':hashlib.sha256(raw).hexdigest(),'rows':out,'cache':reader.cache.stats(),'blinds_verified':False,'positions_verified':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');p.add_argument('output');a=p.parse_args(argv);r=run(a.report)
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    return 0
if __name__=='__main__':raise SystemExit(main())
