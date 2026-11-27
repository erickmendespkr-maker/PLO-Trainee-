"""PLO5 preflop betting-state transitions, standard two-blind cash games.
Integer incremental payments. No antes, straddles or short posted blinds.
Full raises and cumulative short all-in reopening supported.
No strategy or payoff estimation in this module.
"""
from dataclasses import dataclass, replace
from plo5_pre_gto_context import ORDERS, need, integer

VERSION = "plo5-preflop-tree-v1"

@dataclass(frozen=True)
class State:
    order: tuple
    initial: tuple
    paid: tuple
    folded: tuple
    pending: tuple
    last_level: tuple
    last_min: tuple
    minimum: int
    bb: int

    @property
    def remaining(self):
        return tuple(a-b for a,b in zip(self.initial,self.paid))

    @property
    def pot(self):
        return sum(self.paid)

    @property
    def actor(self):
        return self.order[self.pending[0]] if self.pending else None

    @property
    def active(self):
        return tuple(i for i,f in enumerate(self.folded) if not f)

    @property
    def status(self):
        if len(self.active)==1:
            return "fold_terminal"
        if self.pending:
            return "decision"
        return "all_in_showdown" if sum(self.remaining[i]>0 for i in self.active)<=1 else "flop_transition"


def prune(s):
    live=[i for i in s.active if s.remaining[i]>0]
    if len(s.active)<=1 or not live:
        return replace(s,pending=())
    pending=tuple(i for i in s.pending if i in live)
    if len(live)==1:
        i=live[0]
        pending=(i,) if s.paid[i]<max(s.paid[j] for j in s.active) else ()
    return replace(s,pending=pending)


def start(stacks,sb,bb):
    need(type(stacks) is dict and len(stacks) in ORDERS,"Expected 2-6 seats")
    order=ORDERS[len(stacks)]
    need(set(stacks)==set(order),"Invalid positions")
    initial=tuple(integer(stacks[p],1) for p in order)
    sb=integer(sb,1);bb=integer(bb,1)
    need(sb<bb and stacks["SB"]>=sb and stacks["BB"]>=bb,"Unsupported blinds")
    paid=tuple(sb if p=="SB" else bb if p=="BB" else 0 for p in order)
    n=len(order)
    return prune(State(order,initial,paid,(False,)*n,tuple(range(n)),(-1,)*n,(bb,)*n,bb,bb))


def bounds(s):
    need(s.pending,"No decision")
    i=s.pending[0]; left=s.remaining[i]
    high=max(s.paid[j] for j in s.active)
    call=max(0,high-s.paid[i])
    cap=min(left,s.pot+2*call)
    reopen=s.last_level[i]<0 or high-s.last_level[i]>=s.last_min[i]
    opponent_can_act=any(j!=i and s.remaining[j]>0 for j in s.active)
    full_min=call+s.minimum
    can_raise=reopen and opponent_can_act and cap>call and (cap>=full_min or cap==left)
    return dict(position=s.order[i],pot=s.pot,to_call=call,call_payment=min(call,left),
                full_raise_min=full_min,raise_max=cap if can_raise else None,
                raise_min=min(full_min,left) if can_raise else None,
                reopened=reopen,stack=left)


def actions(s, sizings=()):
    """Explicit raise payments plus legal minimum and maximum. Not exhaustive
    unless caller supplies every legal integer payment; no hidden rounding."""
    b=bounds(s); c=b["to_call"]
    out=[("fold",0),("call",b["call_payment"])] if c else [("check",0)]
    lo,hi=b["raise_min"],b["raise_max"]
    if lo is not None:
        vals={lo,hi}
        for x in sizings:
            integer(x)
            if lo<=x<=hi: vals.add(x)
        out.extend(("raise",x) for x in sorted(vals))
    return tuple(out)


def step(s,position,action,amount):
    b=bounds(s); integer(amount)
    need(position==b["position"],"Wrong actor")
    c=b["to_call"]; lo,hi=b["raise_min"],b["raise_max"]
    need((action=="fold" and amount==0 and c>0) or
         (action=="check" and amount==0 and c==0) or
         (action=="call" and c>0 and amount==b["call_payment"]) or
         (action=="raise" and lo is not None and lo<=amount<=hi),
         "Illegal action")
    i=s.pending[0]; paid=list(s.paid); folded=list(s.folded)
    levels=list(s.last_level); mins=list(s.last_min)
    paid[i]+=amount
    minimum=s.minimum; pending=s.pending[1:]
    if action=="fold": folded[i]=True
    if action=="raise":
        minimum=max(minimum,amount-c)
        pending=tuple(j for j in tuple(range(i+1,len(paid)))+tuple(range(i))
                      if not folded[j] and paid[j]<s.initial[j] and paid[j]<paid[i])
    levels[i]=max(paid[j] for j in range(len(paid)) if not folded[j])
    mins[i]=minimum
    return prune(replace(s,paid=tuple(paid),folded=tuple(folded),pending=pending,
                         last_level=tuple(levels),last_min=tuple(mins),minimum=minimum))


def replay(stacks,sb,bb,history):
    s=start(stacks,sb,bb)
    for e in history:
        need(type(e) is dict and set(e)=={"position","action","amount"},"Invalid event")
        s=step(s,e["position"],e["action"],e["amount"])
    return s


def selftest():
    s=start({"SB":200,"BB":200},1,2)
    assert bounds(s)["raise_max"]==5
    s=step(s,"SB","call",1)
    assert s.actor=="BB" and bounds(s)["raise_max"]==4
    assert step(s,"BB","check",0).status=="flop_transition"
    s=start({"UTG":200,"CO":200,"BTN":200,"SB":200,"BB":200},1,2)
    assert s.actor=="UTG" and bounds(s)["raise_max"]==7
    s=step(s,"UTG","raise",7)
    assert s.minimum==5 and bounds(s)["raise_max"]==24
    s=start({"CO":100,"BTN":9,"SB":11,"BB":100},1,2)
    s=step(s,"CO","raise",7)
    s=step(s,"BTN","raise",9)
    s=step(s,"SB","raise",10)
    s=step(s,"BB","call",9)
    assert s.actor=="CO" and not bounds(s)["reopened"]
    assert bounds(s)["raise_max"] is None
    s=step(s,"CO","call",4)
    assert s.status=="flop_transition"
    s=start({"CO":100,"BTN":9,"SB":12,"BB":100},1,2)
    s=step(s,"CO","raise",7)
    s=step(s,"BTN","raise",9)
    s=step(s,"SB","raise",11)
    s=step(s,"BB","call",10)
    assert bounds(s)["reopened"] and bounds(s)["raise_min"]==10
    s=start({"SB":5,"BB":100},1,2)
    s=step(s,"SB","raise",4)
    assert bounds(s)["raise_max"] is None
    assert step(s,"BB","call",3).status=="all_in_showdown"
    s=start({"SB":100,"BB":2},1,2)
    assert bounds(s)["raise_max"] is None
    assert step(s,"SB","call",1).status=="all_in_showdown"
    print("Preflop tree analytical checks passed")


if __name__=="__main__":
    selftest()
