"""Exact public-board texture descriptors, not a strategic abstraction."""
from collections import Counter
from itertools import combinations
RANKS="23456789TJQKA"
WINDOWS=[frozenset(range(i,i+5)) for i in range(9)]+[frozenset((12,0,1,2,3))]
def classify(board):
    if type(board) not in (list,tuple) or len(board) not in (3,4,5) or any(type(c) is not str or len(c)!=2 or c[0] not in RANKS or c[1] not in "cdhs" for c in board) or len(set(board))!=len(board):
        raise ValueError("Invalid board")
    ranks=Counter(RANKS.index(c[0]) for c in board)
    suits=Counter(c[1] for c in board)
    triples=set(frozenset(t) for t in combinations(ranks,3))
    straight_pairs=set()
    for t in triples:
        for w in WINDOWS:
            if t<=w:straight_pairs.add(tuple(sorted(w-t)))
    return dict(street={3:"flop",4:"turn",5:"river"}[len(board)],rank_pattern=sorted(ranks.values(),reverse=True),suit_pattern=sorted(suits.values(),reverse=True),paired=any(v>=2 for v in ranks.values()),flush_possible=any(v>=3 for v in suits.values()),straight_possible=bool(straight_pairs),straight_hole_rank_pairs=[tuple(RANKS[i] for i in p) for p in sorted(straight_pairs)],quads_possible=any(v>=2 for v in ranks.values()),full_house_possible=any(v>=2 for v in ranks.values()),distinct_ranks=len(ranks))
def selftest():
    assert classify(["As","2s","3s"])["straight_possible"]
    assert ("4","5") in classify(["As","2s","3s"])["straight_hole_rank_pairs"]
    assert classify(["As","2s","3s"])["flush_possible"]
    assert not classify(["As","7d","2c"])["straight_possible"]
    assert classify(["As","Ad","2c"])["full_house_possible"]
    assert not classify(["As","Ad","2c"])["flush_possible"]
    print("PASS board texture fixtures")
if __name__=="__main__":selftest()
