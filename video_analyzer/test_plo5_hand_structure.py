import random
import unittest
from collections import Counter
from itertools import combinations, permutations
from math import comb
from plo5_hand_structure import describe
from plo5_hand_classes import RANKS, SUITS


def straight_high(cards):
    v=sorted(set(14-RANKS.index(c) for c in cards))
    if v==[2,3,4,5,14]: return 5
    return v[-1] if len(v)==5 and v[-1]-v[0]==4 else 0


class StructureTests(unittest.TestCase):
    def test_broadway_double_suited(self):
        r=describe(['As','Ks','Qh','Jh','Tc'])
        self.assertEqual(r['rank_partition'],[1]*5)
        self.assertEqual(r['broadway_cards'],5)
        self.assertEqual(r['straight_capable_pairs'],10)
        self.assertEqual(r['distinct_straight_flop_rank_patterns'],20)
        self.assertEqual(len(r['top_straight_flop_rank_patterns']),20)
        self.assertEqual(r['adjacent_rank_gaps'],[0]*4)
        self.assertEqual(sum(x['suited_pairs'] for x in r['suited_groups']),2)
        self.assertEqual(sum(x['ace_high_pair_available'] for x in r['suited_groups']),1)

    def test_quads_and_rank_blockers(self):
        r=describe(['As','Ah','Ad','Ac','Ks'])
        self.assertEqual(r['rank_partition'],[4,1])
        self.assertEqual(r['paired_private_combinations'],6)
        self.assertEqual(r['straight_capable_pairs'],4)
        self.assertEqual(r['rank_blockers'][0],{'rank':'A','held':4,'unseen':0,'opponent_two_card_rank_pairs_remaining':0,'opponent_two_card_rank_pairs_removed':6})
        self.assertEqual(r['rank_blockers'][1]['opponent_two_card_rank_pairs_remaining'],3)

    def test_wheel_and_gaps(self):
        r=describe(['As','2d','9c','9d','Kh'])
        p=next(p for p in r['private_pairs'] if set(p['cards'])=={'As','2d'})
        self.assertEqual(p['straight_windows'],[{'high':5,'board_ranks':['5','4','3']}])
        self.assertEqual(r['adjacent_rank_gaps'],[0,3,6])
        self.assertTrue(any(x['board_ranks']==['5','4','3'] for x in r['top_straight_flop_rank_patterns']) is False)

    def test_suit_self_blocking(self):
        for n in range(2,6):
            h=[r+'s' for r in 'AKQJT'[:n]]+[r+'h' for r in '987'[:5-n]]
            r=describe(h);g=next(x for x in r['suited_groups'] if x['suit']=='s')
            self.assertEqual(g['suited_pairs'],comb(n,2))
            self.assertEqual(g['three_same_suit_flops'],comb(13-n,3))
            self.assertEqual(g['unseen_suit_cards'],13-n)
            self.assertEqual(r['flop_denominator_hero_only'],16215)

    def test_permutation_invariance(self):
        h=['As','Ks','Qh','Jh','Tc'];a=describe(h)
        self.assertEqual(a,describe(h[::-1]))
        for perm in permutations(SUITS):
            mapping=dict(zip(SUITS,perm));b=describe([c[0]+mapping[c[1]] for c in h])
            for key in ('hand_class','rank_partition','straight_capable_pairs','distinct_straight_flop_rank_patterns','top_straight_flop_rank_patterns','rank_blockers'):
                self.assertEqual(a[key],b[key])

    def test_independent_rank_oracle(self):
        rng=random.Random(20261125);deck=[r+s for r in RANKS for s in SUITS]
        for _ in range(24):
            h=rng.sample(deck,5);r=describe(h);counts=Counter(c[0] for c in h)
            hp=list(combinations([c[0] for c in h],2));patterns={};top={}
            for triple in combinations(RANKS,3):
                if any(counts[x]==4 for x in triple):continue
                best=max(straight_high(p+triple) for p in hp)
                if not best:continue
                patterns[triple]=best
                rem=[x for x in RANKS if counts[x]<4 and x not in triple]
                opp=max((straight_high(p+triple) for p in combinations(rem,2)),default=0)
                if best>=opp:top[triple]=(best,opp)
            self.assertEqual(r['distinct_straight_flop_rank_patterns'],len(patterns))
            self.assertEqual({tuple(x['board_ranks']):(x['hero_straight_high'],x['max_opponent_straight_high']) for x in r['top_straight_flop_rank_patterns']},top)

    def test_invalid_and_no_strategy_claim(self):
        for h in (['As']*5,['As','Ks','Qs','Js'],['As','Ks','Qs','Js','Ts','9s'],['As','Ks','Qs','Js','XX']):
            with self.assertRaises(ValueError):describe(h)
        r=describe(['As','Ks','Qh','Jh','Tc'])
        self.assertIsNone(r['equity']);self.assertIsNone(r['frequency']);self.assertIsNone(r['ev_bb']);self.assertFalse(r['gto_solution'])

    def test_bridge_preserves_descriptor_boundary(self):
        from test_plo5_decision_analysis import BridgeTests,fixture
        t=BridgeTests();t.setUp()
        try:
            r=t.run_fixture(fixture(True));ref=r['starting_equity']
            self.assertEqual(ref['hand_structure']['hand_class'],ref['hand_class'])
            self.assertFalse(ref['exact_suit_match']);self.assertIsNone(ref['frequency']);self.assertIsNone(ref['ev_bb'])
        finally:t.doCleanups()


if __name__=='__main__':unittest.main()
