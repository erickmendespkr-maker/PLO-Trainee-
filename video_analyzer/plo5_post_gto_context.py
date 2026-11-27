"""Strict public context for offline PLO5 postflop models."""
from hashlib import sha256
import json
from plo5_pre_gto_context import cards,need,integer,ORDERS

VERSION="post-gto-context-v1"
DECK={r+s for r in "23456789TJQKA" for s in "cdhs"}

def normalize(c):
    need(type(c) is dict and set(c)=={"variant","board","seats","pot","bb","stacks","ranges","actor","rake_bps","rake_cap","tree_version","continuation_version"},"Invalid context schema")
    need(type(c["variant"]) is int and c["variant"]==5,"PLO5 only")
    board=c["board"]
    need(type(board) is list and len(board) in (3,4,5) and all(type(x) is str and x in DECK for x in board) and len(set(board))==len(board),"Invalid board")
    seats=c["seats"]
    need(type(seats) is list and 2<=len(seats)<=6 and len(set(seats))==len(seats) and all(p in ORDERS[6] for p in seats),"Invalid seats")
    need(c["actor"] in seats,"Invalid actor")
    need(type(c["stacks"]) is dict and set(c["stacks"])==set(seats),"Invalid stacks")
    stacks={p:integer(c["stacks"][p]) for p in seats}
    need(stacks[c["actor"]]>0,"Actor all-in")
    pot=integer(c["pot"],1);bb=integer(c["bb"],1)
    need(integer(c["rake_bps"])<=10000,"Invalid rake")
    integer(c["rake_cap"])
    need(type(c["ranges"]) is dict and set(c["ranges"])==set(seats),"Missing ranges")
    ranges={}
    for p in seats:
        rows=c["ranges"][p];need(type(rows) is list and 1<=len(rows)<=2598960,"Invalid range")
        seen=set();legal=[]
        for row in rows:
            need(type(row) is dict and set(row)=={"cards","weight"},"Invalid holding")
            h=tuple(cards(row["cards"]));w=integer(row["weight"],1)
            need(h not in seen,"Duplicate holding");seen.add(h)
            if not set(h)&set(board):legal.append(dict(cards=list(h),weight=w))
        need(legal,"Range fully blocked")
        ranges[p]=sorted(legal,key=lambda x:x["cards"])
    for k in ("tree_version","continuation_version"):
        need(type(c[k]) is str and 0<len(c[k])<=128,"Version required")
    return dict(c,schema=VERSION,board=sorted(board[:3])+board[3:],stacks=stacks,ranges=ranges)

def identity(c):
    n=normalize(c)
    return sha256(json.dumps(n,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def describe(c):
    n=normalize(c)
    return dict(key=identity(c),street={3:"flop",4:"turn",5:"river"}[len(n["board"])],
                spr_by_seat={p:n["stacks"][p]/n["pot"] for p in n["seats"]},
                legal_holdings={p:len(n["ranges"][p]) for p in n["seats"]},
                root_only=True,joint_range_feasibility_verified=False,gto_solution=False)

def selftest():
    a=dict(cards=["As","Ks","Qh","Jd","Tc"],weight=1)
    b=dict(cards=["Ah","Kh","Qs","Jc","Td"],weight=1)
    c=dict(variant=5,board=["2c","3d","4h"],seats=["BB","BTN"],actor="BB",pot=20,bb=2,stacks={"BB":180,"BTN":180},ranges={"BB":[a],"BTN":[b]},rake_bps=0,rake_cap=0,tree_version="test",continuation_version="test")
    assert describe(c)["spr_by_seat"]["BB"]==9
    assert identity(c)==identity(dict(c,board=c["board"][::-1]))
    assert identity(dict(c,board=c["board"]+["5s","6s"]))!=identity(dict(c,board=c["board"]+["6s","5s"]))
    try:normalize(dict(c,variant=6))
    except ValueError:pass
    else:raise AssertionError("PLO6 accepted")
    print("PASS postflop root context")
if __name__=="__main__":selftest()
