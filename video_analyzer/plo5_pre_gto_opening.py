"""Offline export of opening policies from a restricted preflop solve.
No imputation for absent holdings. Canonical suit classes are summaries only:
suit-dependent physical policies must not be replaced by their class average.
"""
from itertools import permutations
from collections import defaultdict
from math import isfinite
from plo5_pre_gto_context import cards, need

VERSION="pre-gto-opening-v1"
CLASSES=134459

def canonical(hand):
    h=cards(hand)
    columns=sorted(tuple(int(r+s in h) for r in "23456789TJQKA") for s in "cdhs")
    return "".join(str(columns[s][r]) for r in range(13) for s in range(4))

def export(report, *, hu_holdings=None):
    need(report.get("variant")==5 and report.get("gto_solution") is False,
         "Expected restricted PLO5 solver report")
    tree=report["tree"]; policy=report["policy"]
    need(type(tree) is list and tree and tree[0]["node"]==0,"Invalid tree")
    nodes={row["node"]:row for row in tree}
    need(len(nodes)==len(tree),"Duplicate node")
    # Only all-fold histories prior to the first voluntary entry.
    # Child ordering is bound to the action list at each node.
    rows=defaultdict(list)
    for row in policy:rows[row["node"]].append(row)
    result=[];node=0;seen=set()
    while nodes[node]["status"]=="decision":
        need(node not in seen,"Cycle in tree");seen.add(node)
        t=nodes[node];p=t["position"]; rr=rows[node]
        need(rr,"Missing policy")
        signature=None;physical={}
        for row in rr:
            need(row["position"]==p,"Position mismatch")
            h=row["holding"]
            if type(h) is int:
                need(hu_holdings is not None and p in hu_holdings and 0<=h<len(hu_holdings[p]),"HU holding mapping required")
                h=hu_holdings[p][h]
            h=tuple(cards(h));need(h not in physical,"Duplicate holding")
            aa=row["actions"]; sig=tuple((a["action"],a["amount"]) for a in aa)
            need(len(sig)==len(t["children"]) and len(set(sig))==len(sig),"Action/tree mismatch")
            need(all(a in ("fold","call","check","raise") and type(b) is int and b>=0 for a,b in sig),"Invalid action")
            if signature is None:signature=sig
            need(signature==sig,"Inconsistent action ordering")
            f=[a["frequency"] for a in aa]
            need(all(type(x) in (int,float) and isfinite(x) and 0<=x<=1 for x in f) and abs(sum(f)-1)<1e-8,"Invalid frequencies")
            physical[h]=f
        groups=defaultdict(list)
        for h,f in physical.items():groups[canonical(h)].append((h,f))
        out=[]
        for key,entries in sorted(groups.items()):
            out.append(dict(class_signature=key,observed_physical_holdings=len(entries),
                            physical_policies=[dict(cards=list(h),frequency=f) for h,f in sorted(entries)],
                            observed_mean_frequency=[sum(f[k] for h,f in entries)/len(entries) for k in range(len(signature))]))
        result.append(dict(node=node,position=p,actions=[dict(action=a,amount=b) for a,b in signature],
                           observed_classes=len(groups),missing_classes=CLASSES-len(groups),
                           coverage_fraction=len(groups)/CLASSES,classes=out))
        if ("fold",0) not in signature:break
        node=t["children"][signature.index(("fold",0))]
    return dict(version=VERSION,variant=5,opening_nodes=result,gto_solution=False,
                missing_policy="UNSOLVED",class_means_are_observed_unweighted_summaries=True,
                source_version=report.get("version"),source_target_reached=report.get("target_reached"),
                source_gap_bb=report.get("nashconv_bb",report.get("nash_gap_bb")))

def selftest():
    h=["As","Kd","Qh","Jc","Ts"]
    for p in permutations("cdhs"):
        m=dict(zip("cdhs",p))
        assert canonical(h)==canonical([c[0]+m[c[1]] for c in h])
    r={"variant":5,"gto_solution":False,"tree":[{"node":0,"position":"SB","status":"decision","children":[1,2]},
       {"node":1,"status":"fold_terminal"},{"node":2,"status":"all_in_showdown"}],
       "policy":[{"node":0,"position":"SB","holding":h,"actions":[{"action":"fold","amount":0,"frequency":.25},{"action":"raise","amount":5,"frequency":.75}]}]}
    e=export(r)["opening_nodes"][0]
    assert e["observed_classes"]==1 and e["missing_classes"]==134458
    assert e["classes"][0]["observed_mean_frequency"]==[.25,.75]
    print("Opening export analytical checks passed")

if __name__=="__main__":selftest()
