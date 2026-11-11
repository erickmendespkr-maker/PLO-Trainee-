"""Offline heads-up PLO5/PLO6 showdown equity with explicit fixed opponent holdings.

Monte Carlo over unknown board runouts only. This is NOT a range solver, GTO,
or inference from recorded footage. Exactly two hole and three board cards play.
"""
from __future__ import annotations
from collections import Counter
from itertools import combinations
import math
import random
import re

DECK = tuple(r+s for r in '23456789TJQKA' for s in 'cdhs')
RANK = {r:i+2 for i,r in enumerate('23456789TJQKA')}
CARD = re.compile(r'[2-9TJQKA][cdhs]\Z')

def validate(hero, villain, board):
    if not all(type(x) is list for x in (hero,villain,board)):
        raise ValueError('cards must be lists')
    if len(hero) not in (5,6) or len(villain)!=len(hero) or len(board) not in (0,3,4,5):
        raise ValueError('expected PLO5/PLO6 and 0/3/4/5 board cards')
    cards=hero+villain+board
    if any(type(c) is not str or not CARD.fullmatch(c) for c in cards) or len(cards)!=len(set(cards)):
        raise ValueError('invalid or duplicate card')

def five_rank(cards):
    values=sorted((RANK[c[0]] for c in cards),reverse=True)
    counts=Counter(values)
    groups=sorted(((n,v) for v,n in counts.items()),reverse=True)
    uniq=set(values)
    if 14 in uniq: uniq.add(1)
    straights=[high for high in range(5,15) if all(v in uniq for v in range(high-4,high+1))]
    straight=max(straights,default=0)
    flush=len({c[1] for c in cards})==1
    if flush and straight: return (8,straight)
    if groups[0][0]==4: return (7,groups[0][1],groups[1][1])
    if groups[0][0]==3 and groups[1][0]==2: return (6,groups[0][1],groups[1][1])
    if flush: return (5,*values)
    if straight: return (4,straight)
    if groups[0][0]==3: return (3,groups[0][1],*sorted((v for v in values if v!=groups[0][1]),reverse=True))
    pairs=sorted((v for n,v in groups if n==2),reverse=True)
    if len(pairs)==2: return (2,*pairs,next(v for v in values if v not in pairs))
    if len(pairs)==1: return (1,pairs[0],*sorted((v for v in values if v!=pairs[0]),reverse=True))
    return (0,*values)

def omaha_rank(hole, board):
    if len(board)!=5 or len(hole) not in (5,6):
        raise ValueError('requires 5 board and 5/6 private cards')
    return max(five_rank(a+b) for a in combinations(hole,2) for b in combinations(board,3))

def exact(hero,villain,board,max_runouts=200000):
    validate(hero,villain,board)
    remain=tuple(c for c in DECK if c not in set(hero+villain+board))
    k=5-len(board)
    count=math.comb(len(remain),k)
    if count>max_runouts: raise ValueError('exact enumeration exceeds configured cap')
    wins=ties=0
    for extra in combinations(remain,k):
        a=omaha_rank(hero,board+list(extra));b=omaha_rank(villain,board+list(extra))
        wins+=a>b;ties+=a==b
    return {'method':'exact_board_enumeration','trials':count,'wins':wins,'ties':ties,
            'losses':count-wins-ties,'equity':(wins+ties/2)/count,'board_runout_only':True,
            'opponent_holding_known_assumed':True,'gto_solution':False}

def monte_carlo(hero,villain,board,iterations=10000,seed=0):
    validate(hero,villain,board)
    if type(iterations) is not int or not 1<=iterations<=1000000 or type(seed) is not int or not 0<=seed<=2**32-1:
        raise ValueError('invalid iterations/seed')
    rng=random.Random(seed)
    remain=tuple(c for c in DECK if c not in set(hero+villain+board))
    k=5-len(board)
    wins=ties=0
    for _ in range(iterations):
        extra=rng.sample(remain,k)
        a=omaha_rank(hero,board+extra);b=omaha_rank(villain,board+extra)
        wins+=a>b;ties+=a==b
    equity=(wins+ties/2)/iterations
    # Conservative Hoeffding 95% half-width for bounded [0,1] payouts.
    half=math.sqrt(math.log(40)/(2*iterations))
    return {'method':'monte_carlo_board_runout','seed':seed,'trials':iterations,
            'wins':wins,'ties':ties,'losses':iterations-wins-ties,'equity':equity,
            'ci95_conservative':[max(0,equity-half),min(1,equity+half)],
            'ci_method':'Hoeffding bounded payoff, iid sampling with replacement',
            'board_runout_only':True,'opponent_holding_known_assumed':True,'gto_solution':False}
