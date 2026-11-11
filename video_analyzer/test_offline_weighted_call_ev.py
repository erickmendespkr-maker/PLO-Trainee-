"""Synthetic tests for conditional EV bridge; run from video_analyzer directory."""
import copy
import unittest
from offline_weighted_call_ev import analyze

HERO5=['As','Ks','Qs','Js','Ts']
BOARD=['2c','3d','4h','5s','9c']
WIDE=[{'cards':['Ah','Kh','Qh','Jh','Th'],'weight':3},
      {'cards':['Ad','Kd','Qd','Jd','Td'],'weight':1}]
TIGHT=[{'cards':['Ac','Kc','Qc','Jc','Tc'],'weight':1}]


def scenario():
    return {'schema_version':1,
            'source_type':'manually_authored_hypothetical_not_video_verified',
            'scenario_id':'synthetic_case',
            'hero':HERO5[:], 'board':BOARD[:],
            'pot_before_call_bb':150,'call_cost_bb':50,
            'ranges':[{'range_id':'wide','holdings':copy.deepcopy(WIDE)},
                      {'range_id':'tight','holdings':copy.deepcopy(TIGHT)}],
            'iterations':100,'seed':42,
            'assumptions':{'heads_up':True,'showdown_after_call':True,'no_rake':True,
                           'no_side_pots':True,'no_future_betting':True,
                           'equity_includes_tie_fraction':True}}


class WeightedCallEVTests(unittest.TestCase):
    def test_exact_river_ev_identity(self):
        r=analyze(scenario())
        self.assertEqual(r['break_even_equity'],.25)
        for row in r['range_results']:
            self.assertAlmostEqual(row['ev_call_bb'],row['equity']*200-50)
            self.assertEqual(row['equity_method'],'exact_weighted_river')
            self.assertEqual(row['equity_interval_conditional'],[row['equity']]*2)
            self.assertIsNone(row['trials'])
    def test_not_video_or_gto(self):
        r=analyze(scenario())
        self.assertFalse(r['source_hand_reconstruction_verified'])
        self.assertFalse(r['strategic_error_established'])
        self.assertFalse(r['gto_solution'])
        self.assertFalse(r['range_uncertainty_included_in_interval'])
    def test_repeatability_mc(self):
        s=scenario();s['board']=BOARD[:4]
        a=analyze(s);b=analyze(s)
        self.assertEqual(a,b)
        self.assertTrue(all(row['trials']==100 for row in a['range_results']))
    def test_plo6_river(self):
        s=scenario();s['hero'].append('6d')
        for r in s['ranges']:
            for h in r['holdings']:h['cards'].append('7h' if h['cards'][0]=='Ah' else ('8h' if h['cards'][0]=='Ad' else '9h'))
        self.assertEqual(len(analyze(s)['range_results']),2)
    def test_duplicate_range_id(self):
        s=scenario();s['ranges'][1]['range_id']='wide'
        with self.assertRaises(ValueError):analyze(s)
    def test_no_rake_model(self):
        s=scenario();s['assumptions']['no_rake']=False
        with self.assertRaises(ValueError):analyze(s)
    def test_no_side_pots_model(self):
        s=scenario();s['assumptions']['no_side_pots']=False
        with self.assertRaises(ValueError):analyze(s)
    def test_no_future_betting_model(self):
        s=scenario();s['assumptions']['no_future_betting']=False
        with self.assertRaises(ValueError):analyze(s)
    def test_bool_money_rejected(self):
        s=scenario();s['call_cost_bb']=True
        with self.assertRaises(ValueError):analyze(s)
    def test_duplicate_card_rejected(self):
        s=scenario();s['ranges'][0]['holdings'][0]['cards'][0]='As'
        # Blocked holdings are allowed, but if every holding in a range is
        # blocked, the model must fail instead of silently guessing a range.
        s['ranges'][0]['holdings'][1]['cards'][0]='As'
        with self.assertRaises(ValueError):analyze(s)
    def test_invalid_seed(self):
        s=scenario();s['seed']=-1
        with self.assertRaises(ValueError):analyze(s)
    def test_invalid_iterations(self):
        s=scenario();s['iterations']=0
        with self.assertRaises(ValueError):analyze(s)
    def test_missing_scenario_field(self):
        s=scenario();del s['source_type']
        with self.assertRaises(ValueError):analyze(s)
    def test_missing_range(self):
        s=scenario();s['ranges'].pop()
        with self.assertRaises(ValueError):analyze(s)
    def test_no_holdings(self):
        s=scenario();s['ranges'][0]['holdings']=[]
        with self.assertRaises(ValueError):analyze(s)


if __name__=='__main__':
    unittest.main(verbosity=2)
