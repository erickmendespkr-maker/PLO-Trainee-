"""Rebuild PPPoker rank templates from local, hash-bound annotated frames."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
from plo5_fourcolor_cards import train, RANKS, SUITS


def rebuild(rows, folder):
    if type(rows) is not list or not rows:
        raise ValueError('Expected labeled frames')
    folder=Path(folder)
    seen=set(); samples=[]; last=-1
    for row in rows:
        t=row['requested_seconds']
        if type(t) is not int or t<=last or t<0 or row['partition']!='train':
            raise ValueError('Use increasing training frames only')
        last=t
        p=folder/f'{t:04}.png'
        if not p.is_file() or p.is_symlink():raise ValueError('Missing local frame')
        raw=p.read_bytes(); h=hashlib.sha256(raw).hexdigest()
        if h!=row['sha256'] or h in seen:raise ValueError('Changed or duplicate frame')
        seen.add(h)
        with Image.open(p) as im:rgb=im.convert('RGB')
        if rgb.size!=(1504,696):raise ValueError('Wrong frame geometry')
        truth=row['truth']
        if type(truth) is not list or len(truth)!=4:raise ValueError('Four table labels required')
        for t,pair in enumerate(truth,1):
            if type(pair) is not list or len(pair)!=2 or any(type(x) is not str for x in pair):raise ValueError('Invalid field labels')
            known=[]
            for field,declared in zip(('hero','board'),pair):
                if declared=='?':continue
                cards=declared.split()
                if len(cards) not in ((5,) if field=='hero' else (0,3,4,5)) or any(len(c)!=2 or c[0] not in RANKS or c[1] not in SUITS for c in cards):raise ValueError('Invalid cards')
                known.extend(cards);samples.append((rgb,t,field,cards))
            if len(known)!=len(set(known)):raise ValueError('Duplicate physical card')
    return {r:[[g.hex(),a,f] for g,a,f in vv] for r,vv in train(samples).items()}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('labels');p.add_argument('frames');p.add_argument('output');a=p.parse_args(argv)
    rows=json.loads(Path(a.labels).read_text(encoding='utf-8'));out=Path(a.output)
    if out.exists() or out.is_symlink():raise ValueError('New bank file required')
    bank=rebuild(rows,a.frames)
    with out.open('x',encoding='utf-8') as f:json.dump(bank,f)
    print(json.dumps({'templates':sum(map(len,bank.values())),'training_frames':len(rows),'cards_verified':False}))
    return 0

if __name__=='__main__':raise SystemExit(main())
