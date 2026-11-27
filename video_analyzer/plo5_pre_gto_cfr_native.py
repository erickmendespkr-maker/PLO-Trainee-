"""Bounded subprocess adapter for the native HU CFR+ training kernel."""
import subprocess
from pathlib import Path
from math import isfinite
from plo5_pre_gto_context import need

def train(executable,nodes,deals,coefficients,keys,iterations,timeout=120,continuation=None):
    p=Path(executable).resolve(strict=True)
    keys=sorted(keys); ids={key:i for i,key in enumerate(keys)}
    need(0<len(keys)<=1000000 and len(nodes)*len(deals)*iterations<=100000000,"Native budget exceeded")
    lines=[f"{len(nodes)} {len(deals)} {len(keys)} {iterations}"]
    lines.extend(f"{w:.17g} {q:.17g}" for i,j,w,q in deals)
    for n,(s,aa,ch) in enumerate(nodes):
        if aa is None:
            a,b=coefficients[n];lines.append(f"-1 0 {a:.17g} {b:.17g}")
        else:
            actor=s.pending[0]
            lines.append(" ".join(map(str,[actor,len(ch),0,0,*ch,*(ids[n,d[actor]] for d in deals)])))
    if continuation is not None:
        leaves=sorted({n for n,i,j in continuation})
        need(len(leaves)*len(deals)<=2000000,"Native continuation budget exceeded")
        need(set(continuation)=={(n,i,j) for n in leaves for i,j,w,q in deals},"Incomplete continuation table")
        lines.append(f"CONT1 {len(leaves)}")
        for n in leaves:
            need(0<=n<len(nodes) and nodes[n][0].status=="flop_transition","Invalid continuation leaf")
            vals=[continuation[n,i,j] for i,j,w,q in deals]
            need(all(isfinite(v) and abs(v)<=1e12 for v in vals),"Invalid continuation value")
            lines.append(str(n)+" "+" ".join(format(v,".17g") for v in vals))
    proc=subprocess.run([str(p)],input="\n".join(lines)+"\n",capture_output=True,text=True,timeout=timeout,check=True)
    rows=proc.stdout.splitlines()
    need(len(rows)==len(keys),"Native output row count")
    result={}
    for i,line in enumerate(rows):
        fields=line.split()
        need(bool(fields) and int(fields[0])==i,"Native output identity")
        v=list(map(float,fields[1:]))
        need(len(v)==len(nodes[keys[i][0]][1]) and all(isfinite(x) and 0<=x<=1 for x in v) and abs(sum(v)-1)<1e-8,"Native probability vector")
        result[keys[i]]=v
    return result

def compare(executable):
    from plo5_pre_gto_hu import solve
    cases=[({"SB":2,"BB":2},[(0,0,1,.75)]),({"SB":5,"BB":5},[(0,0,1,.3),(1,0,2,.7)])]
    for stacks,pairs in cases:
        a=solve(stacks,1,2,pairs,iterations=200)
        b=solve(stacks,1,2,pairs,iterations=200,cfr_executable=executable)
        for field in ("value_sb_bb","nash_gap_bb","best_response_lower_bb","best_response_upper_bb"):
            assert abs(a[field]-b[field])<1e-8,field
        for x,y in zip(a["policy"],b["policy"]):
            assert (x["node"],x["holding"])==(y["node"],y["holding"])
            for u,v in zip(x["actions"],y["actions"]):
                assert abs(u["frequency"]-v["frequency"])<1e-8
                if u["ev_bb"] is None:assert v["ev_bb"] is None
                else:assert abs(u["ev_bb"]-v["ev_bb"])<1e-8
    print("PASS native/Python parity")

if __name__=="__main__":
    import sys
    compare(sys.argv[1])
