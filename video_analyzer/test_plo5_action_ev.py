import copy
import unittest
from fractions import Fraction
from plo5_action_ev import analyze
from test_plo5_equity import T1,T2,T3,TB,entry


def scenario():
    return {'variant':5,'hero':T1,'board':TB,'range':[entry(T2,3),entry(T3,1),entry(T1,6)],
            'pot':100,'hero_street':10,'opponent_street':30,'hero_stack':300,'opponent_stack':300,
            'bb':10,'min_increment':20,'rake_bps':500,'rake_cap':10,'rake_on_fold':False,
            'aggressions':[{'extra':40,'call_bps':[10000,0,10000]}]}


class ActionEVTests(unittest.TestCase):
    def test_call_rake_pot_odds_and_fraction(self):
        r=analyze(scenario()); fold,call,raise_=r['actions']
        self.assertEqual(fold['ev_bb'],0)
        self.assertEqual(call['showdown_pot_chips'],120)
        self.assertEqual(call['showdown_rake_chips'],6)
        self.assertEqual(call['ev_fraction_bb'],{'numerator':41,'denominator':8})
        self.assertAlmostEqual(r['break_even_call_equity'],20/114)
        self.assertAlmostEqual(r['pot_odds_without_rake'],1/6)
        self.assertEqual(r['range_audit']['blocked_weight_fraction'],.6)
        self.assertEqual(len(r['scenario_sha256']),64)
        self.assertEqual(r['scenario_sha256'],analyze(scenario())['scenario_sha256'])

    def test_raise_conditioned_range_fold_mass_and_rake(self):
        r=analyze(scenario())['actions'][2]
        self.assertEqual(r['fold_probability_fraction'],{'numerator':1,'denominator':4})
        self.assertEqual(r['equity']['equity'],.5)
        self.assertEqual(r['showdown_pot_chips'],200)
        self.assertEqual(r['showdown_rake_chips'],10)
        self.assertEqual(r['ev_fraction_bb'],{'numerator':41,'denominator':8})
        self.assertEqual(r['sampling_interval_bb'],[5.125,5.125])

    def test_fold_rake_unmatched_raise_returned(self):
        s=scenario();s['rake_on_fold']=True;s['aggressions'][0]['call_bps']=[0,0,10000]
        r=analyze(s)['actions'][2]
        self.assertEqual(r['fold_probability'],1)
        self.assertEqual(r['fold_rake_chips'],6)
        self.assertEqual(r['ev_bb'],9.4)
        self.assertIsNone(r['equity'])

    def test_check_bet_and_all_call(self):
        s=scenario();s.update(hero_street=0,opponent_street=0,rake_bps=0)
        s['aggressions'][0]['call_bps']=[10000]*3
        r=analyze(s);check,bet=r['actions']
        self.assertEqual([check['action'],bet['action']],['check','bet'])
        self.assertEqual(check['ev_bb'],6.25)
        self.assertEqual(bet['ev_bb'],7.25)
        self.assertIsNone(r['break_even_call_equity'])

    def test_mixed_response_weights_and_partial_call(self):
        s=scenario();s['rake_bps']=0;s['aggressions'][0]['call_bps']=[5000,10000,0]
        r=analyze(s)['actions'][2]
        self.assertEqual(r['fold_probability_fraction'],{'numerator':3,'denominator':8})
        self.assertEqual(r['equity']['equity_fraction'],{'numerator':7,'denominator':10})
        self.assertEqual(r['ev_fraction_bb'],{'numerator':35,'denominator':4})

    def test_pot_limit_and_stack_bounds(self):
        s=scenario();s['aggressions'][0]['extra']=120
        self.assertEqual(analyze(s)['max_matched_extra_chips'],120)
        for field,value in [('extra',121),('extra',19),('extra',0)]:
            b=copy.deepcopy(s);b['aggressions'][0][field]=value
            with self.assertRaises(ValueError):analyze(b)
        for field,value in [('hero_stack',19),('opponent_stack',119),('pot',39),('opponent_street',9)]:
            b=copy.deepcopy(s);b[field]=value
            with self.assertRaises(ValueError):analyze(b)

    def test_sampling_intervals_and_no_gto(self):
        r=analyze(scenario(),method='monte_carlo',trials=80,seed=8)
        for a in r['actions']:
            self.assertLessEqual(a['sampling_interval_bb'][0],a['ev_bb']+1e-12)
            self.assertGreaterEqual(a['sampling_interval_bb'][1],a['ev_bb']-1e-12)
        self.assertTrue(r['sampling_intervals_are_marginal'])
        self.assertFalse(r['gto_solution']);self.assertIsNone(r['ev_loss_bb'])

    def test_reject_invalid_and_duplicate(self):
        for field,value in [('variant',6),('bb',0),('rake_bps',10001),('rake_on_fold',1),('hero_stack',True)]:
            s=scenario();s[field]=value
            with self.assertRaises(ValueError):analyze(s)
        for probs in ([10000],[-1,0,0],[True,0,0],[10001,0,0]):
            s=scenario();s['aggressions'][0]['call_bps']=probs
            with self.assertRaises(ValueError):analyze(s)
        s=scenario();s['aggressions']*=2
        with self.assertRaises(ValueError):analyze(s)
        s=scenario();s['range'][0]['weight']=100001
        with self.assertRaises(ValueError):analyze(s)


if __name__=='__main__':unittest.main()
