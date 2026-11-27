"""Batch access to the C++ single-holding canonical state index (not policy IDs)."""
import subprocess
from pathlib import Path
from plo5_pre_gto_context import cards,need
from plo5_post_gto_context import DECK

SIZES={0:134459,3:1800975787,4:78124329712,5:3337988096872}
CARD_ID={r+s:i*4+j for i,r in enumerate('23456789TJQKA') for j,s in enumerate('cdhs')}


def rank_batch(executable,street,states,timeout=120):
    need(type(street) is int and street in SIZES,'Invalid street')
    need(type(states) is list and len(states)<=100000,'Invalid batch size')
    lines=[f'{street} rank {len(states)}']
    for h,b in states:
        h=cards(h)
        need(type(b) in (tuple,list) and len(b)==street and all(type(x) is str and x in DECK for x in b) and len(set(h+list(b)))==5+street,'Invalid board')
        lines.append(' '.join(str(CARD_ID[x]) for x in h+list(b)))
    p=subprocess.run([str(Path(executable).resolve(strict=True))],input='\n'.join(lines)+'\n',text=True,capture_output=True,check=True,timeout=timeout)
    ids=[int(x) for x in p.stdout.splitlines()]
    need(len(ids)==len(states) and all(0<=x<SIZES[street] for x in ids),'Invalid native IDs')
    return ids


def unrank_batch(executable,street,ids,timeout=120):
    need(type(street) is int and street in SIZES,'Invalid street')
    need(type(ids) is list and len(ids)<=100000 and all(type(x) is int and 0<=x<SIZES[street] for x in ids),'Invalid indices')
    p=subprocess.run([str(Path(executable).resolve(strict=True))],input=f'{street} unrank {len(ids)}\n'+'\n'.join(map(str,ids))+'\n',text=True,capture_output=True,check=True,timeout=timeout)
    rows=p.stdout.splitlines();need(len(rows)==len(ids),'Invalid native output')
    inverse={v:k for k,v in CARD_ID.items()};out=[]
    for row in rows:
        need(len(row)==52 and set(row)<={'0','1','2','3','4'},'Invalid native matrix')
        groups=[[inverse[i] for i,v in enumerate(row) if v==str(j)] for j in (1,2,3,4)]
        need([len(x) for x in groups]==[5,3 if street else 0,int(street>=4),int(street==5)],'Invalid native card counts')
        out.append((groups[0],groups[1]+groups[2]+groups[3]))
    return out
