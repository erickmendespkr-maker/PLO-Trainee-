"""Offline exact PLO5 turn equity versus one uniformly random opponent."""
import argparse, json
from fractions import Fraction
from itertools import combinations
from math import comb
from offline_omaha_showdown import _cards
from plo5_exact_river_equity import DECK
from plo5_rank_cache import fast_five


def cliques5(edges):
    """Count five-vertex cliques in a forward-only adjacency bitset graph."""
    count=0
    for a,tail in enumerate(edges):
        bs=tail
        while bs:
            bit=bs & -bs;bs^=bit;b=bit.bit_length()-1
            cs=bs & edges[b]
            while cs:
                bit=cs & -cs;cs^=bit;c=bit.bit_length()-1
                ds=cs & edges[c]
                while ds:
                    bit=ds & -ds;ds^=bit;d=bit.bit_length()-1
                    count+=(ds & edges[d]).bit_count()
    return count


def count_river(hero_rank,pool,river,base,added):
    n=len(pool);win=[0]*n;not_lost=[0]*n
    for (i,j),rank in base.items():
        if river in (i,j):continue
        best=max(rank,max(fast_five((pool[i],pool[j])+t) for t in added))
        if best<=hero_rank:
            not_lost[i]|=1<<j
            if best<hero_rank:win[i]|=1<<j
    w=cliques5(win);nl=cliques5(not_lost)
    return w,nl-w,comb(n-1,5)-nl


def equity(hero,board,dead=()):
    h=_cards(hero,5);b=_cards(board,4)
    if not isinstance(dead,(list,tuple)) or len(dead)>37:raise ValueError('Invalid dead cards')
    d=_cards(dead,len(dead));used=set(h+b+d)
    if len(used)!=9+len(d):raise ValueError('Overlapping known cards')
    pool=tuple(c for c in DECK if c not in used);n=len(pool)
    triples=tuple(combinations(b,3));pairs=tuple(combinations(b,2));hp=tuple(combinations(h,2))
    base={(i,j):max(fast_five((pool[i],pool[j])+t) for t in triples) for i,j in combinations(range(n),2)}
    hero_base=max(fast_five(p+t) for p in hp for t in triples)
    rows=[];w=t=l=0
    for i,card in enumerate(pool):
        added=tuple(p+(card,) for p in pairs);hr=max(hero_base,max(fast_five(p+q) for p in hp for q in added))
        a,c,z=count_river(hr,pool,i,base,added);w+=a;t+=c;l+=z
        total=comb(n-1,5);share=Fraction(2*a+c,2*total)
        rows.append({'river':card,'wins':a,'ties':c,'losses':z,'equity':float(share)})
    total=n*comb(n-1,5)
    if w+t+l!=total:raise RuntimeError('Enumeration coverage mismatch')
    share=Fraction(2*w+t,2*total)
    return {'variant':5,'method':'exact_uniform_single_opponent_turn','hero':list(h),'board':list(b),'declared_dead':list(d),'river_cards':n,'joint_outcomes':total,'wins':w,'ties':t,'losses':l,'equity':float(share),'equity_fraction':{'numerator':share.numerator,'denominator':share.denominator},'by_river':rows,'gto_solution':False,'range_conditioned':False,'video_verified':False,'financial_result_verified':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--hero',nargs=5,required=True);p.add_argument('--board',nargs=4,required=True);p.add_argument('--dead',nargs='*',default=[]);a=p.parse_args(argv)
    print(json.dumps(equity(a.hero,a.board,a.dead),indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
