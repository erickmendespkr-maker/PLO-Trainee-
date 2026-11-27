"""Bounded native CFR+ forest adapter; chance is hidden in shared infoset IDs."""
import subprocess
from pathlib import Path
from math import isfinite
from plo5_pre_gto_context import need


def train(executable,nodes,deals,terminal,keys,iterations,timeout=120):
    path=Path(executable).resolve(strict=True)
    keys=sorted(keys); ids={k:i for i,k in enumerate(keys)}
    forest=[]; roots=[]
    def flatten(n,d,depth=0):
        need(depth<=128 and len(forest)<1000000,'Native forest budget exceeded')
        s,aa,ch,_,_=nodes[n]
        if ch and not aa:return flatten(ch[deals[d][3][len(s.board)-5]],d,depth)
        i=len(forest);forest.append(None)
        if not ch:forest[i]=f'-1 {terminal[n][d][0]:.17g} {terminal[n][d][1]:.17g}'
        else:
            p=s.pending[0]; children=[flatten(k,d,depth+1) for k in ch]
            forest[i]=' '.join(map(str,[p,ids[n,deals[d][p]],len(children),*children]))
        return i
    for d,deal in enumerate(deals):roots.append(f'{flatten(0,d)} {deal[2]:.17g}')
    need(len(forest)*iterations<=100000000,'Native work budget exceeded')
    payload='\n'.join([f'{len(forest)} {len(keys)} {len(deals)} {iterations}',*roots,*forest])+'\n'
    r=subprocess.run([str(path)],input=payload,capture_output=True,text=True,check=True,timeout=timeout)
    lines=r.stdout.splitlines();need(len(lines)==len(keys),'Native output size')
    out={}
    for i,line in enumerate(lines):
        fields=line.split();need(bool(fields) and int(fields[0])==i,'Native output identity')
        v=list(map(float,fields[1:]));need(len(v)==len(nodes[keys[i][0]][1]) and all(isfinite(x) and 0<=x<=1 for x in v) and abs(sum(v)-1)<1e-8,'Native probability vector')
        out[keys[i]]=v
    return out
