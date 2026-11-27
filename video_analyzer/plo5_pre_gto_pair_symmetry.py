"""Exact joint suit equivalence of ordered, disjoint PLO5 holdings.
Only equity reuse; strategic information sets and physical range weights stay intact.
"""
from itertools import permutations
from hashlib import sha256
from plo5_pre_gto_context import cards,need

SUITS="cdhs"
RANKS="23456789TJQKA"
PERMS=tuple(permutations(range(4)))

def joint_key(first,second):
    a,b=cards(first),cards(second)
    need(not set(a)&set(b),"Overlapping holdings")
    cols=[tuple(1 if r+s in a else 2 if r+s in b else 0 for r in RANKS) for s in SUITS]
    cols.sort()
    return bytes(v for c in cols for v in c)

def representative(key):
    need(type(key) is bytes and len(key)==52 and all(v in (0,1,2) for v in key),"Invalid pair key")
    h=[[],[]]
    for s in range(4):
        for r in range(13):
            v=key[13*s+r]
            if v:h[v-1].append(RANKS[r]+SUITS[s])
    need(joint_key(*h)==key,"Noncanonical pair key")
    return h

def pair_seed(key,seed):
    need(type(seed) is int and 0<=seed<2**64,"Invalid seed")
    return int.from_bytes(sha256(seed.to_bytes(8,"little")+key).digest()[:8],"little")

def selftest():
    a=["As","Ks","Qh","Jd","Tc"]
    b=["Ah","Kh","Qs","Jc","Td"]
    k=joint_key(a,b)
    for p in PERMS:
        f=lambda h:[c[0]+SUITS[p[SUITS.index(c[1])]] for c in h]
        assert joint_key(f(a),f(b))==k
    assert joint_key(*representative(k))==k
    c=["Ac","Kc","Qs","Jh","Td"]
    assert joint_key(a,c)!=k
    print("PASS joint suit symmetry, roundtrip and relative blocker distinction")
if __name__=="__main__":selftest()
