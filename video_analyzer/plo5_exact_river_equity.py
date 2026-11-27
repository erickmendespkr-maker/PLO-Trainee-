"""Exact offline PLO5 river equity against one uniformly random legal holding."""
import argparse
from fractions import Fraction
from itertools import combinations
import json
from math import comb
from offline_omaha_showdown import _cards, RANKS, SUITS
from plo5_evaluator import evaluate
from plo5_rank_cache import fast_five

DECK=tuple(r+s for r in RANKS for s in SUITS)


def pair_codes(hero,board,remaining):
    """A five-card opponent beats/ties Hero iff one of its ten pairs does."""
    rank=evaluate(hero,board)['rank'];triples=tuple(combinations(board,3))
    n=len(remaining);codes=[[0]*n for _ in range(n)]
    for i,j in combinations(range(n),2):
        best=max(fast_five((remaining[i],remaining[j])+b) for b in triples)
        codes[i][j]=2 if best>rank else 1 if best==rank else 0
    return codes


def tally(codes):
    wins=ties=losses=0
    for a,b,c,d,e in combinations(range(len(codes)),5):
        x,y,z,w=codes[a],codes[b],codes[c],codes[d]
        code=max(x[b],x[c],x[d],x[e],y[c],y[d],y[e],z[d],z[e],w[e])
        if code==2:losses+=1
        elif code==1:ties+=1
        else:wins+=1
    return wins,ties,losses


def equity(hero,board,dead=()):
    h=_cards(hero,5);b=_cards(board,5)
    if not isinstance(dead,(list,tuple)) or len(dead)>37:raise ValueError('Invalid declared dead cards')
    d=_cards(dead,len(dead));used=set(h+b+d)
    if len(used)!=10+len(d):raise ValueError('Overlapping known cards')
    remaining=tuple(c for c in DECK if c not in used)
    wins,ties,losses=tally(pair_codes(h,b,remaining));total=comb(len(remaining),5)
    if wins+ties+losses!=total:raise RuntimeError('Enumeration coverage mismatch')
    share=Fraction(2*wins+ties,2*total)
    return {'variant':5,'method':'exact_uniform_single_opponent_river','hero':list(h),'board':list(b),'declared_dead':list(d),'opponent_holdings':total,'wins':wins,'ties':ties,'losses':losses,'equity_fraction':{'numerator':share.numerator,'denominator':share.denominator},'equity':float(share),'pair_evaluations':comb(len(remaining),2),'five_card_rank_evaluations':10*comb(len(remaining),2),'gto_solution':False,'range_conditioned':False,'financial_result_verified':False,'video_verified':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--hero',nargs=5,required=True);p.add_argument('--board',nargs=5,required=True);p.add_argument('--dead',nargs='*',default=[]);a=p.parse_args(argv)
    print(json.dumps(equity(a.hero,a.board,a.dead),indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
