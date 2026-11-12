"""End-to-end synthetic mathematical integration: weighted equity -> EV -> audit.

No poker recordings, solver/GTO, scraped ranges or live-game interfaces.
Run: cd video_analyzer && python -m unittest -v test_offline_weighted_ev_integration
"""
import copy
import unittest

from offline_weighted_call_ev import analyze
from offline_ev_scenario_audit import audit

HERO5 = ['As','Ks','Qs','Js','Ts']
BOARD = ['2c','3d','4h','5s','9c']
RANGES = [
    {'range_id':'wide','holdings':[
        {'cards':['Ah','Kh','Qh','Jh','Th'],'weight':3},
        {'cards':['Ad','Kd','Qd','Jd','Td'],'weight':1}]},
    {'range_id':'tight','holdings':[
        {'cards':['Ac','Kc','Qc','Jc','Tc'],'weight':1}]},
]
ASSUMPTIONS = {'heads_up':True,'showdown_after_call':True,'no_rake':True,
               'no_side_pots':True,'no_future_betting':True,
               'equity_includes_tie_fraction':True}


def scenario(board=None, hero=None):
    return {'schema_version':1,
            'source_type':'manually_authored_hypothetical_not_video_verified',
            'scenario_id':'synthetic_integration',
            'hero':copy.deepcopy(HERO5 if hero is None else hero),
            'board':copy.deepcopy(BOARD if board is None else board),
            'pot_before_call_bb':150,'call_cost_bb':50,
            'ranges':copy.deepcopy(RANGES),'iterations':100,'seed':42,
            'assumptions':copy.deepcopy(ASSUMPTIONS)}


class WeightedEVIntegrationTests(unittest.TestCase):
    def test_exact_river_pipeline(self):
        report=analyze(scenario())
        checked=audit(report)
        self.assertEqual(checked['range_count'],2)
        self.assertEqual(checked['analysis_status'],'hypothetical_ev_scenario_audit_only')
        self.assertEqual([r['equity_method'] for r in report['range_results']],
                         ['exact_weighted_river']*2)
        for row in report['range_results']:
            self.assertAlmostEqual(row['ev_call_bb'],row['equity']*200-50)
            self.assertEqual(row['equity_interval_conditional'],[row['equity']]*2)
        self.assertFalse(checked['source_hand_reconstruction_verified'])
        self.assertFalse(checked['strategic_error_established'])
        self.assertFalse(checked['gto_solution'])
        self.assertFalse(checked['range_uncertainty_quantified'])

    def test_monte_carlo_pipeline_is_reproducible(self):
        s=scenario(board=BOARD[:4])
        first=analyze(s)
        second=analyze(s)
        self.assertEqual(first,second)
        self.assertEqual(audit(first),audit(second))
        self.assertTrue(all(r['trials']==100 for r in first['range_results']))
        self.assertTrue(all(r['equity_method']=='weighted_range_monte_carlo'
                            for r in first['range_results']))

    def test_plo6_exact_river_pipeline(self):
        s=scenario(hero=HERO5+['6d'])
        for r in s['ranges']:
            for h in r['holdings']:
                h['cards'].append('7h' if h['cards'][0]=='Ah' else
                                  ('8h' if h['cards'][0]=='Ad' else '9h'))
        self.assertEqual(audit(analyze(s))['range_count'],2)

    def test_pot_odds_and_envelope(self):
        report=analyze(scenario())
        checked=audit(report)
        self.assertAlmostEqual(report['break_even_equity'],.25)
        lows=[r['ev_interval_conditional_bb'][0] for r in report['range_results']]
        highs=[r['ev_interval_conditional_bb'][1] for r in report['range_results']]
        self.assertAlmostEqual(checked['ev_call_scenario_envelope_bb'][0],min(lows))
        self.assertAlmostEqual(checked['ev_call_scenario_envelope_bb'][1],max(highs))

    def test_auditor_rejects_corrupted_ev(self):
        report=analyze(scenario())
        report['range_results'][0]['ev_call_bb']+=1
        with self.assertRaises(ValueError):
            audit(report)

    def test_auditor_rejects_false_video_verification(self):
        report=analyze(scenario())
        report['source_hand_reconstruction_verified']=True
        with self.assertRaises(ValueError):
            audit(report)

    def test_auditor_rejects_false_gto_claim(self):
        report=analyze(scenario())
        report['gto_solution']=True
        with self.assertRaises(ValueError):
            audit(report)

    def test_auditor_rejects_range_uncertainty_claim(self):
        report=analyze(scenario())
        report['range_uncertainty_included_in_interval']=True
        with self.assertRaises(ValueError):
            audit(report)

    def test_range_blockers_fail_closed(self):
        s=scenario()
        for holding in s['ranges'][0]['holdings']:
            holding['cards'][0]='As'
        with self.assertRaises(ValueError):
            analyze(s)

    def test_rejects_unmodelled_rake(self):
        s=scenario()
        s['assumptions']['no_rake']=False
        with self.assertRaises(ValueError):
            analyze(s)


if __name__ == '__main__':
    unittest.main(verbosity=2)
