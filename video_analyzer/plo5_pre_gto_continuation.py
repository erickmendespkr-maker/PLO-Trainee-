"""Explicit HU zero-sum continuation values, in BB, for offline restricted games.
No equity multiplier or inference from position alone. Caller supplies the
continuation utility for every nonterminal-flop leaf and legal private pair.
Values are net of all contributions from the beginning of the hand.
"""
from math import isfinite
from plo5_pre_gto_context import need
from plo5_pre_gto_store import digest

VERSION="pre-gto-continuation-table-v1"

def validate(nodes,deals,bb,table,source):
    need(type(source) is dict and set(source)=={"method","artifact_sha256"},"Continuation provenance required")
    need(type(source["method"]) is str and bool(source["method"].strip()),"Missing method")
    h=source["artifact_sha256"]
    need(type(h) is str and len(h)==64 and all(c in "0123456789abcdef" for c in h),"Invalid source hash")
    need(type(table) is list,"Expected continuation rows")
    leaves={n:s for n,(s,aa,ch) in enumerate(nodes) if s.status=="flop_transition"}
    keys={(n,i,j) for n in leaves for i,j,w,q in deals}
    need(len(table)==len(keys),"Continuation coverage mismatch")
    out={}
    for row in table:
        need(type(row) is dict and set(row)=={"node","sb_holding","bb_holding","net_sb_bb"},"Invalid continuation row")
        key=(row["node"],row["sb_holding"],row["bb_holding"])
        need(all(type(x) is int for x in key) and key in keys and key not in out,"Invalid or duplicate continuation key")
        v=row["net_sb_bb"];s=leaves[key[0]]
        bound=min(s.initial)/bb
        need(type(v) in (float,int) and isfinite(v) and -bound<=v<=bound,"Continuation outside effective stack")
        out[key]=float(v)
    return out,dict(version=VERSION,source=source,table_sha256=digest(sorted(table,key=lambda r:(r["node"],r["sb_holding"],r["bb_holding"]))),
                    covered_leaves=len(leaves),covered_pairs=len(out),gto_solution=False)

def selftest():
    from plo5_pre_gto_tree import start,step
    s=start({"SB":200,"BB":200},1,2)
    s=step(s,"SB","call",1);s=step(s,"BB","check",0)
    nodes=[(s,None,())];deals=[(0,0,1.,.5)]
    source=dict(method="synthetic fixture",artifact_sha256="0"*64)
    row=dict(node=0,sb_holding=0,bb_holding=0,net_sb_bb=1.25)
    v,m=validate(nodes,deals,2,[row],source)
    assert v[0,0,0]==1.25 and m["covered_pairs"]==1
    for rows in ([],[dict(row,net_sb_bb=101)],[dict(row,node=1)]):
        try:validate(nodes,deals,2,rows,source)
        except ValueError:pass
        else:raise AssertionError("Invalid continuation accepted")
    print("PASS continuation table contract")
if __name__=="__main__":selftest()
