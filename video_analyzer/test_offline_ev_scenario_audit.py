import copy
import unittest
from offline_ev_scenario_audit import audit


def fixture():
    rows=[]
    for name, q in [('wide',.30),('tight',.20)]:
        interval=[q-.01,q+.01]
        ev_interval=[200*x-50 for x in interval]
        rows.append({'range_id':name,'equity':q,'equity_interval_conditional':interval,
                     'ev_call_bb':200*q-50,'ev_interval_conditional_bb':ev_interval,
                     'conditional_label':'positive_under_interval' if ev_interval[0]>0 else 'negative_under_interval',
                     'range_is_user_assumption':True,'range_uncertainty_included_in_interval':False})
    return {'analysis_status':'hypothetical_weighted_range_ev_not_video_verified',
            'scenario_id':'synthetic','pot_before_call_bb':150,'call_cost_bb':50,
            'break_even_equity':.25,'range_results':rows,'range_sensitive':True,
            'source_hand_reconstruction_verified':False,'strategic_error_established':False,
            'automatic_clip_selection_authorized':False,'gto_solution':False,
            'range_uncertainty_included_in_interval':False}


class AuditTests(unittest.TestCase):
    def test_scenario_envelope(self):
        r=audit(fixture())
        self.assertAlmostEqual(r['ev_call_scenario_envelope_bb'][0],-12)
        self.assertAlmostEqual(r['ev_call_scenario_envelope_bb'][1],12)
        self.assertTrue(r['range_sensitive'])
        self.assertFalse(r['range_uncertainty_quantified'])
    def test_no_claim_of_video(self):
        for key in ('source_hand_reconstruction_verified','strategic_error_established','gto_solution'):
            x=fixture();x[key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):audit(x)
    def test_invalid_pot_odds(self):
        x=fixture();x['break_even_equity']=.5
        with self.assertRaises(ValueError):audit(x)
    def test_inconsistent_ev(self):
        x=fixture();x['range_results'][0]['ev_call_bb']+=1
        with self.assertRaises(ValueError):audit(x)
    def test_bad_interval(self):
        x=fixture();x['range_results'][0]['equity_interval_conditional']=[.4,.5]
        with self.assertRaises(ValueError):audit(x)
    def test_duplicate_ranges(self):
        x=fixture();x['range_results'][1]['range_id']='wide'
        with self.assertRaises(ValueError):audit(x)
    def test_bad_range_label(self):
        x=fixture();x['range_results'][0]['conditional_label']='negative_under_interval'
        with self.assertRaises(ValueError):audit(x)
    def test_bad_sensitivity_flag(self):
        x=fixture();x['range_sensitive']=False
        with self.assertRaises(ValueError):audit(x)
    def test_boolean_money_rejected(self):
        x=fixture();x['pot_before_call_bb']=True
        with self.assertRaises(ValueError):audit(x)
    def test_missing_range(self):
        x=fixture();x['range_results']=[]
        with self.assertRaises(ValueError):audit(x)
    def test_conditional_ci_is_not_range_uncertainty(self):
        x=fixture();x['range_uncertainty_included_in_interval']=True
        with self.assertRaises(ValueError):audit(x)
    def test_all_positive_scenarios(self):
        x=fixture();x['range_results'][1]=copy.deepcopy(x['range_results'][0]);x['range_results'][1]['range_id']='second';x['range_sensitive']=False
        self.assertTrue(audit(x)['all_scenarios_favor_call'])
    def test_nonfinite_rejected(self):
        x=fixture();x['range_results'][0]['equity']=float('nan')
        with self.assertRaises(ValueError):audit(x)

if __name__=='__main__':unittest.main()
