"""Restricted postflop public betting state. Integer chip payments.
Root assumes a settled previous street, explicit postflop seat order, no
pre-existing side pots. Chance transitions are separate from betting.
"""
from dataclasses import dataclass,replace
from plo5_pre_gto_context import need,integer

VERSION="post-gto-tree-v1"

@dataclass(frozen=True)
class State:
    order:tuple
    board:tuple
    base_pot:int
    remaining:tuple
    paid:tuple
    total_paid:tuple
    folded:tuple
    pending:tuple
    last_level:tuple
    last_min:tuple
    minimum:int
    bb:int

    @property
    def active(self):return tuple(i for i,f in enumerate(self.folded) if not f)
    @property
    def pot(self):return self.base_pot+sum(self.total_paid)
    @property
    def actor(self):return self.order[self.pending[0]] if self.pending else None
    @property
    def status(self):
        if len(self.active)==1:return "fold_terminal"
        if self.pending:return "decision"
        if sum(self.remaining[i]>0 for i in self.active)<=1:return "all_in_showdown"
        return "river_showdown" if len(self.board)==5 else "chance_transition"

def prune(s):
    live=[i for i in s.active if s.remaining[i]>0]
    if len(s.active)==1 or not live:return replace(s,pending=())
    p=tuple(i for i in s.pending if i in live)
    if len(live)==1:
        i=live[0]
        p=(i,) if s.paid[i]<max(s.paid[j] for j in s.active) else ()
    return replace(s,pending=p)

def start(context):
    from plo5_post_gto_context import normalize
    c=normalize(context);order=tuple(c["seats"]);n=len(order)
    rem=tuple(c["stacks"][p] for p in order)
    pending=tuple(i for i in range(n) if rem[i])
    need(pending and order[pending[0]]==c["actor"],"Actor must be first live seat in postflop order")
    return prune(State(order,tuple(c["board"]),c["pot"],rem,(0,)*n,(0,)*n,(False,)*n,pending,(-1,)*n,(c["bb"],)*n,c["bb"],c["bb"]))

def bounds(s):
    need(s.pending,"No decision")
    i=s.pending[0];high=max(s.paid[j] for j in s.active)
    call=high-s.paid[i];left=s.remaining[i]
    cap=min(left,s.pot+2*call)
    reopen=s.last_level[i]<0 or high-s.last_level[i]>=s.last_min[i]
    full=call+s.minimum
    can=reopen and any(j!=i and s.remaining[j]>0 for j in s.active) and cap>call and (cap>=full or cap==left)
    return dict(position=s.actor,to_call=call,call_payment=min(call,left),stack=left,pot=s.pot,raise_min=min(full,left) if can else None,raise_max=cap if can else None,reopened=reopen)

def actions(s,pot_bps=(5000,10000),include_min=False):
    b=bounds(s);c=b["to_call"]
    out=[("fold",0),("call",b["call_payment"])] if c else [("check",0)]
    lo,hi=b["raise_min"],b["raise_max"]
    need(type(pot_bps) in (list,tuple) and len(pot_bps)<=16,"Invalid sizings")
    need(type(include_min) is bool,"Invalid minimum flag")
    need(all(type(f) is int and 1<=f<=10000 for f in pot_bps),"Invalid pot fraction")
    if lo is not None:
        sizes={hi}
        if include_min:sizes.add(lo)
        for f in pot_bps:
            x=c+(s.pot+c)*f//10000
            if lo<=x<=hi:sizes.add(x)
        out.extend(("raise" if c else "bet",x) for x in sorted(sizes))
    return tuple(out)

def step(s,position,action,amount):
    b=bounds(s);integer(amount);need(position==s.actor,"Wrong actor")
    c=b["to_call"];lo,hi=b["raise_min"],b["raise_max"]
    aggressive=action==("raise" if c else "bet")
    need((action=="fold" and c>0 and amount==0) or (action=="check" and c==0 and amount==0) or (action=="call" and c>0 and amount==b["call_payment"]) or (aggressive and lo is not None and lo<=amount<=hi),"Illegal action")
    i=s.pending[0];n=len(s.order)
    paid=list(s.paid);total=list(s.total_paid);rem=list(s.remaining);folded=list(s.folded);levels=list(s.last_level);mins=list(s.last_min)
    paid[i]+=amount;total[i]+=amount;rem[i]-=amount
    pending=s.pending[1:];minimum=s.minimum
    if action=="fold":folded[i]=True
    if aggressive:
        minimum=max(minimum,amount-c)
        pending=tuple(j for j in tuple(range(i+1,n))+tuple(range(i)) if not folded[j] and rem[j]>0 and paid[j]<paid[i])
    levels[i]=max(paid[j] for j in range(n) if not folded[j]);mins[i]=minimum
    return prune(replace(s,paid=tuple(paid),total_paid=tuple(total),remaining=tuple(rem),folded=tuple(folded),pending=pending,last_level=tuple(levels),last_min=tuple(mins),minimum=minimum))

def advance(s,card):
    from plo5_post_gto_context import DECK
    need(s.status=="chance_transition","Not a street transition")
    need(type(card) is str and card in DECK and card not in s.board,"Invalid community card")
    # Private-card blockers must be applied by the chance engine.
    n=len(s.order)
    return prune(replace(s,board=s.board+(card,),paid=(0,)*n,pending=tuple(i for i in s.active if s.remaining[i]>0),last_level=(-1,)*n,last_min=(s.bb,)*n,minimum=s.bb))

def selftest():
    a=dict(cards=["As","Ks","Qh","Jd","Tc"],weight=1)
    b=dict(cards=["Ah","Kh","Qs","Jc","Td"],weight=1)
    c=dict(variant=5,board=["2c","3d","4h"],seats=["BB","BTN"],actor="BB",pot=20,bb=2,stacks={"BB":180,"BTN":180},ranges={"BB":[a],"BTN":[b]},rake_bps=0,rake_cap=0,tree_version=VERSION,continuation_version="test")
    s=start(c);assert actions(s)==(("check",0),("bet",10),("bet",20))
    s=step(s,"BB","bet",20);assert bounds(s)["raise_max"]==80
    s=step(s,"BTN","call",20);assert s.status=="chance_transition" and s.pot==60
    s=advance(s,"5s");assert s.actor=="BB" and s.paid==(0,0) and s.pot==60
    s=step(s,"BB","check",0);s=step(s,"BTN","check",0);s=advance(s,"6s")
    s=step(s,"BB","check",0);s=step(s,"BTN","check",0);assert s.status=="river_showdown"
    print("PASS postflop tree fixtures")
if __name__=="__main__":selftest()
