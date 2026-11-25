import unittest
from itertools import combinations
from math import comb
from plo5_postflop_draws import draws, decision_math, DECK
from test_plo5_evaluator import oracle_five, oracle_omaha

H=['As','Ks','Qh','Jh','Tc']
B=['9s','8s','2d']


class DrawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=draws(H,B)

    def test_wrap_flush_and_union(self):
        r=self.r; s=r['targets']['straight']; f=r['targets']['flush']
        self.assertEqual(r['straight_draw_card_count'],13);self.assertTrue(r['wrap_heuristic'])
        self.assertEqual(f['next_completion']['count'],9)
        self.assertEqual(len(set(s['next_cards']) & set(f['next_cards'])),4)
        self.assertEqual(r['combined_next_completion']['count'],18)
        self.assertEqual(r['combined_next_completion']['denominator'],44)
        self.assertEqual(r['combined_by_river_completion']['count'],621)
        self.assertEqual(r['river_runout_denominator'],946)
        self.assertEqual(len(r['top_flush_completion_cards']),9)
        self.assertEqual(r['nut_flush_completion_cards'],['3s','4s'])
        self.assertFalse(r['outs_are_winning_outs'])

    def test_backdoor_flush(self):
        r=draws(['As','Ks','Qh','Jh','Tc'],['9s','8d','2c'])
        f=r['targets']['flush'];self.assertTrue(f['backdoor_only'])
        self.assertEqual(f['next_cards'],[])
        self.assertEqual(f['by_river_completion']['count'],comb(10,2))
        self.assertEqual(f['two_card_only_completion']['count'],45)
        self.assertEqual(f['by_river_completion']['denominator'],946)

    def test_turn_rank_oracle_and_nuts(self):
        h=H;b=B+['7d'];r=draws(h,b)
        base=oracle_omaha(h,b); remain=[c for c in DECK if c not in h+b]
        self.assertEqual(r['next_card_denominator'],43)
        better=[];nuts=[];absolute=[]
        for c in remain:
            future=b+[c];rank=oracle_omaha(h,future)
            if rank>base:better.append(c)
            ranks={p:max(oracle_five(p+t) for t in combinations(future,3)) for p in combinations([x for x in DECK if x not in future],2)}
            if rank==max(ranks.values()):absolute.append(c)
            if rank>=max(v for p,v in ranks.items() if not set(p).intersection(h)):nuts.append(c)
        self.assertEqual(r['next_rank_improvement_cards'],better)
        self.assertEqual(r['next_unbeatable_after_blockers_cards'],nuts)
        self.assertEqual(r['next_absolute_board_nut_cards'],absolute)
        self.assertEqual(r['redraw_rank_improvement_cards'],better)

    def test_set_redraw_and_current_nuts_vulnerability(self):
        h=['As','Ah','Kd','Qc','Jh'];b=['Ad','7s','2c']
        r=draws(h,b);self.assertTrue(r['current_unbeatable_after_blockers'])
        self.assertEqual(r['targets']['quads']['next_cards'],['Ac'])
        self.assertEqual(len(r['targets']['full_house']['next_cards']),6)
        self.assertIn('Ac',r['redraw_rank_improvement_cards'])
        self.assertTrue(r['next_loses_unbeatable_status_cards'])

    def test_river_no_further_draw(self):
        r=draws(['As','Ks','2c','3d','4h'],['Qs','Js','Ts','9d','8c'])
        self.assertEqual(r['next_card_denominator'],0);self.assertEqual(r['river_runout_denominator'],0)
        self.assertTrue(r['current_unbeatable_after_blockers'])
        self.assertTrue(r['targets']['flush']['already_possible']);self.assertTrue(r['targets']['straight']['already_possible'])
        self.assertIsNone(r['combined_next_completion']['probability'])

    def test_decision_math_and_missing_stack(self):
        r=decision_math('10','5','70','30');self.assertAlmostEqual(r['pot_odds_without_rake'],1/3)
        self.assertEqual(r['decision_time_remaining_stack_to_pot_ratio'],3)
        self.assertEqual(r['hero_remaining_stack_to_pot_ratio'],7)
        r=decision_math('10','0','70');self.assertIsNone(r['pot_odds_without_rake']);self.assertIsNone(r['decision_time_remaining_stack_to_pot_ratio'])
        self.assertEqual(r['spr_scope'],'remaining_stacks_at_decision_not_street_start')

    def test_invalid(self):
        for h,b in ((H[:4],B),(H+['2c'],B),(H,['As','2d','3h']),(H,B[:2]),(H,['2d']*3)):
            with self.assertRaises(ValueError):draws(h,b)
        for args in (('0','0','10'),('5','6','10'),('5','4','3'),('5','1','10','-2'),('5','1/2','10'),('5',True,'10')):
            with self.assertRaises(ValueError):decision_math(*args)

    def test_review_bridge(self):
        from test_plo5_decision_analysis import BridgeTests, fixture
        t=BridgeTests();t.setUp()
        try:
            r=t.run_fixture(fixture());self.assertEqual(r['postflop_draws']['street'],'river')
            self.assertEqual(r['postflop_decision_math']['decision_time_remaining_stack_to_pot_ratio'],3)
            self.assertFalse(r['video_verified']);self.assertIsNone(r['ev_loss_bb'])
            r=t.run_fixture(fixture(True));self.assertIsNone(r['postflop_draws']);self.assertIsNone(r['postflop_decision_math'])
        finally:t.doCleanups()


if __name__=='__main__':unittest.main()
