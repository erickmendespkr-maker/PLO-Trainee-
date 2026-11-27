"""Exact HU showdown equity over explicit weighted PLO5 ranges and runouts.
Not strategic EV. No rake, betting or future range updates.
"""
from itertools import combinations
from fractions import Fraction
from math import comb
from functools import lru_cache
from plo5_evaluator import evaluate
from plo5_post_gto_context import DECK
from plo5_pre_gto_context import cards,need

def equity(hero,board,opponents,*,max_runouts=100000):
    hero=tuple(cards(hero))
    need(type(board) in (list,tuple) and len(board) in (3,4,5) and all(type(x) is str and x in DECK for x in board) and len(set(board))==len(board),"Invalid board")
    board=tuple(board);known=set(hero)|set(board)
    need(len(known)==5+len(board),"Hero overlaps board")
    need(type(opponents) is list and 1<=len(opponents)<=2598960,"Invalid range")
    need(type(max_runouts) is int and 1<=max_runouts<=1000000,"Invalid work budget")
    missing=5-len(board);count=comb(42-len(board),missing)
    legal=[];seen=set();excluded=0
    for row in opponents:
        need(type(row) is dict and set(row)=={"cards","weight"},"Invalid holding")
        h=tuple(cards(row["cards"]));w=row["weight"]
        need(type(w) is int and 1<=w<=10**12,"Invalid weight")
        need(h not in seen,"Duplicate holding");seen.add(h)
        if known.intersection(h):excluded+=w
        else:
            legal.append((h,w))
            need(len(legal)*count<=max_runouts,"Exact enumeration budget exceeded")
    need(legal,"No legal opponent holding")
    @lru_cache(maxsize=2048)
    def hero_rank(b):return evaluate(hero,b)["rank"]
    wins=ties=losses=0
    for h,w in legal:
        for future in combinations(sorted(DECK-known-set(h)),missing):
            b=board+future
            a=hero_rank(b);v=evaluate(h,b)["rank"]
            if a>v:wins+=w
            elif a==v:ties+=w
            else:losses+=w
    total=wins+ties+losses
    q=Fraction(2*wins+ties,2*total)
    return dict(variant=5,method="exact_weighted_hu_runouts",equity=float(q),equity_fraction=[q.numerator,q.denominator],win=float(Fraction(wins,total)),tie=float(Fraction(ties,total)),loss=float(Fraction(losses,total)),legal_holdings=len(legal),excluded_weight=excluded,runouts_evaluated=len(legal)*count,hero_cache_hits=hero_rank.cache_info().hits,gto_solution=False)

def selftest():
    hero=["As","Ks","2c","3d","4h"]
    board=["Qs","Js","Ts","5c","6d"]
    villain=dict(cards=["Ah","Ad","Kh","Kd","7c"],weight=3)
    blocked=dict(cards=["As","8c","9c","Th","Jd"],weight=7)
    r=equity(hero,board,[villain,blocked])
    assert r["equity"]==1 and r["excluded_weight"]==7 and r["runouts_evaluated"]==1
    r=equity(hero,board[:4],[villain])
    assert r["equity"]==1 and r["runouts_evaluated"]==38
    print("PASS exact HU postflop equity")
if __name__=="__main__":selftest()
