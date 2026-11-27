"""Versioned offline PLO5 preflop game identity, independent of chosen action.
Physical suit labels are retained jointly across ranges. No strategy is inferred.
Betting legality is intentionally delegated to the future tree/replay layer.
"""
import hashlib
import json
import re

VERSION = "plo5-pre-gto-context-v1"
ORDERS = {2: ("SB","BB"), 3: ("BTN","SB","BB"),
          4: ("CO","BTN","SB","BB"), 5: ("MP","CO","BTN","SB","BB"),
          6: ("UTG","MP","CO","BTN","SB","BB")}

def need(ok, message):
    if not ok:
        raise ValueError(message)

def integer(x, minimum=0):
    need(type(x) is int and minimum <= x <= 10**12, "Invalid integer")
    return x

def cards(x):
    need(type(x) in (tuple,list) and len(x)==5, "Five private cards required")
    need(all(type(c) is str and re.fullmatch(r"[2-9TJQKA][cdhs]",c) for c in x), "Invalid card")
    need(len(set(x))==5,"Duplicate card")
    return sorted(x)

def normalize(context):
    fields={"variant","stacks","sb","bb","rake_bps","rake_cap","rake_on_fold",
            "history","ranges","tree_version","continuation_version"}
    need(type(context) is dict and set(context)==fields and type(context["variant"]) is int
         and context["variant"]==5,"Strict PLO5 schema required")
    s=context["stacks"]
    need(type(s) is dict and len(s) in ORDERS and set(s)==set(ORDERS[len(s)]),"Invalid positions")
    order=ORDERS[len(s)]
    stacks={p:integer(s[p],1) for p in order}
    sb=integer(context["sb"],1);bb=integer(context["bb"],1)
    need(sb<bb and stacks["SB"]>=sb and stacks["BB"]>=bb,"Invalid blinds")
    rate=integer(context["rake_bps"]);need(rate<=10000,"Invalid rake")
    cap=integer(context["rake_cap"])
    need(type(context["rake_on_fold"]) is bool,"Invalid rake flag")
    history=context["history"]
    need(type(history) is list and len(history)<=512,"Invalid history")
    h=[]
    for e in history:
        need(type(e) is dict and set(e)=={"position","action","amount"} and e["position"] in s,
             "Invalid history entry")
        action=e["action"];amount=integer(e["amount"])
        need(action in ("fold","check","call","raise") and
             ((amount==0) if action in ("fold","check") else (amount>0)),"Invalid action amount")
        h.append(dict(position=e["position"],action=action,amount=amount))
    ranges=context["ranges"]
    need(type(ranges) is dict and set(ranges)==set(s),"Range required per seat")
    rr={}
    for p in order:
        entries=ranges[p]
        need(type(entries) is list and 1<=len(entries)<=2598960,"Invalid range")
        seen=set(); rows=[]
        for e in entries:
            need(type(e) is dict and set(e)=={"cards","weight"},"Invalid holding")
            c=cards(e["cards"]); w=integer(e["weight"],1)
            need(tuple(c) not in seen,"Duplicate holding")
            seen.add(tuple(c));rows.append(dict(cards=c,weight=w))
        rr[p]=sorted(rows,key=lambda e:e["cards"])
    for k in ("tree_version","continuation_version"):
        need(type(context[k]) is str and 0<len(context[k])<=128,"Missing model version")
    return dict(schema=VERSION,variant=5,stacks=stacks,sb=sb,bb=bb,rake_bps=rate,
                rake_cap=cap,rake_on_fold=context["rake_on_fold"],history=h,ranges=rr,
                tree_version=context["tree_version"],continuation_version=context["continuation_version"])

def identity(context):
    normalized=normalize(context)
    payload=json.dumps(normalized,sort_keys=True,separators=(",",":"),allow_nan=False)
    return dict(key=hashlib.sha256(payload.encode()).hexdigest(),payload=payload,
                betting_legality_verified=False,gto_solution=False)

def selftest():
    a={"cards":["As","Kd","Qh","Jc","Ts"],"weight":1}
    b={"cards":["2s","3d","4h","5c","6s"],"weight":2}
    c=dict(variant=5,stacks={"SB":200,"BB":200},sb=1,bb=2,rake_bps=0,rake_cap=0,
           rake_on_fold=False,history=[],ranges={"SB":[a,b],"BB":[b]},
           tree_version="test",continuation_version="terminal")
    import copy
    d=copy.deepcopy(c);d["ranges"]["SB"].reverse();d["ranges"]["SB"][0]["cards"].reverse()
    assert identity(c)["key"]==identity(d)["key"]
    for field,value in [("bb",3),("rake_bps",500),("tree_version","other"),
                        ("continuation_version","other"),("history",[dict(position="SB",action="call",amount=1)])]:
        d=copy.deepcopy(c);d[field]=value
        assert identity(c)["key"]!=identity(d)["key"]
    d=copy.deepcopy(c);d["ranges"]["SB"][0]["weight"]=3
    assert identity(c)["key"]!=identity(d)["key"]
    d=copy.deepcopy(c);d["variant"]=6
    try: identity(d)
    except ValueError: pass
    else: raise AssertionError("Accepted PLO6")
    print("Context identity checks passed")

if __name__=="__main__":
    selftest()
