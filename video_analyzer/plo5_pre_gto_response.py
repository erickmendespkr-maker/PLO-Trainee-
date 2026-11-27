"""Export restricted PLO5 decision policies at all preflop response nodes.
Replays every edge against the betting engine. No unobserved strategy inferred.
"""
from collections import defaultdict
from math import isfinite
from plo5_pre_gto_context import cards, need
from plo5_pre_gto_tree import start, step, bounds
from plo5_pre_gto_opening import canonical, CLASSES

VERSION="pre-gto-response-v1"

def classify(position,history):
    raises=[i for i,e in enumerate(history) if e["action"]=="raise"]
    acted=any(e["position"]==position and e["action"]!="fold" for e in history)
    calls_after=sum(e["action"]=="call" for e in history[raises[-1]+1:]) if raises else 0
    if not raises:
        spot="limped_pot" if any(e["action"]=="call" for e in history) else "unopened"
    else:
        spot="facing_open" if len(raises)==1 else "facing_"+str(len(raises)+1)+"bet"
    return dict(spot=spot,raise_count=len(raises),last_raiser=history[raises[-1]]["position"] if raises else None,
                callers_since_raise=calls_after,blind_defense=bool(raises) and position in ("SB","BB"),
                first_action=not acted)

def action_label(action,context):
    n=context["raise_count"]
    if action=="raise":
        if n==0:return "isolation_raise" if context["spot"]=="limped_pot" else "rfi"
        if n==1:return "squeeze" if context["callers_since_raise"] else "three_bet"
        return str(n+2)+"bet"
    if action=="call":
        if not n:return "limp"
        if not context["first_action"]:return "call_after_prior_action"
        return "blind_call" if context["blind_defense"] else "cold_call"
    return action

def export(report,stacks,sb,bb,*,hu_holdings=None):
    need(report.get("variant")==5 and report.get("gto_solution") is False,"Expected restricted PLO5 report")
    tree=report["tree"];nodes={t["node"]:t for t in tree}
    need(len(nodes)==len(tree) and 0 in nodes,"Invalid node identities")
    grouped=defaultdict(list)
    for row in report["policy"]:
        need(row["node"] in nodes,"Unknown policy node")
        grouped[row["node"]].append(row)
    visited=set();out=[]
    def visit(node,state,history):
        need(node in nodes and node not in visited,"Invalid tree edge")
        visited.add(node);t=nodes[node]
        need(t["position"]==state.actor and t["paid"]==list(state.paid) and t["status"]==state.status,
             "Tree replay mismatch")
        if not state.pending:
            need(not t["children"] and not grouped[node],"Unexpected terminal policy")
            return
        rr=grouped[node];need(rr,"Missing decision policy")
        context=classify(state.actor,history);sig=None;physical={};classes=set()
        for row in rr:
            need(row["position"]==state.actor,"Actor mismatch")
            h=row["holding"]
            if type(h) is int:
                need(hu_holdings is not None and state.actor in hu_holdings and 0<=h<len(hu_holdings[state.actor]),"HU mapping required")
                h=hu_holdings[state.actor][h]
            h=tuple(cards(h));need(h not in physical,"Duplicate holding")
            aa=row["actions"];ss=tuple((a["action"],a["amount"]) for a in aa)
            need(len(ss)==len(t["children"]) and len(set(ss))==len(ss),"Action mismatch")
            if sig is None:sig=ss
            need(sig==ss,"Inconsistent actions")
            fs=[a["frequency"] for a in aa]
            need(all(type(x) in (float,int) and isfinite(x) and 0<=x<=1 for x in fs) and abs(sum(fs)-1)<1e-8,"Invalid frequencies")
            physical[h]=fs;classes.add(canonical(h))
        b=bounds(state)
        out.append(dict(node=node,position=state.actor,history=history,context=context,
                        pot_chips=state.pot,to_call_chips=b["to_call"],remaining_stacks=list(state.remaining),
                        actions=[dict(action=a,amount=x,label=action_label(a,context),all_in=x==b["stack"]) for a,x in sig],
                        physical_policies=[dict(cards=list(h),class_signature=canonical(h),frequency=f) for h,f in sorted(physical.items())],
                        observed_classes=len(classes),missing_classes=CLASSES-len(classes)))
        for (a,x),child in zip(sig,t["children"]):
            visit(child,step(state,state.actor,a,x),history+[dict(position=state.actor,action=a,amount=x)])
    visit(0,start(stacks,sb,bb),[])
    need(len(visited)==len(nodes),"Unreachable tree nodes")
    return dict(version=VERSION,variant=5,decisions=out,missing_policy="UNSOLVED",
                source_version=report.get("version"),source_gap_bb=report.get("nashconv_bb",report.get("nash_gap_bb")),
                source_target_reached=report.get("target_reached"),gto_solution=False,
                betting_tree_replayed=True)

def selftest():
    h=[dict(position="UTG",action="raise",amount=7),dict(position="MP",action="call",amount=7)]
    c=classify("CO",h)
    assert action_label("raise",c)=="squeeze"
    assert action_label("call",c)=="cold_call"
    c=classify("BB",h)
    assert c["blind_defense"] and action_label("call",c)=="blind_call"
    c=classify("UTG",h+[dict(position="CO",action="raise",amount=24)])
    assert action_label("raise",c)=="4bet" and action_label("call",c)=="call_after_prior_action"
    print("Response classification checks passed")

if __name__=="__main__":selftest()
