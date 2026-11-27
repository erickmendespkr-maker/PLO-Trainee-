"""Extend an existing PPPoker rank bank with hash-bound dim Hero glyphs."""
import argparse, hashlib, json
from pathlib import Path
from PIL import Image
from plo5_fourcolor_cards import RANKS, SUITS, load_bank, regions, feature, detect


def dim(roi):
    pixels=list(roi.convert('RGB').getdata())
    neutral=sorted(max(p) for p in pixels if max(p)-min(p)<18 and min(p)>80)
    return len(neutral)>.35*len(pixels) and 110<=neutral[int(.7*(len(neutral)-1))]<=155


def extend(bank, rows, folder):
    result={r:list(v) for r,v in bank.items()};seen=set();folder=Path(folder)
    if not isinstance(rows,list) or not rows:raise ValueError('Training labels required')
    for row in rows:
        name,t,cs=row['file'],row['table_id'],row['hero_cards']
        if row['partition']!='train' or Path(name).name!=name or type(t) is not int or not 1<=t<=4 or (name,t) in seen or type(cs) is not list or len(cs)!=5 or any(type(c) is not str or len(c)!=2 or c[0] not in RANKS or c[1] not in SUITS for c in cs) or len(set(cs))!=5:raise ValueError('Invalid dim training label')
        seen.add((name,t));p=folder/name
        if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Training frame mismatch')
        with Image.open(p) as im:im=im.convert('RGB')
        if im.size!=(1504,696) or detect(im,t)!='pppoker':raise ValueError('Wrong geometry or platform')
        for i,c in enumerate(cs):
            if not all(dim(x) for x in regions(im,t,'hero',i)):continue
            a,b,sig,bg,bs,empty=feature(im,t,'hero',i)
            if a!=b or a!=c[1] or sig is None or empty or bg<=.25 or bs<=.30:continue
            template=(*sig,'hero')
            if template not in result[c[0]] and len(result[c[0]])<128:result[c[0]].append(template)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bank');p.add_argument('labels');p.add_argument('frames');p.add_argument('output');a=p.parse_args(argv)
    rows=json.loads(Path(a.labels).read_bytes());bank=load_bank(a.bank);new=extend(bank,rows,a.frames)
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump({r:[[g.hex(),s,k] for g,s,k in v] for r,v in new.items()},f)
    print(json.dumps({'original_templates':sum(map(len,bank.values())),'new_templates':sum(map(len,new.values())),'cards_verified':False}))
    return 0
if __name__=='__main__':raise SystemExit(main())
