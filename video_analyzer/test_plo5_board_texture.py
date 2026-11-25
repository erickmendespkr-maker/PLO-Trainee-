import random
import unittest
from fractions import Fraction
from itertools import combinations
from math import comb
from plo5_board_texture import texture, compare_ranges, DECK, pair_ranks
from test_plo5_evaluator import oracle_five, oracle_omaha
from plo5_equity import known_equity

B=['Qs','Js','Ts','9d','8c']
H=['As','Ks','2c','3d','4h']
V=['Ac','Ad','Kh','Kd','7c']


def entry(cards,weight=1): return {'cards':cards,'weight':weight}


class TextureTests(unittest.TestCase):
    def test_dry_and_connected_flops(self):
        a=texture(['Ac','7d','2h']); b=texture(['9c','8d','7h']); c=texture(['Ac','2d','3h'])
        self.assertTrue(a['dry_flop_heuristic']);self.assertFalse(a['straight_possible_now'])
        self.assertTrue(b['straight_possible_now']);self.assertFalse(b['dry_flop_heuristic'])
        self.assertTrue(c['straight_possible_now']);self.assertEqual(c['flop_suit_texture'],'rainbow')
        self.assertEqual(a['board_pairs_examined'],comb(49,2))

    def test_paired_and_suits(self):
        r=texture(['As','Ad','Ks']);self.assertTrue(r['paired']);self.assertEqual(r['rank_partition'],[2,1]);self.assertEqual(r['flop_suit_texture'],'two_tone')
        self.assertEqual(r['board_nut_rank'],[7,14,13]);self.assertFalse(r['flush_possible_now'])
        r=texture(['As','Ks','7s']);self.assertEqual(r['flop_suit_texture'],'monotone');self.assertTrue(r['flush_possible_now']);self.assertEqual(r['board_nut_category'],'flush')
        r=texture(['As','Ad','Ks','Kd']);self.assertEqual(r['rank_partition'],[2,2]);self.assertEqual(r['street'],'turn')

    def test_absolute_royal_nuts_and_blockers(self):
        r=texture(B,H);self.assertEqual(r['board_nut_rank'],[8,14]);self.assertEqual(r['board_nut_pairs'],[['Ks','As']])
        self.assertTrue(r['hero']['has_board_nuts']);self.assertTrue(r['hero']['cannot_be_tied_now']);self.assertTrue(r['hero']['cannot_be_beaten_now'])
        self.assertEqual(r['hero']['opponent_pairs_examined'],comb(42,2));self.assertEqual(r['hero']['opponent_pairs_beating_hero'],0)

    def test_blocker_relative_nuts_not_absolute(self):
        r=texture(['As','Ah','Kc'],['Ad','Kd','Qc','Jh','Tc'])
        self.assertEqual(r['hero']['made_hand']['rank'],(6,14,13));self.assertFalse(r['hero']['has_board_nuts'])
        self.assertTrue(r['hero']['cannot_be_beaten_now']);self.assertFalse(r['hero']['cannot_be_tied_now'])
        self.assertGreater(r['hero']['opponent_pairs_tying_hero'],0)

    def test_pair_oracle_all_streets(self):
        rng=random.Random(29)
        for size in (3,4,5):
            for _ in range(3):
                cards=rng.sample(DECK,size+5);b=cards[:size];h=cards[size:];r=texture(b,h)
                expected={p:max(oracle_five(p+t) for t in combinations(b,3)) for p in combinations([c for c in DECK if c not in b],2)}
                self.assertEqual(pair_ranks(b),expected)
                self.assertEqual(tuple(r['board_nut_rank']),max(expected.values()))
                self.assertEqual(r['hero']['made_hand']['rank'],oracle_omaha(h,b))
                self.assertEqual(tuple(r['hero']['opponent_max_rank_after_blockers']),max(v for p,v in expected.items() if not set(p).intersection(h)))

    def test_weighted_joint_range_and_nut_advantage(self):
        # A's royal holding is blocked by B's third holding, so weights must be jointly conditioned.
        weak=['2s','3c','4d','5h','6c']; block=['As','2d','3h','4c','5d'];
        a=[entry(H,3),entry(weak,1)]; b=[entry(V,2),entry(block,5),entry(B[:1]+['2h','3s','4s','5s'],7)]
        r=compare_ranges(B,a,b)
        self.assertEqual((r['input_joint_weight'],r['legal_joint_weight'],r['excluded_joint_weight']),(56,13,43))
        self.assertEqual(r['legal_pairings'],3);self.assertEqual(r['board_nut_weight_a'],6);self.assertEqual(r['board_nut_weight_b'],0)
        self.assertEqual(r['nut_advantage'],'A')
        expected=Fraction(0)
        for x in a:
            for y in b:
                h,v=x['cards'],y['cards']
                if len(set(h+v+B))!=15:continue
                rx,ry=oracle_omaha(h,B),oracle_omaha(v,B)
                expected+=x['weight']*y['weight']*Fraction(2 if rx>ry else 1 if rx==ry else 0,2)
        self.assertEqual(Fraction(**r['equity_a_fraction']),expected/13)
        rev=compare_ranges(B,b,a);self.assertAlmostEqual(r['equity_a']+rev['equity_a'],1)

    def test_nut_advantage_not_equity_advantage(self):
        # A has a rare royal; most of its weight is a weak hand beaten by B.
        r=compare_ranges(B,[entry(H),entry(['2s','3c','4d','5h','6c'],9)],[entry(V)])
        self.assertEqual(r['nut_advantage'],'A');self.assertEqual(r['equity_advantage'],'B')
        self.assertEqual(r['board_nut_fraction_a'],.1);self.assertFalse(r['gto_solution'])

    def test_turn_exact_matches_existing_equity(self):
        b=B[:4];r=compare_ranges(b,[entry(H)],[entry(V)])
        old=known_equity(H,b,V)
        self.assertEqual(r['evaluated_states'],38);self.assertEqual(r['equity_a_fraction'],old['equity_fraction'])

    def test_monte_carlo_reproducibility(self):
        b=B[:3];a=[entry(H)];v=[entry(V)]
        r=compare_ranges(b,a,v,method='monte_carlo',trials=60,seed=29)
        self.assertEqual(r,compare_ranges(b,a,v,method='monte_carlo',trials=60,seed=29))
        self.assertEqual(r['mass_denominator'],60);self.assertEqual(r['possible_states'],741)
        self.assertLessEqual(r['equity_a_sampling_ci95'][0],r['equity_a']);self.assertGreaterEqual(r['equity_a_sampling_ci95'][1],r['equity_a'])
        self.assertFalse(r['range_uncertainty_included'])

    def test_review_bridge(self):
        from test_plo5_decision_analysis import BridgeTests, fixture
        t=BridgeTests();t.setUp()
        try:
            r=t.run_fixture(fixture());self.assertEqual(r['postflop_texture']['street'],'river')
            self.assertEqual(r['postflop_texture']['hero']['made_hand']['rank'],oracle_omaha(r['context']['hero'],r['context']['board']))
            self.assertFalse(r['video_verified']);self.assertFalse(r['gto_solution'])
            self.assertIsNone(t.run_fixture(fixture(True))['postflop_texture'])
        finally:t.doCleanups()

    def test_invalid_and_budget(self):
        for b,h in ((B[:2],H),(B+[B[0]],H),(B,H[:4]),(B,H+['2d']),(B,[B[0]]+H[1:]),([B[0]]*3,H)):
            with self.assertRaises(ValueError):texture(b,h)
        for a,b in (([entry(H)],[entry(H)]),([entry(H),entry(H[::-1])],[entry(V)]),([entry(H,True)],[entry(V)]),([entry(H+["2d"])],[entry(V)])):
            with self.assertRaises(ValueError):compare_ranges(B,a,b)
        with self.assertRaises(ValueError):compare_ranges(B[:3],[entry(H)],[entry(V)],method='exact',max_exact=10)


if __name__=='__main__':unittest.main()
