"""Independent rank oracle, weighted exhaustive five-card classes and PLO5 tests."""
from collections import Counter
from fractions import Fraction
from itertools import combinations, combinations_with_replacement
from math import comb, prod
import random
import unittest

from plo5_evaluator import evaluate, showdown
from offline_omaha_showdown import _five

RANKS = '23456789TJQKA'
DECK = [r+s for r in RANKS for s in 'cdhs']


def oracle_five(cards):
    # Independent implementation: rank multiplicity pattern and consecutive differences.
    vals = sorted([RANKS.index(c[0])+2 for c in cards], reverse=True)
    unique = sorted(set(vals), reverse=True)
    flush = all(c[1] == cards[0][1] for c in cards)
    straight = 5 if unique == [14,5,4,3,2] else unique[0] if len(unique)==5 and unique[0]-unique[-1]==4 else 0
    ordered = sorted(unique, key=lambda x:(vals.count(x),x), reverse=True)
    pattern = tuple(vals.count(x) for x in ordered)
    if flush and straight: return (8,straight)
    if pattern==(4,1): return (7,*ordered)
    if pattern==(3,2): return (6,*ordered)
    if flush: return (5,*vals)
    if straight: return (4,straight)
    return ({(3,1,1):3,(2,2,1):2,(2,1,1,1):1,(1,1,1,1,1):0}[pattern],*ordered)


def oracle_omaha(hole,board):
    # Enumerate five-card subsets of the entire visible set; filter by provenance.
    h=set(hole)
    return max(oracle_five(c) for c in combinations(tuple(hole)+tuple(board),5) if len(h.intersection(c))==2)


class EvaluatorTests(unittest.TestCase):
    def test_weighted_exhaustive_five_card_rank_classes(self):
        # One representative for each rank multiset and possible flush status.
        # Weight by number of physical suit assignments, not by class count.
        totals=Counter(); distinct=set(); cases=0
        for ranks in combinations_with_replacement(RANKS,5):
            counts=Counter(ranks)
            if max(counts.values())>4: continue
            weight=prod(comb(4,n) for n in counts.values())
            if len(counts)==5:
                reps=[([r+'s' for r in ranks],4),([r+'cdhsc'[i] for i,r in enumerate(ranks)],weight-4)]
            else:
                reps=[([r+s for r,n in counts.items() for s in 'cdhs'[:n]],weight)]
            for cards,w in reps:
                rank=_five(cards)
                self.assertEqual(rank,oracle_five(cards),cards)
                totals[rank[0]]+=w;distinct.add(rank);cases+=1
        self.assertEqual(cases,7462)
        self.assertEqual(len(distinct),7462)
        self.assertEqual([totals[i] for i in range(9)],[1302540,1098240,123552,54912,10200,5108,3744,624,40])
        self.assertEqual(sum(totals.values()),comb(52,5))

    def test_exact_two_three_and_witness(self):
        h=['As','Ks','2c','3d','4h'];b=['Qs','Js','Ts','9d','8c']
        for n,count in ((3,10),(4,40),(5,100)):
            r=evaluate(h,b[:n]);self.assertEqual(r['rank'],(8,14))
            self.assertEqual(r['combinations_evaluated'],count)
            self.assertEqual(set(r['used_private']),{'As','Ks'})
            self.assertEqual(set(r['used_board']),{'Qs','Js','Ts'})
        self.assertEqual(evaluate(list(reversed(h)),list(reversed(b))),evaluate(h,b))

    def test_board_only_and_one_hole_flush_invalid(self):
        b=['As','Ks','Qs','Js','Ts']
        self.assertLess(evaluate(['2c','3d','4h','5c','6d'],b)['rank'][0],5)
        self.assertLess(evaluate(['9s','2d','3h','4c','5d'],b)['rank'][0],5)

    def test_wheel_and_tiebreak(self):
        self.assertEqual(evaluate(['Ac','2d','9c','Tc','Jc'],['3s','4h','5d'])['rank'],(4,5))
        b=['Ac','Ad','Kh','7s','2c']
        h1=['Ah','Kd','3c','4s','5d'];h2=['As','Kc','8s','9d','Tc']
        self.assertEqual(showdown([h1,h2],b)['winner_indices'],[0,1])
        self.assertEqual(oracle_five(['Ac','Ad','Ks','Qh','Jc']),(1,14,13,12,11))

    def test_three_way_exact_split(self):
        b=['2c','3d','4h','9s','Tc']
        hands=[['As','5s','Kc','Qd','Jh'],['Ad','5d','Ks','Qc','Jc'],['Ah','5h','Kd','Qs','Jd']]
        r=showdown(hands,b)
        self.assertEqual(r['winner_indices'],[0,1,2])
        self.assertEqual(r['shares'],[{'numerator':1,'denominator':3}]*3)
        self.assertEqual(sum(Fraction(x['numerator'],x['denominator']) for x in r['shares']),1)

    def test_reject_invalid_card_counts_and_duplicates(self):
        h=['As','Ks','2c','3d','4h'];b=['Qs','Js','Ts','9d','8c']
        for bad,board in [(h[:4],b),(h+['5h'],b),(h,b[:2]),(h,b+['6d']),(['As']*5,b),(h,['As']+b[1:]),(['XX']+h[1:],b)]:
            with self.subTest(bad=bad,board=board),self.assertRaises(ValueError):evaluate(bad,board)
        for hands,board in [([h,h],b),([h],b),([h,h+['5h']],b),([h,['5c','6c','7c','8h','9h']],b[:4])]:
            with self.assertRaises(ValueError):showdown(hands,board)

    def test_seeded_oracle_comparison_all_streets(self):
        rng=random.Random(20261125)
        for i in range(240):
            n=2+i%5; deal=rng.sample(DECK,5*n+5);b=deal[-5:]
            hands=[deal[j*5:j*5+5] for j in range(n)]
            for h in hands:
                for size in (3,4,5):
                    self.assertEqual(evaluate(h,b[:size])['rank'],oracle_omaha(h,b[:size]))
            ranks=[oracle_omaha(h,b) for h in hands];r=showdown(hands,b)
            self.assertEqual(r['ranks'],ranks)
            self.assertEqual(r['winner_indices'],[j for j,x in enumerate(ranks) if x==max(ranks)])
            self.assertEqual(sum(Fraction(x['numerator'],x['denominator']) for x in r['shares']),1)


if __name__=='__main__':unittest.main()
